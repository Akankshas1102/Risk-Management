import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from app.services.ingestion import ingest_csv
from app.services.orchestrator import run_full_pipeline

router = APIRouter(prefix="/api", tags=["ingestion"])


@router.post("/ingest")
async def ingest_upload(file: UploadFile, background_tasks: BackgroundTasks):
    """
    Accept a multipart CSV upload, run the full ingestion pipeline, and return
    the run summary.  Re-uploading the same data is safe (upsert on incrowid).
    After a successful ingest, the ML pipeline (risk scores, forecasters, drivers)
    is automatically triggered as a background task.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    with tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, dir=tempfile.gettempdir()
    ) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        summary = ingest_csv(
            tmp_path,
            source="csv_upload",
            on_success=lambda: background_tasks.add_task(
                run_full_pipeline, trigger="post_ingest"
            ),
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return summary
