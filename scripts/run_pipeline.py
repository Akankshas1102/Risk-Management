"""
CLI wrapper for run_full_pipeline.  Intended for cron/scheduler usage.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --trigger scheduled

Exit codes:
    0  — all steps succeeded
    1  — at least one step failed (partial or full failure)
    2  — pipeline could not start (unrecoverable error)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.orchestrator import run_full_pipeline


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the full ML pipeline.")
    p.add_argument(
        "--trigger",
        default="scheduled",
        choices=["manual", "scheduled", "post_ingest"],
        help="Trigger label stored in pipeline_runs (default: scheduled).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Starting pipeline (trigger={args.trigger}) ...")

    try:
        result = run_full_pipeline(trigger=args.trigger)
    except Exception as exc:
        print(f"FATAL: pipeline could not start — {exc}", file=sys.stderr)
        return 2

    # Print per-step summary
    for step_name, info in result.get("steps", {}).items():
        status_tag = "[OK]  " if info["status"] == "ok" else "[FAIL]"
        duration = f"{info.get('duration_s', 0):.1f}s"
        detail = (
            f"sites={info.get('sites_processed', '?')}  "
            f"rows={info.get('rows_written') or info.get('driver_rows_written', '?')}"
            if info["status"] == "ok"
            else info.get("traceback", "")[:120].replace("\n", " ")
        )
        print(f"  {status_tag} {step_name:<15} {duration:>6}   {detail}")

    overall = result.get("status", "failed")
    print(f"\nPipeline finished: status={overall}  total={result.get('total_duration_s', 0):.1f}s  run_id={result.get('run_id')}")

    return 0 if overall == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
