"""
CLI: compute risk scores for all complete quarters and persist to DB.

Usage:
    python scripts/compute_risk_scores.py
    python scripts/compute_risk_scores.py --quarters 2024-Q1 2024-Q2
    python scripts/compute_risk_scores.py --include-partial
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.risk_score import compute_risk_scores, persist_risk_scores


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute and persist risk scores.")
    p.add_argument(
        "--quarters",
        nargs="*",
        metavar="YYYY-Qn",
        help="Specific quarters to compute (default: all complete quarters).",
    )
    p.add_argument(
        "--include-partial",
        action="store_true",
        help="Also compute the current (incomplete) quarter.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("Computing risk scores...")
    df = compute_risk_scores(
        quarters=args.quarters or None,
        include_partial=args.include_partial,
    )

    if df.empty:
        print("No complete quarters found in incidents_clean. Run ingestion first.")
        sys.exit(0)

    print(f"Computed scores for {df['quarter'].nunique()} quarter(s), {df['site'].nunique()} site(s).")
    print(f"Risk level distribution:\n{df['risk_level'].value_counts().to_string()}")

    print("Persisting to database...")
    persist_risk_scores(df)
    print(f"Done. {len(df)} rows upserted into risk_scores.")


if __name__ == "__main__":
    main()
