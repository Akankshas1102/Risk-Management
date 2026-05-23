"""
CLI: generate 6-month walk-forward backtest for every site's champion model.

For each site, trains the champion model on data up to CUTOFF (6 months before the
site's latest data point) and predicts the following 6 months.  Actual monthly counts
come from OL_INCIDENTS.  Results stored in backtest_results (site, month, actual,
predicted, model_name).

Usage:
    python scripts/compute_backtest.py
    python scripts/compute_backtest.py --sites "BALCO" "VAL J"
    python scripts/compute_backtest.py --months 6
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from app.core.ssms import SSMSSession
from app.ml.features import build_site_monthly_series, build_bu_monthly_series, get_site_bu, _build_lag_features_from_series
from app.ml.forecaster import (
    MIN_INCIDENTS, MIN_MONTHS, train_prophet, train_xgboost, _xgb_forecast,
    _aggregate_to_quarters, _month_to_fiscal_quarter,
)
from app.models.ol_incidents import OLIncident
from app.models.predictions import ModelRun
from app.models.backtest import BacktestResult
import app.models.backtest  # noqa — registers with SSMSBase


BACKTEST_MONTHS = 6


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sites", nargs="*")
    p.add_argument("--months", type=int, default=BACKTEST_MONTHS)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def get_all_sites():
    with SSMSSession() as s:
        rows = s.execute(
            select(OLIncident.SINAME, OLIncident.BUNAME)
            .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
            .distinct()
            .order_by(OLIncident.SINAME)
        ).all()
    return [(r.SINAME, r.BUNAME) for r in rows]


def get_champion_model(site: str) -> str | None:
    """Return the champion model name for a site from model_runs."""
    with SSMSSession() as s:
        row = s.execute(
            select(ModelRun.model_name)
            .where(ModelRun.site == site, ModelRun.is_champion == True)  # noqa: E712
            .order_by(ModelRun.trained_at.desc())
            .limit(1)
        ).first()
    if row:
        return row[0]
    # Fall back to predictions_cache model_name
    with SSMSSession() as s:
        row = s.execute(
            text("SELECT TOP 1 model_name FROM predictions_cache WHERE site = :s ORDER BY trained_at DESC"),
            {"s": site},
        ).first()
    return row[0] if row else None


def _predict_monthly(series: pd.DataFrame, n_months: int, model_name: str) -> pd.DataFrame:
    """Return DataFrame [ds, yhat] predicting the next n_months from the series."""
    if model_name in ("prophet", "ensemble", "bu_prophet"):
        result = train_prophet(series)
        if result["success"]:
            future = result["model"].make_future_dataframe(periods=n_months, freq="MS")
            fc = result["model"].predict(future).tail(n_months)[["ds", "yhat"]].copy()
            fc["yhat"] = fc["yhat"].clip(lower=0)
            fc["ds"] = pd.to_datetime(fc["ds"])
            return fc

    # XGBoost fallback
    features = _build_lag_features_from_series(series)
    if not features.empty:
        result = train_xgboost(features)
        if result["success"]:
            return _xgb_forecast(result, n_months)

    return pd.DataFrame(columns=["ds", "yhat"])


def compute_site_backtest(site: str, bu: str, n_months: int) -> list[dict]:
    series = build_site_monthly_series(site)
    if series.empty or len(series) < MIN_MONTHS + n_months:
        # Use BU series scaled by site share
        bu_series = build_bu_monthly_series(bu) if bu else series
        if bu_series.empty or len(bu_series) < MIN_MONTHS + n_months:
            return []
        site_total = float(series["y"].sum()) if not series.empty else 1.0
        bu_total = float(bu_series["y"].sum())
        if bu_total == 0:
            bu_total = 1.0
        scale = (site_total / bu_total) if bu_total > 0 else 0.05
        train_series = bu_series
    else:
        scale = 1.0
        train_series = series

    # Cutoff: last n_months rows are the "future" we will evaluate
    cutoff_idx = len(train_series) - n_months
    if cutoff_idx < MIN_MONTHS:
        return []

    train_cut = train_series.iloc[:cutoff_idx].copy()
    actual_window = train_series.iloc[cutoff_idx:].copy()

    # Determine champion model name (prefer from DB, fallback ensemble)
    champ = get_champion_model(site) or "ensemble"
    # Normalise: "ensemble" → try both, pick best; for simplicity use prophet first
    use_model = "prophet" if champ in ("prophet", "ensemble") else "xgboost"

    preds_df = _predict_monthly(train_cut, n_months, use_model)
    if preds_df.empty:
        # Try the other model
        alt = "xgboost" if use_model == "prophet" else "prophet"
        preds_df = _predict_monthly(train_cut, n_months, alt)
        use_model = alt

    if preds_df.empty:
        return []

    # Align predicted with actual by ds
    preds_df = preds_df.set_index("ds")["yhat"]

    rows = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for _, act_row in actual_window.iterrows():
        ds = act_row["ds"]
        month_str = ds.strftime("%Y-%m")
        pred = float(preds_df.get(ds, np.nan))
        if np.isnan(pred):
            continue
        rows.append({
            "site": site,
            "month": month_str,
            "actual": float(act_row["y"]) * (1.0 / scale) if scale != 1.0 else float(act_row["y"]),
            "predicted": round(pred * scale, 2) if scale != 1.0 else round(pred, 2),
            "model_name": use_model,
            "computed_at": now,
        })
    return rows


def upsert_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with SSMSSession() as s:
        sites = list({r["site"] for r in rows})
        for site in sites:
            s.execute(text("DELETE FROM backtest_results WHERE site = :s"), {"s": site})
        for row in rows:
            s.add(BacktestResult(**row))
        s.commit()


def main():
    args = parse_args()
    all_pairs = get_all_sites()
    if args.sites:
        all_pairs = [(s, bu) for s, bu in all_pairs if s in args.sites]

    print(f"Computing {args.months}-month backtest for {len(all_pairs)} site(s).")
    ok = skipped = errors = 0
    all_rows: list[dict] = []

    for site, bu in all_pairs:
        try:
            rows = compute_site_backtest(site, bu, args.months)
            if not rows:
                skipped += 1
                continue
            all_rows.extend(rows)
            print(f"  {site:<35}  {len(rows)} months")
            ok += 1
        except Exception as exc:
            print(f"  ERROR {site}: {exc}", file=sys.stderr)
            errors += 1

    if not args.dry_run:
        upsert_rows(all_rows)

    print(f"\nDone. ok={ok}  skipped={skipped}  errors={errors}  rows={len(all_rows)}")
    if args.dry_run:
        print("(Dry run — no writes)")


if __name__ == "__main__":
    main()
