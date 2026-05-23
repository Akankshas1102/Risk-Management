#!/usr/bin/env python
"""
CLI entry point for the full ML pipeline.

Runs risk_scores → forecasters → backtest → drivers in sequence.

Usage
-----
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --trigger scheduled
    python scripts/run_pipeline.py --trigger manual --verbose

Exit codes
----------
    0  — all steps succeeded   (status == 'success')
    1  — one or more failed    (status == 'partial' or 'failed')
    2  — unhandled exception before any step ran

Cron example (cron fallback when no long-running server is available)
----------------------------------------------------------------------
    # /etc/cron.d/risk-pipeline   (runs daily at 02:00 UTC)
    0 2 * * * vedanta /path/venv/bin/python /path/scripts/run_pipeline.py \\
              --trigger scheduled >> /var/log/pipeline.log 2>&1
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── Import path setup ────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("run_pipeline")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the full ML risk-management pipeline.")
    p.add_argument(
        "--trigger",
        default="manual",
        choices=["manual", "scheduled", "post_ingest"],
        help="Trigger label stored in pipeline_runs (default: manual).",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full per-step counts and tracebacks.",
    )
    return p.parse_args()


def _step_detail(step: dict, verbose: bool) -> list[str]:
    """Return human-readable lines for one step result."""
    lines = []
    for k, v in step.items():
        if k in ("status", "duration_s", "traceback"):
            continue
        lines.append(f"       {k}: {v}")
    if step["status"] != "ok" and "traceback" in step:
        tb_lines = step["traceback"].strip().split("\n")
        lines.append("       --- traceback (last 5 lines) ---")
        for ln in tb_lines[-5:]:
            lines.append(f"       {ln}")
    elif verbose:
        pass  # counts already printed above
    return lines


def main() -> int:
    args = parse_args()

    log.info("=== ML Pipeline starting (trigger=%s) ===", args.trigger)

    try:
        from app.services.orchestrator import run_full_pipeline  # noqa
    except ImportError as exc:
        log.error("Import failed — is backend/ in sys.path? %s", exc)
        return 2

    try:
        result = run_full_pipeline(trigger=args.trigger)
    except Exception as exc:
        log.exception("Unhandled exception in run_full_pipeline: %s", exc)
        return 2

    # ── Print summary ─────────────────────────────────────────────────────
    print()
    print("=" * 64)
    print(f"  run_id    : {result['run_id']}")
    print(f"  trigger   : {result['trigger']}")
    print(f"  status    : {result['status'].upper()}")
    print(f"  duration  : {result['total_duration_s']:.1f}s")
    print(f"  started   : {result['started_at']}")
    print(f"  finished  : {result['finished_at']}")
    print()

    for step_name, step in result["steps"].items():
        ok = step["status"] == "ok"
        icon = "[OK]" if ok else "[!!]"
        duration = step.get("duration_s", 0)
        print(f"  {icon}  {step_name:<16}  {step['status']:<8}  {duration:>6.1f}s")

        if args.verbose or not ok:
            for line in _step_detail(step, args.verbose):
                print(line)

    print("=" * 64)
    print()

    overall = result["status"]
    if overall == "success":
        log.info("Pipeline succeeded (run_id=%s)", result["run_id"])
        return 0
    else:
        log.error(
            "Pipeline finished with status=%s (run_id=%s)",
            overall, result["run_id"],
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
