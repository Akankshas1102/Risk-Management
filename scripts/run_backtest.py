"""
CLI: walk-forward backtest for all sites' champion models.

Calls backend/app/ml/backtest.py::run_all_backtests() and writes results
into backtest_results (site, month, actual, predicted, abs_pct_error, model_name).

Usage
-----
    python scripts/run_backtest.py                        # all sites, 6-month window
    python scripts/run_backtest.py --months 12            # 12-month holdout window
    python scripts/run_backtest.py --sites "BALCO" "RDC"  # specific sites only
    python scripts/run_backtest.py --dry-run              # compute but don't write
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s %(message)s",
)

from app.ml.backtest import DEFAULT_BACKTEST_MONTHS, run_all_backtests
from app.ml.features import get_global_max_date


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Walk-forward backtest for all sites.")
    p.add_argument("--sites", nargs="*", help="Specific sites to backtest (default: all)")
    p.add_argument(
        "--months", type=int, default=DEFAULT_BACKTEST_MONTHS,
        help=f"Holdout window in months (default: {DEFAULT_BACKTEST_MONTHS})",
    )
    p.add_argument("--dry-run", action="store_true", help="Compute but do not write to DB")
    p.add_argument("-v", "--verbose", action="store_true", help="Show per-site progress")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger("app.ml.backtest").setLevel(logging.DEBUG)

    global_max = get_global_max_date()
    print(f"OL_INCIDENTS global max date: {global_max.date()}")
    print(f"Backtest window: {args.months} months holdout")
    if args.dry_run:
        print("DRY RUN — no DB writes.")
    print()

    site_pairs = None
    if args.sites:
        # Build pairs from the requested sites (resolve BU from OL_INCIDENTS)
        from sqlalchemy import select
        from app.core.ssms import SSMSSession
        from app.models.ol_incidents import OLIncident
        with SSMSSession() as s:
            rows = s.execute(
                select(OLIncident.SINAME, OLIncident.BUNAME)
                .where(
                    OLIncident.YEAR >= "2020",
                    OLIncident.SINAME.isnot(None),
                    OLIncident.SINAME.in_(args.sites),
                )
                .distinct()
                .order_by(OLIncident.SINAME)
            ).all()
        site_pairs = [(r.SINAME, r.BUNAME) for r in rows]
        if not site_pairs:
            print(f"ERROR: none of the requested sites found in OL_INCIDENTS: {args.sites}")
            sys.exit(1)

    print(f"Running backtest for {'all' if site_pairs is None else len(site_pairs)} site(s)...")

    result = run_all_backtests(
        site_pairs=site_pairs,
        n_months=args.months,
        dry_run=args.dry_run,
    )

    print(
        f"\nDone.  ok={result['ok']}  skipped={result['skipped']}  "
        f"errors={result['errors']}  rows={result['total_rows']}"
    )
    if args.dry_run:
        print("(No data written — dry run)")
    elif result['total_rows'] > 0:
        print(f"Wrote {result['total_rows']} rows to backtest_results.")


if __name__ == "__main__":
    main()
