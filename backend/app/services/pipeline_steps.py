"""
Reusable pipeline step functions used by the orchestrator.

Each step function:
- Takes a session_factory argument (SessionLocal by default)
- Returns a summary dict {sites_processed, rows_written, errors, ...}
- Is idempotent: re-running produces no duplicates
- Never catches exceptions — the orchestrator handles that

Steps (in execution order):
  step_risk_scores  — composite risk score per site per quarter
  step_forecasters  — n-quarter-ahead predictions (Prophet / XGBoost)
  step_backtest     — walk-forward 6-month holdout evaluation
  step_drivers      — SHAP driver attribution + rules-based recommendations
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.ml.drivers import compute_drivers_for_site
from app.ml.forecaster import predict_next_n_quarters
from app.models.drivers import Recommendation, RiskDriver
from app.models.ol_incidents import OLIncident
from app.models.pipeline import RiskScore
from app.models.predictions import ModelRun, PredictionsCache
from app.services.recommendations import generate_recommendations
from app.services.risk_score import (
    _DEFAULT_WEIGHTS,
    _current_quarter_str,
    _quarter_sort_key,
    _score_to_level,
    compute_diversity_index,
    compute_frequency_index,
    compute_severity_index,
    compute_velocity_index,
)


def _to_builtin(value):
    """Convert numpy / pandas scalars into plain Python types for SQLAlchemy."""
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


# ---------------------------------------------------------------------------
# Step 1 — Risk scores (SQL Server OL_INCIDENTS → risk_scores table)
# ---------------------------------------------------------------------------

def step_risk_scores(sf=None) -> dict:
    """
    Compute composite risk scores from OL_INCIDENTS and persist to SQL Server
    risk_scores table.  Uses _DEFAULT_WEIGHTS (0.35/0.30/0.20/0.15).
    """
    sf = sf or SessionLocal

    # Load incidents as a scoring DataFrame — RTRIM/LTRIM site names so SQL Server's
    # collation (which ignores trailing spaces in UNIQUE constraints) and pandas see
    # the same canonical string for each site.
    with sf() as session:
        rows = session.execute(
            select(
                func.rtrim(func.ltrim(OLIncident.SINAME)).label("site_name"),
                OLIncident.BUNAME.label("buname"),
                OLIncident.QUARTER.label("quarter"),
                OLIncident.YEAR.label("year"),
                OLIncident.LEVELNAME.label("severity"),
                OLIncident.INCIDENTCATNAME.label("incident_category"),
            )
            .where(
                OLIncident.YEAR >= "2020",
                OLIncident.SINAME.isnot(None),
                OLIncident.YEAR.isnot(None),
                OLIncident.QUARTER.isnot(None),
            )
        ).all()

    if not rows:
        return {"sites_processed": 0, "rows_written": 0, "errors": 0, "reason": "no data"}

    df = pd.DataFrame(
        rows,
        columns=["site_name", "buname", "quarter", "year", "severity", "incident_category"],
    )
    # Normalise site names: OL_INCIDENTS has mixed-case entries ("RAM Agucha" and
    # "RAM AGUCHA").  SQL Server's default CI collation treats them as equal for
    # UNIQUE constraints; we must apply the same normalisation in Python.
    df["site_name"] = df["site_name"].str.upper().str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["severity"] = df["severity"].str.lower().fillna("low")
    df["quarter_str"] = df["year"].astype(str) + "-" + df["quarter"]

    current_q = _current_quarter_str()
    available = sorted(
        [q for q in df["quarter_str"].dropna().unique() if q != current_q],
        key=_quarter_sort_key,
    )
    if not available:
        return {"sites_processed": 0, "rows_written": 0, "errors": 0, "reason": "no complete quarters"}

    site_bu: dict[str, str | None] = (
        df.groupby("site_name")["buname"]
        .agg(lambda x: x.mode().iloc[0] if len(x.mode()) else None)
        .to_dict()
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    records: list[dict] = []

    for qstr in available:
        f_idx = compute_frequency_index(df, qstr)
        sev_idx = compute_severity_index(df, qstr)
        vel_idx = compute_velocity_index(df, qstr)
        div_idx = compute_diversity_index(df, qstr)
        qsk = _quarter_sort_key(qstr)

        for site in f_idx:
            w = _DEFAULT_WEIGHTS
            fi, si, vi, di = f_idx[site], sev_idx.get(site, 0.5), vel_idx.get(site, 0.5), div_idx.get(site, 0.5)
            score = round(max(0.0, min(100.0, 100.0 * (
                w["w_frequency"] * fi + w["w_severity"] * si
                + w["w_velocity"] * vi + w["w_diversity"] * di
            ))), 4)
            records.append({
                "site": site,
                "business_unit": site_bu.get(site),
                "quarter": qstr,
                "quarter_sort_key": qsk,
                "risk_score": score,
                "risk_level": _score_to_level(score),
                "frequency_index": round(fi, 6),
                "severity_index": round(si, 6),
                "velocity_index": round(vi, 6),
                "diversity_index": round(di, 6),
                "computed_at": now,
            })

    # Deduplicate (safety net in case the same site+quarter was computed twice)
    seen_keys: set[tuple] = set()
    unique_records = []
    for rec in records:
        key = (rec["site"], rec["quarter"])
        if key not in seen_keys:
            seen_keys.add(key)
            unique_records.append(rec)
    records = unique_records

    # Two-phase upsert: DELETE committed before INSERT so the ORM never
    # sees stale rows alongside new objects in the same session flush.
    with sf() as session:
        session.execute(text("DELETE FROM risk_scores"))   # full replace on each run
        session.commit()

    with sf() as session:
        for rec in records:
            session.add(RiskScore(**rec))
        session.commit()

    sites = len({r["site"] for r in records})
    return {"sites_processed": sites, "rows_written": len(records), "errors": 0}


# ---------------------------------------------------------------------------
# Step 2 — Forecasters (train + cache predictions)
# ---------------------------------------------------------------------------

def _all_sites(sf) -> list[tuple[str, str]]:
    with sf() as session:
        rows = session.execute(
            select(OLIncident.SINAME, OLIncident.BUNAME)
            .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
            .distinct()
            .order_by(OLIncident.SINAME)
        ).all()
    return [(r.SINAME, r.BUNAME) for r in rows]


def step_forecasters(sf=None, n_quarters: int = 3) -> dict:
    """Train forecasters for all sites and persist predictions_cache + model_runs."""
    sf = sf or SessionLocal
    trained_at = datetime.now(timezone.utc).replace(tzinfo=None)
    all_pairs = _all_sites(sf)

    pred_records: list[dict] = []
    run_records: list[dict] = []
    errors = 0

    for site, bu in all_pairs:
        try:
            df = predict_next_n_quarters(site, n=n_quarters, session_factory=sf)
            if df.empty:
                continue
            for _, row in df.iterrows():
                pred_records.append({
                    "site": site, "business_unit": bu,
                    "target_quarter": row["target_quarter"],
                    "predicted_count": _to_builtin(row["predicted_count"]),
                    "lower_ci": _to_builtin(row["lower_ci"]),
                    "upper_ci": _to_builtin(row["upper_ci"]),
                    "model_name": row["model_name"],
                    "trained_at": trained_at,
                    "training_data_through": row.get("training_data_through"),
                    "confidence_band": row["confidence_band"],
                })
            first = df.iloc[0]
            for key, name in [("_prophet", "prophet"), ("_xgb", "xgboost")]:
                rmse = first.get(f"{key}_rmse")
                if rmse is None:
                    continue
                run_records.append({
                    "model_name": name, "site": site,
                    "trained_at": trained_at,
                    "training_rows": int(first.get(f"{key}_n") or 0),
                    "holdout_rmse": _to_builtin(rmse),
                    "holdout_mape": _to_builtin(first.get(f"{key}_mape")),
                    "is_champion": False,
                    "notes": f"confidence={first['confidence_band']}",
                })
        except Exception as exc:
            errors += 1

    # Set is_champion (lower RMSE) per site
    from itertools import groupby
    run_records.sort(key=lambda r: r["site"] or "")
    for _, grp in groupby(run_records, key=lambda r: r["site"]):
        grp_list = list(grp)
        best = min(grp_list, key=lambda r: r["holdout_rmse"] or 9999)
        best["is_champion"] = True

    # Persist — delete existing predictions per site then insert
    sites_with_preds = list({r["site"] for r in pred_records})
    with sf() as session:
        for site in sites_with_preds:
            session.execute(text("DELETE FROM predictions_cache WHERE site = :s"), {"s": site})
        for rec in pred_records:
            session.add(PredictionsCache(**rec))
        for rec in run_records:
            session.add(ModelRun(**rec))
        session.commit()

    return {
        "sites_processed": len(all_pairs),
        "rows_written": len(pred_records),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Step 3 — Drivers and recommendations
# ---------------------------------------------------------------------------

def _get_site_context(site: str, sf) -> dict:
    """Compute site-level context used by the recommendations rules engine."""
    with sf() as session:
        row = session.execute(
            text("""
                SELECT year, quarter, COUNT(*) as total
                FROM ol_incidents
                WHERE siname = :s AND CAST(NULLIF(year, '') AS INTEGER) > 2000
                GROUP BY year, quarter
                ORDER BY CAST(NULLIF(year, '') AS INTEGER)*10 +
                    CASE quarter WHEN 'Q4' THEN 0 WHEN 'Q1' THEN 1
                                 WHEN 'Q2' THEN 2 ELSE 3 END DESC
                LIMIT 1
            """),
            {"s": site},
        ).first()
        if not row:
            return {}

        prev = session.execute(
            text("""
                SELECT COUNT(*) as total FROM ol_incidents
                WHERE siname = :s AND CAST(NULLIF(year, '') AS INTEGER) > 2000
                  AND NOT (year = :y AND quarter = :q)
                GROUP BY year, quarter
                ORDER BY CAST(NULLIF(year, '') AS INTEGER)*10 +
                    CASE quarter WHEN 'Q4' THEN 0 WHEN 'Q1' THEN 1
                                 WHEN 'Q2' THEN 2 ELSE 3 END DESC
                LIMIT 1
            """),
            {"s": site, "y": row.year, "q": row.quarter},
        ).first()

        lag_rows = session.execute(
            text("""
                SELECT occureddate, reporteddate FROM ol_incidents
                WHERE siname = :s AND year = :y AND quarter = :q
                  AND occureddate IS NOT NULL AND reporteddate IS NOT NULL
                  AND LENGTH(occureddate) = 10 AND LENGTH(reporteddate) = 10
            """),
            {"s": site, "y": row.year, "q": row.quarter},
        ).all()

        bu_row = session.execute(
            select(OLIncident.BUNAME)
            .where(OLIncident.SINAME == site).limit(1)
        ).first()

    lags = []
    for r in lag_rows:
        try:
            lags.append((pd.Timestamp(r.REPORTEDDATE) - pd.Timestamp(r.OCCUREDDATE)).days)
        except Exception:
            pass

    prev_total = prev.total if prev else None
    delta = (
        round((row.total - prev_total) / prev_total * 100, 1) if prev_total else None
    )
    return {
        "site": site,
        "quarter": f"{row.year}-{row.quarter}",
        "total_incidents_qtr": row.total,
        "delta_qtr_pct": delta,
        "reporting_lag_p90": float(np.percentile(lags, 90)) if lags else None,
        "business_unit": bu_row[0] if bu_row else None,
    }


def step_drivers(sf=None) -> dict:
    """Compute SHAP drivers and recommendations for all sites."""
    sf = sf or SessionLocal
    all_pairs = _all_sites(sf)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    errors = 0
    driver_rows = 0
    rec_rows = 0

    for site, bu in all_pairs:
        try:
            drivers_df = compute_drivers_for_site(site, session_factory=sf)
            if drivers_df.empty:
                continue
            top10 = drivers_df.head(10).to_dict(orient="records")
            ctx = _get_site_context(site, sf)
            quarter = ctx.get("quarter") or drivers_df.iloc[0]["quarter"]
            recs = generate_recommendations(top10, ctx)

            with sf() as session:
                # Drivers: delete+insert per site
                session.execute(text("DELETE FROM risk_drivers WHERE site = :s"), {"s": site})
                for _, row in drivers_df.head(10).iterrows():
                    session.add(RiskDriver(
                        site=site, quarter=row["quarter"],
                        driver_name=row["driver_name"], category=row["category"],
                        impact_score=row["impact_score"], trend=row["trend"],
                        pct_change_vs_last_qtr=row["pct_change_vs_last_qtr"],
                        sparkline_data=row.get("sparkline_data"),
                        computed_at=row["computed_at"],
                    ))
                # Recommendations: delete+insert per site+quarter
                session.execute(
                    text("DELETE FROM recommendations WHERE site = :s AND quarter = :q"),
                    {"s": site, "q": quarter},
                )
                for rec in recs:
                    session.add(Recommendation(
                        site=site, quarter=quarter,
                        action_text=rec.action_text, priority=rec.priority,
                        impact_estimate=rec.impact_estimate or "",
                        suggested_owner=rec.suggested_owner or "",
                        status="open", source=rec.source,
                        driver_link=rec.driver_link or "",
                        created_at=now,
                    ))
                session.commit()

            driver_rows += min(10, len(drivers_df))
            rec_rows += len(recs)
        except Exception:
            errors += 1

    return {
        "sites_processed": len(all_pairs),
        "driver_rows_written": driver_rows,
        "rec_rows_written": rec_rows,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Step 3b — Walk-forward backtest (runs after forecasters, before drivers)
# ---------------------------------------------------------------------------

def step_backtest(sf=None) -> dict:
    """
    Run 6-month walk-forward holdout backtest for all sites and persist
    results to backtest_results.

    Delegates entirely to ``run_all_backtests()``.  Returns a summary dict
    with keys: ok, skipped, errors, total_rows (rows written to DB).

    A site is *skipped* (not *errored*) when it has insufficient history
    for the holdout window (e.g. VLCTPP).

    Parameters
    ----------
    sf : Unused — backtest module manages its own DB connections.
         Accepted for API consistency with the other step functions.
    """
    # run_all_backtests handles its own DB connections via SessionLocal
    from app.ml.backtest import run_all_backtests  # noqa: PLC0415

    result = run_all_backtests()   # site_pairs=None → all sites from OL_INCIDENTS
    # Normalise key names to match the step-result convention used by the orchestrator
    return {
        "sites_ok": result.get("ok", 0),
        "sites_skipped": result.get("skipped", 0),
        "errors": result.get("errors", 0),
        "rows_written": result.get("total_rows", 0),
    }
