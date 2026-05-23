"""
CLI: load raw CSV → clean → save parquet.

Usage:
    python scripts/run_cleaning.py
    python scripts/run_cleaning.py --raw data/raw/OL_INCIDENTS_20260518_142042.csv
    python scripts/run_cleaning.py --raw <path> --out data/processed/incidents_clean.parquet
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.cleaner import clean_incidents

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_RAW = REPO_ROOT / "data" / "raw" / "OL_INCIDENTS_20260518_142042.csv"
DEFAULT_OUT = REPO_ROOT / "data" / "processed" / "incidents_clean.parquet"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clean raw incident CSV and write parquet.")
    p.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="Path to raw CSV")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output parquet path")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.raw.exists():
        print(f"ERROR: raw file not found: {args.raw}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading  {args.raw}")
    df_raw = pd.read_csv(args.raw)
    print(f"  {len(df_raw):,} rows, {df_raw.shape[1]} columns")

    print("Cleaning ...")
    df_clean, _quarantine, report = clean_incidents(df_raw)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(args.out, index=False)
    print(f"Saved    {args.out}  ({len(df_clean):,} rows)")

    print("\n--- Cleaning report ---")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
