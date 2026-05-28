"""
Per-site data & model health snapshot service.

Powers the "Site Detail" drawer in the frontend Data Health tab.

Public API
----------
get_site_detail(site, db) -> dict
    Returns a single self-describing payload that lets the frontend
    explain — without hardcoding anything — how much data a site has,
    which quarters were used to train the forecaster, which were held
    out to test it, what the predictions vs actuals were, and what
    the system thinks the next 3 quarters will look like.

system_accuracy(db) -> dict
    Aggregate accuracy across all sites (incident-weighted average of
    pct_within_20).  Used for the system-level "Average Accuracy" KPI.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ml.features import build_site_quarterly_series, get_site_bu
from app.ml.forecaster import HOLDOUT_QUARTERS, _quarter_start_to_fiscal
from app.models.backtest import BacktestResult
from app.models.ol_incidents import OLIncident
from app.models.predictions import ModelRun, PredictionsCache
from app.services.risk_score import _quarter_sort_key


# ---------------------------------------------------------------------------
# Quarter / month helpers
# ---------------------------------------------------------------------------

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ym_label(year: int, month: int) -> str:
    """`(2024, 5) -> 'May 2024'`."""
    return f"{_MONTH_NAMES[month - 1]} {year}"


def _quarter_label(qstr: str) -> str:
    """`'2024-Q1' -> '2024-Q1 (Apr-Jun 2024)'`."""
    try:
        year_s, q = qstr.split("-")
        ranges = {
            "Q1": "Apr-Jun", "Q2": "Jul-Sep", "Q3": "Oct-Dec", "Q4": "Jan-Mar",
        }
        return f"{qstr} ({ranges.get(q, '')} {year_s})"
    except Exception:
        return qstr


# ---------------------------------------------------------------------------
# Status / explanation derivation
# ---------------------------------------------------------------------------

_MIN_INCIDENTS = 50
_MIN_QUARTERS = 4
_MIN_MONTHS_FOR_HEALTHY = 12


def _derive_status_and_reason(
    incidents: int,
    n_quarters: int,
    n_months: int,
    champion_model: Optional[str],
    pct_within_20: Optional[float],
) -> tuple[str, str]:
    """
    Return (status, plain_english_reason) consistent with the values used
    by the diagnostics endpoint, plus a human explanation suitable for the
    frontend "Why this status" panel.
    """
    if not champion_model or champion_model == "none":
        return (
            "Insufficient data",
            f"This site has only {incidents} incident(s) over {n_quarters} "
            f"quarter(s).  The forecaster needs at least {_MIN_INCIDENTS} "
            f"incidents AND {_MIN_QUARTERS} quarters of history to train, "
            f"so no model could be built and no predictions are produced."
        )

    if incidents < _MIN_INCIDENTS or n_quarters < _MIN_QUARTERS:
        return (
            "Sparse - BU fallback",
            f"This site has {incidents} incidents over {n_quarters} "
            f"quarter(s) — below the {_MIN_INCIDENTS}/{_MIN_QUARTERS} "
            f"threshold for a site-only model.  We trained on the whole "
            f"business unit instead and scaled the prediction by this "
            f"site's historical share of the BU."
        )

    if pct_within_20 is None:
        return (
            "No backtest",
            f"A site-level model exists ({champion_model}) but the holdout "
            f"backtest could not run — usually because the actual values "
            f"in the holdout window were zero, which makes the percentage "
            f"error undefined."
        )

    if pct_within_20 >= 75:
        return (
            "Healthy",
            f"The {champion_model} model was within ±20% of actual for "
            f"{pct_within_20:.0f}% of the holdout quarters.  This is "
            f"considered a healthy fit."
        )
    if pct_within_20 >= 50:
        return (
            "OK",
            f"The {champion_model} model was within ±20% of actual for "
            f"{pct_within_20:.0f}% of the holdout quarters.  Acceptable "
            f"but not yet healthy (≥75% target)."
        )
    return (
        "Low accuracy",
        f"The {champion_model} model was within ±20% of actual for only "
        f"{pct_within_20:.0f}% of the holdout quarters.  Consider checking "
        f"the data for outliers or waiting for more history before relying "
        f"on the forecast."
    )


# ---------------------------------------------------------------------------
# Public API — get_site_detail
# ---------------------------------------------------------------------------

def get_site_detail(site: str, db: Session) -> dict[str, Any]:
    """
    Return everything the frontend needs to explain one site:

      • totals (incidents, distinct months, distinct quarters, date range)
      • per-year and per-month breakdowns
      • the **actual** quarterly time series (so the chart can be drawn)
      • which quarters were held out for testing
      • the worked example: predictions vs actuals + per-row error
      • the next-quarter forecast rows
      • the champion model + plain-English status reason

    All numbers are derived live from the database — nothing hardcoded.

    Returns
    -------
    dict (JSON-serialisable).  See the frontend type SiteDetailResponse
    for the full shape.
    """
    # ── 1. BU + total incidents/months/years -----------------------------
    bu = get_site_bu(site)

    yearly_rows = db.execute(text("""
        SELECT CAST(NULLIF(year,'') AS INTEGER) AS yr, COUNT(*) AS n
        FROM ol_incidents
        WHERE siname = :s AND CAST(NULLIF(year,'') AS INTEGER) IS NOT NULL
        GROUP BY yr ORDER BY yr
    """), {"s": site}).all()
    per_year = [{"year": int(r.yr), "incidents": int(r.n)} for r in yearly_rows]
    total_incidents = sum(r["incidents"] for r in per_year)

    monthly_rows = db.execute(text("""
        SELECT CAST(NULLIF(year,'') AS INTEGER) AS yr, month AS mo, COUNT(*) AS n
        FROM ol_incidents
        WHERE siname = :s AND CAST(NULLIF(year,'') AS INTEGER) IS NOT NULL
          AND month IS NOT NULL
        GROUP BY yr, mo ORDER BY yr, mo
    """), {"s": site}).all()
    per_month = [
        {"year": int(r.yr), "month": int(r.mo),
         "label": _ym_label(int(r.yr), int(r.mo)), "incidents": int(r.n)}
        for r in monthly_rows
    ]

    # First / last incident date directly from CSV strings
    range_row = db.execute(text("""
        SELECT MIN(occureddate) AS first_d, MAX(occureddate) AS last_d
        FROM ol_incidents
        WHERE siname = :s AND LENGTH(occureddate) = 10
    """), {"s": site}).first()
    first_incident = range_row.first_d if range_row else None
    last_incident  = range_row.last_d  if range_row else None

    # ── 2. Per-quarter time series (excluding partial current quarter) --
    series = build_site_quarterly_series(site)
    quarterly_series: list[dict] = []
    for _, row in series.iterrows():
        ds = row["ds"]
        q  = _quarter_start_to_fiscal(ds)
        quarterly_series.append({
            "quarter": q,
            "label": _quarter_label(q),
            "incidents": int(row["y"]),
        })

    n_quarters = len(quarterly_series)
    n_months   = len(per_month)


    # ── 3. Champion model row -------------------------------------------
    champ = db.execute(
        select(ModelRun)
        .where(ModelRun.site == site, ModelRun.is_champion == True)  # noqa: E712
        .order_by(ModelRun.trained_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    champion_model    = champ.model_name if champ else None
    holdout_rmse      = float(champ.holdout_rmse) if champ and champ.holdout_rmse is not None else None
    holdout_mape      = float(champ.holdout_mape) if champ and champ.holdout_mape is not None else None
    training_rows_in_model = int(champ.training_rows) if champ and champ.training_rows is not None else None
    last_trained_at   = champ.trained_at.isoformat() if champ and champ.trained_at else None

    # ── 4. Backtest worked example --------------------------------------
    bt_rows = db.execute(
        select(BacktestResult)
        .where(BacktestResult.site == site)
        .order_by(BacktestResult.month.asc())
    ).scalars().all()

    backtest = []
    for r in bt_rows:
        actual = float(r.actual) if r.actual is not None else None
        pred   = float(r.predicted) if r.predicted is not None else None
        ape    = float(r.abs_pct_error) if r.abs_pct_error is not None else None
        backtest.append({
            "quarter": r.month,                # the column is "month" but stores 'YYYY-Qn'
            "label": _quarter_label(r.month),
            "actual": round(actual, 2) if actual is not None else None,
            "predicted": round(pred, 2) if pred is not None else None,
            "abs_pct_error": round(ape, 2) if ape is not None else None,
            "within_20": (ape is not None and ape <= 20),
        })


    # Aggregate accuracy
    valid = [b["abs_pct_error"] for b in backtest if b["abs_pct_error"] is not None]
    n_bt = len(valid)
    mean_ape = round(sum(valid) / n_bt, 2) if n_bt else None
    pct_within_20 = (
        round(sum(1 for v in valid if v <= 20) / n_bt * 100, 1)
        if n_bt else None
    )
    pct_within_30 = (
        round(sum(1 for v in valid if v <= 30) / n_bt * 100, 1)
        if n_bt else None
    )

    # Train / holdout window labels (derived from the actual series)
    holdout_window: list[str] = []
    train_window: list[str] = []
    if n_quarters >= HOLDOUT_QUARTERS:
        holdout_window = [
            quarterly_series[i]["quarter"]
            for i in range(n_quarters - HOLDOUT_QUARTERS, n_quarters)
        ]
        train_window = [
            quarterly_series[i]["quarter"]
            for i in range(0, n_quarters - HOLDOUT_QUARTERS)
        ]


    # ── 5. Forecast (next n quarters) -----------------------------------
    pred_rows = db.execute(
        select(PredictionsCache)
        .where(PredictionsCache.site == site)
        .order_by(PredictionsCache.target_quarter.asc())
    ).scalars().all()
    # Sort by fiscal-quarter sort key for safety
    pred_rows = sorted(pred_rows, key=lambda p: _quarter_sort_key(p.target_quarter))

    forecast = [{
        "quarter": p.target_quarter,
        "label": _quarter_label(p.target_quarter),
        "predicted": round(float(p.predicted_count), 2) if p.predicted_count is not None else None,
        "lower_ci": round(float(p.lower_ci), 2) if p.lower_ci is not None else None,
        "upper_ci": round(float(p.upper_ci), 2) if p.upper_ci is not None else None,
        "model_name": p.model_name,
        "confidence_band": p.confidence_band,
        "training_data_through": p.training_data_through,
    } for p in pred_rows]

    # ── 6. Status + plain-English reason --------------------------------
    status, reason = _derive_status_and_reason(
        incidents=total_incidents,
        n_quarters=n_quarters,
        n_months=n_months,
        champion_model=champion_model,
        pct_within_20=pct_within_20,
    )


    # ── 7. Final payload ------------------------------------------------
    return {
        "site": site,
        "business_unit": bu,
        "totals": {
            "incidents": total_incidents,
            "distinct_months": n_months,
            "distinct_quarters": n_quarters,
            "first_incident": first_incident,
            "last_incident": last_incident,
        },
        "per_year": per_year,
        "per_month": per_month,
        "quarterly_series": quarterly_series,
        "training": {
            "train_quarters": train_window,
            "holdout_quarters": holdout_window,
            "holdout_size": HOLDOUT_QUARTERS,
        },
        "model": {
            "champion_model": champion_model,
            "holdout_rmse": round(holdout_rmse, 2) if holdout_rmse is not None else None,
            "holdout_mape": round(holdout_mape, 2) if holdout_mape is not None else None,
            "training_rows": training_rows_in_model,
            "last_trained_at": last_trained_at,
        },
        "backtest": {
            "rows": backtest,
            "mean_ape": mean_ape,
            "pct_within_20": pct_within_20,
            "pct_within_30": pct_within_30,
            "n_quarters": n_bt,
        },
        "forecast": forecast,
        "status": status,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Public API — system-level accuracy
# ---------------------------------------------------------------------------

def system_accuracy(db: Session) -> dict[str, Any]:
    """
    Aggregate accuracy across every site that has a backtest.

    Returns
    -------
    dict with:
        avg_pct_within_20   — unweighted mean of pct_within_20 across sites
        weighted_pct_within_20 — incident-weighted average (gives big sites
                                 more influence; this is the headline KPI)
        sites_evaluated      — # sites that have at least one backtest row
        sites_total          — # distinct sites in ol_incidents
        sites_no_model       — # sites without a champion (red status)
        sites_sparse         — # sites on BU-fallback (amber status)
    """
    rows = db.execute(text("""
        SELECT br.site,
               AVG(br.abs_pct_error) AS mean_ape,
               SUM(CASE WHEN br.abs_pct_error <= 20 THEN 1.0 ELSE 0.0 END)
                 / NULLIF(COUNT(*),0) * 100  AS pct_within_20,
               COUNT(*)                       AS n_qtrs,
               (SELECT COUNT(*) FROM ol_incidents oi WHERE oi.siname = br.site) AS incidents
        FROM backtest_results br
        WHERE br.abs_pct_error IS NOT NULL
        GROUP BY br.site
    """)).all()

    if rows:
        n = len(rows)
        avg_pw20 = round(sum((float(r.pct_within_20) or 0) for r in rows) / n, 1)
        total_inc = sum(int(r.incidents) for r in rows) or 1
        weighted = round(
            sum(float(r.pct_within_20 or 0) * int(r.incidents) for r in rows) / total_inc,
            1,
        )
    else:
        avg_pw20, weighted = None, None


    sites_total = db.execute(
        text("SELECT COUNT(DISTINCT siname) FROM ol_incidents WHERE siname IS NOT NULL")
    ).scalar() or 0

    sites_no_model = db.execute(text("""
        SELECT COUNT(DISTINCT oi.siname)
        FROM ol_incidents oi
        WHERE oi.siname IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM model_runs mr
              WHERE mr.site = oi.siname AND mr.is_champion = true
          )
    """)).scalar() or 0

    sites_sparse = db.execute(text("""
        SELECT COUNT(DISTINCT site)
        FROM model_runs
        WHERE is_champion = true AND model_name = 'bu_prophet'
    """)).scalar() or 0

    return {
        "avg_pct_within_20": avg_pw20,
        "weighted_pct_within_20": weighted,
        "sites_evaluated": len(rows),
        "sites_total": int(sites_total),
        "sites_no_model": int(sites_no_model),
        "sites_sparse_bu_fallback": int(sites_sparse),
    }
