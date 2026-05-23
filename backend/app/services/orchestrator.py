"""
Pipeline orchestrator.

run_full_pipeline(trigger) runs all three ML steps in sequence.
Each step is wrapped in a timed try/except so one failure never blocks the others.
Full tracebacks are captured and stored in pipeline_runs.steps_run JSON.
"""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.ssms import SSMSSession
from app.models.pipeline import PipelineRun
from app.services.pipeline_steps import step_drivers, step_forecasters, step_risk_scores

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_step(name: str, fn: Callable, *args: Any, **kwargs: Any) -> dict:
    """
    Execute a pipeline step function, capturing timing and any exception.
    Always returns a dict — never raises.
    """
    log.info("Pipeline step '%s' starting", name)
    t0 = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        elapsed = round(time.monotonic() - t0, 1)
        log.info("Pipeline step '%s' finished in %.1fs — %s", name, elapsed, result)
        return {"status": "ok", "duration_s": elapsed, **result}
    except Exception:
        elapsed = round(time.monotonic() - t0, 1)
        tb = traceback.format_exc()
        log.error("Pipeline step '%s' failed after %.1fs:\n%s", name, elapsed, tb)
        return {"status": "error", "duration_s": elapsed, "traceback": tb}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_full_pipeline(
    trigger: str,
    run_id: int | None = None,
    session_factory=None,
) -> dict:
    """
    Execute all three ML pipeline steps in order:
      1. risk_scores   — composite score per site per quarter
      2. forecasters   — n-quarter ahead predictions
      3. drivers       — SHAP attribution + recommendations

    A failure in any step is logged and stored; subsequent steps still run.

    Parameters
    ----------
    trigger : 'manual' | 'scheduled' | 'post_ingest'
    run_id  : If provided, updates an existing pipeline_runs row; otherwise creates one.
    session_factory : Override SSMSSession (for tests).

    Returns
    -------
    dict with run_id, status, steps summary, started_at, finished_at.
    """
    sf = session_factory or SSMSSession
    started_at = _now()

    # ── Create / update the run record ────────────────────────────────────
    if run_id is None:
        run = PipelineRun(trigger=trigger, status="running", started_at=started_at)
        with sf() as session:
            session.add(run)
            session.flush()
            run_id = run.id
            session.commit()
    else:
        with sf() as session:
            run = session.get(PipelineRun, run_id)
            run.status = "running"
            run.started_at = started_at
            session.commit()

    # ── Run steps ─────────────────────────────────────────────────────────
    steps: dict[str, dict] = {}

    steps["risk_scores"] = _run_step("risk_scores", step_risk_scores, sf)

    # Forecasters and drivers can run independently; a forecaster failure
    # does not block driver computation since drivers read raw OL_INCIDENTS.
    steps["forecasters"] = _run_step("forecasters", step_forecasters, sf)
    steps["drivers"] = _run_step("drivers", step_drivers, sf)

    # ── Determine overall status ───────────────────────────────────────────
    statuses = [s["status"] for s in steps.values()]
    if all(s == "ok" for s in statuses):
        overall = "success"
    elif all(s == "error" for s in statuses):
        overall = "failed"
    else:
        overall = "partial"

    error_fragments = [
        f"{name}: {info.get('traceback', '')[:200]}"
        for name, info in steps.items()
        if info["status"] == "error"
    ]
    error_summary = " | ".join(error_fragments) or None
    finished_at = _now()

    # ── Persist final state ───────────────────────────────────────────────
    with sf() as session:
        run = session.get(PipelineRun, run_id)
        run.status = overall
        run.finished_at = finished_at
        run.steps = steps          # uses the @steps.setter to JSON-serialize
        run.error_summary = error_summary
        session.commit()

    total_s = round(sum(s.get("duration_s", 0) for s in steps.values()), 1)
    log.info("Pipeline '%s' finished — status=%s in %.1fs", trigger, overall, total_s)

    return {
        "run_id": run_id,
        "trigger": trigger,
        "status": overall,
        "steps": steps,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "total_duration_s": total_s,
    }


def create_queued_run(trigger: str, session_factory=None) -> int:
    """Insert a pipeline_runs row with status='queued' and return its id."""
    sf = session_factory or SSMSSession
    run = PipelineRun(trigger=trigger, status="queued", started_at=_now())
    with sf() as session:
        session.add(run)
        session.flush()
        run_id = run.id
        session.commit()
    return run_id
