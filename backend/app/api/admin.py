"""
Admin API: pipeline management and data freshness.

POST /api/admin/retrain        — kick off a manual full pipeline run
GET  /api/admin/runs           — last 20 pipeline_runs rows
GET  /api/admin/freshness      — snapshot of data currency
"""

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.ssms import get_ssms_db
from app.models.pipeline import PipelineRun
from app.models.predictions import PredictionsCache
from app.services.orchestrator import create_queued_run, run_full_pipeline

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# POST /api/admin/retrain
# ---------------------------------------------------------------------------

@router.post("/retrain")
async def retrain(background_tasks: BackgroundTasks, db: Session = Depends(get_ssms_db)):
    """
    Trigger a full pipeline run (risk scores → forecasters → drivers).
    Returns immediately with the pipeline_run_id; check /api/admin/runs for status.
    """
    run_id = create_queued_run("manual")
    background_tasks.add_task(run_full_pipeline, trigger="manual", run_id=run_id)
    return {"pipeline_run_id": run_id, "status": "queued"}


# ---------------------------------------------------------------------------
# GET /api/admin/runs
# ---------------------------------------------------------------------------

@router.get("/runs")
def list_runs(db: Session = Depends(get_ssms_db)):
    """Return the last 20 pipeline runs with per-step outcomes."""
    rows = db.execute(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(20)
    ).scalars().all()

    results = []
    for run in rows:
        results.append({
            "id": run.id,
            "trigger": run.trigger,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "steps": run.steps,
            "error_summary": run.error_summary,
        })
    return results


# ---------------------------------------------------------------------------
# GET /api/admin/freshness
# ---------------------------------------------------------------------------

@router.get("/freshness")
def data_freshness(db: Session = Depends(get_ssms_db)):
    """
    Snapshot of data currency across the pipeline.

    Fields
    ------
    last_pipeline_run_at    : most recent finished pipeline_runs row
    pipeline_run_status     : its status
    latest_data_date        : max OCCUREDDATE in OL_INCIDENTS
    latest_predicted_quarter: most recently created prediction target
    """
    # Last pipeline run
    run_row = db.execute(
        select(PipelineRun.finished_at, PipelineRun.status)
        .where(PipelineRun.finished_at.isnot(None))
        .order_by(PipelineRun.finished_at.desc())
        .limit(1)
    ).first()

    # Latest incident date (OCCUREDDATE is varchar YYYY-MM-DD; MAX works on ISO strings)
    data_date_row = db.execute(
        text("""
            SELECT MAX(OCCUREDDATE) AS latest_date
            FROM OL_INCIDENTS
            WHERE TRY_CAST(YEAR AS INT) > 2000
              AND LEN(OCCUREDDATE) = 10
        """)
    ).first()

    # Latest predicted quarter (sort by trained_at as proxy for recency)
    pred_row = db.execute(
        select(PredictionsCache.target_quarter, PredictionsCache.trained_at)
        .order_by(PredictionsCache.trained_at.desc())
        .limit(1)
    ).first()

    return {
        "last_pipeline_run_at": (
            run_row.finished_at.isoformat() if run_row and run_row.finished_at else None
        ),
        "pipeline_run_status": run_row.status if run_row else None,
        "latest_data_date": data_date_row.latest_date if data_date_row else None,
        "latest_predicted_quarter": pred_row.target_quarter if pred_row else None,
        "last_ingest_at": None,  # N/A — OL_INCIDENTS is populated externally
    }
