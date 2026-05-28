"""
Pipeline orchestrator.

run_full_pipeline(trigger)
    Executes all four ML steps in order:
        1. risk_scores    — composite score per site per quarter
        2. forecasters    — n-quarter-ahead predictions
        3. backtest       — walk-forward 6-month holdout evaluation
        4. drivers        — SHAP attribution + rules-based recommendations

    Each step is wrapped in a timed try/except so one failure never blocks
    the others.  Full tracebacks are captured and stored in
    pipeline_runs.steps_run JSON.

Service functions for the admin API
-----------------------------------
trigger_manual_retrain(background_tasks=None) -> dict
    Queue a manual run (status="queued") and start it asynchronously.
    Returns {run_id, status}.

get_recent_runs(limit=10) -> list[dict]
    Return the last `limit` pipeline_runs rows, newest first.

get_freshness() -> dict
    Single snapshot of data currency across the whole pipeline.
    Keys: last_ingest_at, last_pipeline_run_at, latest_incident_date,
          latest_predicted_quarter, n_sites_with_predictions,
          sites_missing_predictions.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models.pipeline import PipelineRun
from app.models.predictions import PredictionsCache
from app.models.ol_incidents import OLIncident
from app.services.pipeline_steps import (
    step_backtest,
    step_drivers,
    step_forecasters,
    step_risk_scores,
)

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
# Core pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(
    trigger: str,
    run_id: Optional[int] = None,
    session_factory=None,
) -> dict:
    """
    Execute all four ML pipeline steps in order:
      1. risk_scores   — composite score per site per quarter
      2. forecasters   — n-quarter-ahead predictions
      3. backtest      — walk-forward 6-month holdout evaluation
      4. drivers       — SHAP attribution + recommendations

    A failure in any step is logged and stored; subsequent steps still run
    (risk_scores failure is the only one that might make forecasters less
    meaningful, but we run it anyway to surface the error clearly).

    Parameters
    ----------
    trigger : 'manual' | 'scheduled' | 'post_ingest'
    run_id  : If provided, updates an existing pipeline_runs row instead of
              creating one.  Pass the value returned by create_queued_run().
    session_factory : Override SessionLocal (for tests).

    Returns
    -------
    dict with run_id, status, steps summary, started_at, finished_at,
    total_duration_s.
    """
    sf = session_factory or SessionLocal
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

    # forecasters reads OL_INCIDENTS directly; not blocked by risk_scores result
    steps["forecasters"] = _run_step("forecasters", step_forecasters, sf)

    # backtest runs after forecasters so champion model_runs rows are current
    steps["backtest"] = _run_step("backtest", step_backtest, sf)

    # drivers reads OL_INCIDENTS directly; runs last so recommendations can
    # reference the freshest sparkline / QoQ data
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
        f"{name}: {info.get('traceback', '')[:300]}"
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
    """
    Insert a pipeline_runs row with status='queued' and return its id.
    Used when you want to reserve a run_id before kicking off the background work.
    """
    sf = session_factory or SessionLocal
    run = PipelineRun(trigger=trigger, status="queued", started_at=_now())
    with sf() as session:
        session.add(run)
        session.flush()
        run_id = run.id
        session.commit()
    return run_id


# ---------------------------------------------------------------------------
# Service functions — call these from the admin API
# ---------------------------------------------------------------------------

def trigger_manual_retrain(background_tasks=None) -> dict:
    """
    Queue a manual full-pipeline run and start it asynchronously.

    Parameters
    ----------
    background_tasks : fastapi.BackgroundTasks (optional).
        If provided, the run is enqueued via FastAPI's task runner.
        If omitted (e.g. called from a script), a daemon thread is used.

    Returns
    -------
    dict: ``{"run_id": <int>, "status": "queued"}``

    Example (admin endpoint)
    ------------------------
    ::

        @router.post("/admin/retrain")
        async def retrain(bg: BackgroundTasks):
            return trigger_manual_retrain(background_tasks=bg)
    """
    run_id = create_queued_run("manual")

    if background_tasks is not None:
        background_tasks.add_task(run_full_pipeline, trigger="manual", run_id=run_id)
    else:
        t = threading.Thread(
            target=run_full_pipeline,
            kwargs={"trigger": "manual", "run_id": run_id},
            daemon=True,
            name=f"pipeline-manual-{run_id}",
        )
        t.start()

    log.info("Manual retrain queued — run_id=%s", run_id)
    return {"run_id": run_id, "status": "queued"}


def get_recent_runs(limit: int = 10, session_factory=None) -> list[dict]:
    """
    Return the most recent pipeline_runs rows, newest first.

    Parameters
    ----------
    limit : Number of rows to return (default 10, max sensibly ~50).

    Returns
    -------
    list of dicts with keys:
        id, trigger, status, started_at, finished_at,
        total_duration_s, steps, error_summary.

    Example (admin endpoint)
    ------------------------
    ::

        @router.get("/admin/runs")
        def list_runs():
            return get_recent_runs(limit=20)
    """
    sf = session_factory or SessionLocal
    with sf() as session:
        rows = session.execute(
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
        ).scalars().all()

    result = []
    for run in rows:
        steps = run.steps  # decoded via @property
        total_s = (
            round(sum(s.get("duration_s", 0) for s in steps.values()), 1)
            if steps else None
        )
        result.append({
            "id": run.id,
            "trigger": run.trigger,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "total_duration_s": total_s,
            "steps": steps,
            "error_summary": run.error_summary,
        })
    return result


def get_freshness(session_factory=None) -> dict:
    """
    Single snapshot of data currency across the whole pipeline.

    All queries hit the same PostgreSQL database (vedanta_risk):
    pipeline_runs, ol_incidents, predictions_cache, ingestion_runs.

    Returns
    -------
    dict with keys:
        last_ingest_at          (str ISO-8601 | None)  — last successful CSV upload
        last_pipeline_run_at    (str ISO-8601 | None)  — last finished pipeline run
        pipeline_run_status     (str | None)           — its status
        latest_incident_date    (str | None)           — MAX(OCCUREDDATE) in ol_incidents
        latest_predicted_quarter (str | None)          — most recently trained prediction target
        n_sites_with_predictions (int)                 — distinct sites in predictions_cache
        sites_missing_predictions (list[str])          — sites in ol_incidents with no predictions

    Example (admin endpoint)
    ------------------------
    ::

        @router.get("/admin/freshness")
        def freshness():
            return get_freshness()
    """
    sf = session_factory or SessionLocal
    result: dict[str, Any] = {}

    # ── Database queries ──────────────────────────────────────────────────
    with sf() as session:
        # Last finished pipeline run
        run_row = session.execute(
            select(PipelineRun.finished_at, PipelineRun.status)
            .where(PipelineRun.finished_at.isnot(None))
            .order_by(PipelineRun.finished_at.desc())
            .limit(1)
        ).first()

        # Latest incident occurrence date (varchar ISO — MAX is lexicographically safe)
        data_date_row = session.execute(
            text("""
                SELECT MAX(occureddate) AS latest_date
                FROM ol_incidents
                WHERE CAST(NULLIF(year, '') AS INTEGER) > 2000
                  AND LENGTH(occureddate) = 10
            """)
        ).first()

        # Latest predicted quarter and count of sites with predictions
        pred_stats = session.execute(
            text("""
                SELECT
                    MAX(trained_at) AS last_trained,
                    COUNT(DISTINCT site) AS n_sites
                FROM predictions_cache
            """)
        ).first()

        latest_pred_q_row = session.execute(
            select(PredictionsCache.target_quarter, PredictionsCache.trained_at)
            .order_by(PredictionsCache.trained_at.desc())
            .limit(1)
        ).first()

        # All sites in OL_INCIDENTS (year ≥ 2020, SINAME not null)
        all_sites_rows = session.execute(
            select(OLIncident.SINAME)
            .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
            .distinct()
        ).all()
        all_sites = {r[0] for r in all_sites_rows}

        # Sites that do have predictions
        pred_site_rows = session.execute(
            select(PredictionsCache.site).distinct()
        ).all()
        sites_with_preds = {r[0] for r in pred_site_rows}

    sites_missing = sorted(all_sites - sites_with_preds)

    result["last_pipeline_run_at"] = (
        run_row.finished_at.isoformat() if run_row and run_row.finished_at else None
    )
    result["pipeline_run_status"] = run_row.status if run_row else None
    result["latest_incident_date"] = (
        data_date_row.latest_date if data_date_row else None
    )
    result["latest_predicted_quarter"] = (
        latest_pred_q_row.target_quarter if latest_pred_q_row else None
    )
    result["n_sites_with_predictions"] = int(pred_stats.n_sites) if pred_stats else 0
    result["sites_missing_predictions"] = sites_missing

    # ── Last successful CSV ingest ────────────────────────────────────────
    from app.models.ingestion import IngestionRun  # noqa: PLC0415

    result["last_ingest_at"] = None
    try:
        with SessionLocal() as session:
            ingest_row = session.execute(
                select(IngestionRun.finished_at)
                .where(IngestionRun.status == "success")
                .order_by(IngestionRun.finished_at.desc())
                .limit(1)
            ).first()

        if ingest_row and ingest_row.finished_at:
            result["last_ingest_at"] = ingest_row.finished_at.isoformat()
    except Exception:
        log.debug("Could not query ingestion_runs for freshness", exc_info=True)

    return result
