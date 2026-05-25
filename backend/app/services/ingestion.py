"""
CSV ingestion pipeline.

Entry point: ingest_csv(file_path, source, on_success) -> dict

Validates and summarises the CSV then writes a run record to SQL Server
(ingestion_runs via IngestionRunSSMS).  The raw incident rows are NOT written
to a relational table — OL_INCIDENTS is the authoritative incident store and is
populated externally.

Phase 2C (2026-05-25): Postgres incident writes (incidents_raw, incidents_clean,
incidents_quarantine) were removed when the Postgres stack was retired.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.core.ssms import SSMSSession
from app.models.ingestion import IngestionRunSSMS
from app.services.cleaner import clean_incidents


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_csv(
    file_path: str,
    source: str,
    session_factory=None,   # kept for signature compatibility — no longer used
    on_success=None,
) -> dict:
    """
    Load a CSV file through the ingestion pipeline and persist a run record
    to SQL Server.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the source CSV.
    source:
        Origin label stored on the run record (e.g. 'csv_upload', 'initial_load').
    session_factory:
        Accepted for backward-compatibility with existing callers; no longer used.
    on_success:
        Optional zero-argument callable invoked after a successful ingest.
        Typically ``background_tasks.add_task(run_full_pipeline, trigger='post_ingest')``.

    Returns
    -------
    Run-summary dict matching the ingestion_runs row.
    """
    batch_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    filename = Path(file_path).name

    # ── 1. Open the run record ────────────────────────────────────────────────
    with SSMSSession() as ssms:
        ssms.add(
            IngestionRunSSMS(
                batch_id=str(batch_id),
                source=source,
                filename=filename,
                status="running",
                started_at=started_at.replace(tzinfo=None),  # SQL Server: no tz
            )
        )
        ssms.commit()

    try:
        df_raw = pd.read_csv(file_path)
        rows_received = len(df_raw)

        df_clean, df_quarantine, report = clean_incidents(df_raw)
        rows_clean = len(df_clean)
        rows_quarantined = len(df_quarantine)

        # ── 2. Mark run as success ───────────────────────────────────────────
        finished_at = datetime.now(timezone.utc)
        with SSMSSession() as ssms:
            run = ssms.execute(
                select(IngestionRunSSMS).where(IngestionRunSSMS.batch_id == str(batch_id))
            ).scalar_one()
            run.rows_received = rows_received
            run.rows_clean = rows_clean
            run.rows_quarantined = rows_quarantined
            run.status = "success"
            run.finished_at = finished_at.replace(tzinfo=None)
            ssms.commit()

        # ── 3. Fire post-ingest hook (e.g. background pipeline run) ─────────
        if on_success is not None:
            on_success()

    except Exception as exc:
        with SSMSSession() as ssms:
            run = ssms.execute(
                select(IngestionRunSSMS).where(IngestionRunSSMS.batch_id == str(batch_id))
            ).scalar_one()
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            run.error_message = str(exc)
            ssms.commit()
        raise

    return {
        "batch_id": str(batch_id),
        "source": source,
        "filename": filename,
        "rows_received": rows_received,
        "rows_clean": rows_clean,
        "rows_quarantined": rows_quarantined,
        "rows_dropped_bad_year": report["rows_dropped_bad_year"],
        "rows_with_negative_lag": report["rows_with_negative_lag"],
        "status": "success",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
