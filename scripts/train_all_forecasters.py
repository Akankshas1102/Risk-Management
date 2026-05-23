"""
CLI: train forecasting models for every site and persist predictions to SQL Server.

Usage:
    python scripts/train_all_forecasters.py
    python scripts/train_all_forecasters.py --sites "ENABLING" "VAL J"
    python scripts/train_all_forecasters.py --quarters 3 --dry-run

Run apply_ssms_migrations.py first if predictions_cache/model_runs don't exist yet.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import pandas as pd
from sqlalchemy import select, text

from app.core.ssms import SSMSSession, ssms_engine
from app.ml.features import build_site_monthly_series
from app.ml.forecaster import (
    MIN_INCIDENTS,
    MIN_MONTHS,
    predict_next_n_quarters,
    train_prophet,
    train_xgboost,
    _build_lag_features_from_series,
)
from app.models.ol_incidents import OLIncident
from app.models.predictions import ModelRun, PredictionsCache
import app.models.predictions  # noqa — registers tables with SSMSBase


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train forecasters and cache predictions.")
    p.add_argument("--sites", nargs="*", help="Specific sites to train (default: all)")
    p.add_argument("--quarters", type=int, default=3, help="Quarters to predict (default: 3)")
    p.add_argument("--dry-run", action="store_true", help="Print what would happen, no DB writes")
    return p.parse_args()


def get_all_sites(session_factory) -> list[tuple[str, str]]:
    with session_factory() as session:
        rows = session.execute(
            select(OLIncident.SINAME, OLIncident.BUNAME)
            .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
            .distinct()
            .order_by(OLIncident.SINAME)
        ).all()
    return [(r.SINAME, r.BUNAME) for r in rows]


def upsert_predictions(rows: list[dict], session_factory, dry_run: bool) -> None:
    if dry_run or not rows:
        return
    sites = list({r["site"] for r in rows})
    with session_factory() as session:
        for site in sites:
            session.execute(
                text("DELETE FROM predictions_cache WHERE site = :s"),
                {"s": site},
            )
        for row in rows:
            session.add(PredictionsCache(**row))
        session.commit()


def insert_model_runs(runs: list[dict], session_factory, dry_run: bool) -> None:
    if dry_run or not runs:
        return
    with session_factory() as session:
        for run in runs:
            session.add(ModelRun(**run))
        session.commit()


def main() -> None:
    args = parse_args()
    sf = SSMSSession

    all_site_pairs = get_all_sites(sf)
    if args.sites:
        all_site_pairs = [(s, bu) for s, bu in all_site_pairs if s in args.sites]

    print(f"Training forecasters for {len(all_site_pairs)} site(s), n={args.quarters} quarters.")
    if args.dry_run:
        print("DRY RUN — no DB writes.")

    all_preds: list[dict] = []
    all_runs: list[dict] = []
    trained_at = datetime.now(timezone.utc).replace(tzinfo=None)  # DATETIME2 without tz
    success = 0
    skipped = 0
    errors = 0

    for site, bu in all_site_pairs:
        try:
            df = predict_next_n_quarters(site, n=args.quarters, session_factory=sf)

            if df.empty:
                skipped += 1
                continue

            # Cache predictions
            for _, row in df.iterrows():
                all_preds.append({
                    "site": site,
                    "business_unit": bu,
                    "target_quarter": row["target_quarter"],
                    "predicted_count": row["predicted_count"],
                    "lower_ci": row["lower_ci"],
                    "upper_ci": row["upper_ci"],
                    "model_name": row["model_name"],
                    "trained_at": trained_at,
                    "training_data_through": row.get("training_data_through"),
                    "confidence_band": row["confidence_band"],
                })

            # Log model metrics (use first row's metrics since they're the same across quarters)
            first = df.iloc[0]
            for model_key, name_prefix in [
                ("_prophet", "prophet"),
                ("_xgb", "xgboost"),
            ]:
                rmse = first.get(f"{model_key}_rmse")
                if rmse is None:
                    continue

                mape = first.get(f"{model_key}_mape")
                n = first.get(f"{model_key}_n", 0)

                # Compare with any sibling run for this site to set is_champion
                all_runs.append({
                    "model_name": name_prefix,
                    "site": site,
                    "trained_at": trained_at,
                    "training_rows": int(n) if n else None,
                    "holdout_rmse": rmse,
                    "holdout_mape": mape,
                    "is_champion": False,  # updated below
                    "notes": f"confidence_band={first['confidence_band']}",
                })

            # Set is_champion: lower RMSE wins
            site_runs = [r for r in all_runs if r["site"] == site]
            if site_runs:
                best = min(site_runs, key=lambda r: r["holdout_rmse"] or 9999)
                best["is_champion"] = True

            print(
                f"  {site:<32}  model={first['model_name']:<12}  "
                f"band={first['confidence_band']:<7}  "
                f"q={','.join(df['target_quarter'])}"
            )
            success += 1

        except Exception as exc:
            print(f"  ERROR {site}: {exc}", file=sys.stderr)
            errors += 1

    upsert_predictions(all_preds, sf, args.dry_run)
    insert_model_runs(all_runs, sf, args.dry_run)

    print(
        f"\nDone. success={success}  skipped={skipped}  errors={errors}  "
        f"predictions_rows={len(all_preds)}"
    )
    if args.dry_run:
        print("(No data written — dry run)")


if __name__ == "__main__":
    main()
