"""
One-time CLI: load all raw CSVs through the production ingestion pipeline.

Usage (from repo root):
    python scripts/initial_load.py
    python scripts/initial_load.py --raw-dir data/raw
    python scripts/initial_load.py --raw-dir data/raw --pattern "OL_INCIDENTS_*.csv"

Re-running is safe — ingestion is idempotent (upsert on incrowid).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.ingestion import ingest_csv

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_PATTERN = "*.csv"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load raw CSVs into the database.")
    p.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    p.add_argument("--pattern", default=DEFAULT_PATTERN)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    csv_files = sorted(args.raw_dir.glob(args.pattern))

    if not csv_files:
        print(f"No files matched {args.raw_dir / args.pattern}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(csv_files)} file(s) in {args.raw_dir}\n")

    total_clean = 0
    total_quarantined = 0
    errors = []

    for csv_path in csv_files:
        print(f"Ingesting {csv_path.name} ...")
        try:
            summary = ingest_csv(str(csv_path), source="initial_load")
            total_clean += summary["rows_clean"]
            total_quarantined += summary["rows_quarantined"]
            print(
                f"  received={summary['rows_received']}  "
                f"clean={summary['rows_clean']}  "
                f"quarantined={summary['rows_quarantined']}  "
                f"batch={summary['batch_id']}"
            )
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            errors.append((csv_path.name, str(exc)))

    print(f"\nDone. Total clean={total_clean}  quarantined={total_quarantined}")
    if errors:
        print(f"\nFailed files ({len(errors)}):")
        for name, msg in errors:
            print(f"  {name}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
