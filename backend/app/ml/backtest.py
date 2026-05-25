"""
Walk-forward backtest engine for site incident forecasters.

Public API
----------
compute_site_backtest(site, bu, n_months) -> list[dict]
    Walk-forward holdout: train on data up to (end - n_months), predict n_months
    forward, compare to actuals.  Returns rows ready for BacktestResult insertion.

run_all_backtests(sites, n_months, dry_run) -> dict
    Run backtest for every (site, bu) pair; upsert results into backtest_results.

compute_abs_pct_error(actual, predicted) -> float | None
    Helper: |actual - predicted| / actual * 100, or None when actual == 0.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.ml.features import (
    _build_lag_features_from_series,
    build_bu_monthly_series,
    build_site_monthly_series,
    get_site_bu,
)
from app.ml.forecaster import (
    MIN_INCIDENTS,
    MIN_MONTHS,
    _xgb_forecast,
    train_prophet,
    train_xgboost,
)
from app.models.backtest import BacktestResult
from app.models.predictions import ModelRun
import app.models.backtest  # noqa — registers BacktestResult with Base metadata

log = logging.getLogger(__name__)

# Default walk-forward window (months held out for evaluation)
DEFAULT_BACKTEST_MONTHS = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_abs_pct_error(actual: Optional[float], predicted: Optional[float]) -> Optional[float]:
    """
    Return |actual - predicted| / actual * 100.
    Returns None when actual is None, zero, or predicted is None.
    """
    if actual is None or predicted is None or actual == 0:
        return None
    return abs(actual - predicted) / actual * 100.0


def _get_champion_model(site: str) -> str | None:
    """Return the champion model name for a site from model_runs (latest champion row)."""
    with SessionLocal() as s:
        row = s.execute(
            select(ModelRun.model_name)
            .where(ModelRun.site == site, ModelRun.is_champion == True)  # noqa: E712
            .order_by(ModelRun.trained_at.desc())
            .limit(1)
        ).first()
    if row:
        return row[0]
    # Fall back to predictions_cache model_name
    with SessionLocal() as s:
        row = s.execute(
            text("SELECT model_name FROM predictions_cache WHERE site = :s ORDER BY trained_at DESC LIMIT 1"),
            {"s": site},
        ).first()
    return row[0] if row else None


def _predict_monthly(
    series: pd.DataFrame,
    n_months: int,
    model_name: str,
) -> pd.DataFrame:
    """
    Return DataFrame [ds, yhat] predicting the next n_months from the series end.
    Tries prophet first (or the requested model), falls back to xgboost.
    """
    use_prophet = model_name in ("prophet", "ensemble", "bu_prophet")
    use_xgb = model_name in ("xgboost", "ensemble")

    if use_prophet:
        result = train_prophet(series)
        if result["success"]:
            future = result["model"].make_future_dataframe(periods=n_months, freq="MS")
            fc = result["model"].predict(future).tail(n_months)[["ds", "yhat"]].copy()
            fc["yhat"] = fc["yhat"].clip(lower=0)
            fc["ds"] = pd.to_datetime(fc["ds"])
            return fc

    if use_xgb or True:  # always try XGBoost as fallback
        features = _build_lag_features_from_series(series)
        if not features.empty:
            result = train_xgboost(features)
            if result["success"]:
                return _xgb_forecast(result, n_months)

    return pd.DataFrame(columns=["ds", "yhat"])


# ---------------------------------------------------------------------------
# Core backtest function
# ---------------------------------------------------------------------------

def compute_site_backtest(
    site: str,
    bu: Optional[str] = None,
    n_months: int = DEFAULT_BACKTEST_MONTHS,
) -> list[dict]:
    """
    Walk-forward backtest for one site.

    Strategy
    --------
    1. Build the monthly series (site-level or BU-level fallback).
    2. Split: train on all rows before the last n_months; holdout = last n_months.
    3. Train the champion model (or ensemble) on the training split.
    4. Predict n_months forward.
    5. Align predicted vs actual by month and compute abs_pct_error.

    Returns
    -------
    List of dicts ready for BacktestResult(**row) insertion.
    Each dict has: site, month, actual, predicted, abs_pct_error, model_name, computed_at.
    """
    series = build_site_monthly_series(site)
    bu_name = bu or get_site_bu(site)

    if series.empty or len(series) < MIN_MONTHS + n_months:
        bu_series = build_bu_monthly_series(bu_name) if bu_name else pd.DataFrame()
        if bu_series.empty or len(bu_series) < MIN_MONTHS + n_months:
            log.info("Skipping %s: insufficient data for %d-month backtest", site, n_months)
            return []

        # Scale BU predictions to site level
        site_total = float(series["y"].sum()) if not series.empty else 0.0
        bu_total = float(bu_series["y"].sum()) or 1.0
        scale = (site_total / bu_total) if bu_total > 0 else 0.05
        train_series = bu_series
    else:
        scale = 1.0
        train_series = series

    cutoff_idx = len(train_series) - n_months
    if cutoff_idx < MIN_MONTHS:
        log.info("Skipping %s: cutoff too early (only %d training months)", site, cutoff_idx)
        return []

    train_cut = train_series.iloc[:cutoff_idx].copy()
    actual_window = train_series.iloc[cutoff_idx:].copy()

    # Determine which model to use
    champ = _get_champion_model(site) or "ensemble"
    use_model = "prophet" if champ in ("prophet", "ensemble", "bu_prophet") else "xgboost"

    preds_df = _predict_monthly(train_cut, n_months, use_model)
    if preds_df.empty:
        # Try alternate model
        alt = "xgboost" if use_model == "prophet" else "prophet"
        preds_df = _predict_monthly(train_cut, n_months, alt)
        use_model = alt

    if preds_df.empty:
        log.warning("No predictions produced for %s", site)
        return []

    preds_map = preds_df.set_index(pd.to_datetime(preds_df["ds"]))["yhat"].to_dict()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows: list[dict] = []
    for _, act_row in actual_window.iterrows():
        ds = pd.Timestamp(act_row["ds"])
        raw_pred = preds_map.get(ds, np.nan)
        if np.isnan(raw_pred):
            continue

        # Un-scale: actual is stored as site actual; predicted was done on BU series then scaled
        actual_val = float(act_row["y"]) / scale if scale != 1.0 else float(act_row["y"])
        pred_val = round(float(raw_pred) * scale, 2) if scale != 1.0 else round(float(raw_pred), 2)

        rows.append({
            "site": site,
            "month": ds.strftime("%Y-%m"),
            "actual": actual_val,
            "predicted": pred_val,
            "abs_pct_error": compute_abs_pct_error(actual_val, pred_val),
            "model_name": use_model,
            "computed_at": now,
        })

    return rows


# ---------------------------------------------------------------------------
# Batch runner (called by scripts/run_backtest.py)
# ---------------------------------------------------------------------------

def upsert_backtest_rows(rows: list[dict]) -> None:
    """DELETE+INSERT backtest rows per site (UNIQUE constraint on (site, month))."""
    if not rows:
        return
    sites = list({r["site"] for r in rows})
    with SessionLocal() as s:
        for site in sites:
            s.execute(text("DELETE FROM backtest_results WHERE site = :s"), {"s": site})
        for row in rows:
            s.add(BacktestResult(**row))
        s.commit()


def run_all_backtests(
    site_pairs: Optional[list[tuple[str, str]]] = None,
    n_months: int = DEFAULT_BACKTEST_MONTHS,
    dry_run: bool = False,
) -> dict:
    """
    Run walk-forward backtest for all (or a subset of) sites.

    Parameters
    ----------
    site_pairs : list of (site, bu) tuples.  Defaults to all distinct sites in OL_INCIDENTS.
    n_months   : holdout window size (default 6).
    dry_run    : if True, compute but do not write to DB.

    Returns
    -------
    dict with keys: ok, skipped, errors, total_rows.
    """
    from app.models.ol_incidents import OLIncident

    if site_pairs is None:
        with SessionLocal() as s:
            rows = s.execute(
                select(OLIncident.SINAME, OLIncident.BUNAME)
                .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
                .distinct()
                .order_by(OLIncident.SINAME)
            ).all()
        site_pairs = [(r.SINAME, r.BUNAME) for r in rows]

    ok = skipped = errors = 0
    all_rows: list[dict] = []

    for site, bu in site_pairs:
        try:
            site_rows = compute_site_backtest(site, bu, n_months)
            if not site_rows:
                skipped += 1
                continue
            all_rows.extend(site_rows)
            ok += 1
            log.debug("Backtest %s: %d months", site, len(site_rows))
        except Exception as exc:
            log.error("Backtest ERROR %s: %s", site, exc)
            errors += 1

    if not dry_run:
        upsert_backtest_rows(all_rows)

    return {"ok": ok, "skipped": skipped, "errors": errors, "total_rows": len(all_rows)}
