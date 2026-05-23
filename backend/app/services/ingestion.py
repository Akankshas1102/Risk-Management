"""
CSV ingestion pipeline.

Entry point: ingest_csv(file_path, source) -> dict
Writes to four tables: ingestion_runs, incidents_raw, incidents_clean, incidents_quarantine.
All raw + clean + quarantine writes happen in a single transaction; the run-status
updates (start and finish) are committed in their own short transactions so they
remain visible even if the main transaction rolls back.
"""

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from app.core.database import SessionLocal
from app.models.incident import IncidentClean, IncidentQuarantine, IncidentRaw, IngestionRun
from app.services.cleaner import clean_incidents


# ---------------------------------------------------------------------------
# Record-building helpers
# ---------------------------------------------------------------------------

def _scalar(v: Any) -> Any:
    """Convert a pandas/numpy scalar to a plain Python value; NaN/NaT → None."""
    if v is None:
        return None
    if v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if np.isnan(v) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _raw_records(df: pd.DataFrame, batch_id: uuid.UUID, ingested_at: datetime) -> list[dict]:
    """Convert raw CSV DataFrame to DB-ready dicts (all values as strings)."""
    df_lower = df.rename(columns=str.lower)
    records = []
    for rec in df_lower.to_dict(orient="records"):
        row: dict = {"batch_id": batch_id, "ingested_at": ingested_at}
        for k, v in rec.items():
            s = _scalar(v)
            row[k] = str(s) if s is not None else None
        records.append(row)
    return records


def _clean_records(df: pd.DataFrame, batch_id: uuid.UUID, cleaned_at: datetime) -> list[dict]:
    """Convert clean DataFrame to DB-ready dicts, renaming incrow_id → incrowid."""
    records = []
    for rec in df.to_dict(orient="records"):
        row: dict = {"batch_id": batch_id, "cleaned_at": cleaned_at}
        for k, v in rec.items():
            db_key = "incrowid" if k == "incrow_id" else k
            row[db_key] = _scalar(v)
        records.append(row)
    return records


def _quarantine_records(
    df: pd.DataFrame, batch_id: uuid.UUID, reason: str
) -> list[dict]:
    """Serialise quarantine rows as JSON blobs (dates become ISO strings)."""
    records = []
    for rec in df.to_dict(orient="records"):
        row_data: dict = {}
        for k, v in rec.items():
            s = _scalar(v)
            if hasattr(s, "isoformat"):
                row_data[k] = s.isoformat()
            else:
                row_data[k] = s
        records.append({"batch_id": batch_id, "row_data": row_data, "reason": reason})
    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_csv(
    file_path: str,
    source: str,
    session_factory: sessionmaker | None = None,
    on_success=None,
) -> dict:
    """
    Load a CSV file through the full ingestion pipeline and persist to Postgres.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the source CSV.
    source:
        Origin label stored on the run record (e.g. 'csv_upload', 'initial_load').
    session_factory:
        Override the default SessionLocal — used in tests to inject a test DB session.
    on_success:
        Optional zero-argument callable invoked after a successful ingest.
        Typically ``background_tasks.add_task(run_full_pipeline, trigger='post_ingest')``.

    Returns
    -------
    Run-summary dict matching the ingestion_runs row.
        Origin label stored on the run record (e.g. 'csv_upload', 'initial_load').
    session_factory:
        Override the default SessionLocal — used in tests to inject a test DB session.

    Returns
    -------
    Run-summary dict matching the ingestion_runs row.
    """
    sf = session_factory or SessionLocal
    batch_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    filename = Path(file_path).name

    # ── 1. Open the run record (committed immediately, visible to observers) ─
    with sf() as session:
        session.add(
            IngestionRun(
                batch_id=batch_id,
                source=source,
                filename=filename,
                status="running",
                started_at=started_at,
            )
        )
        session.commit()

    try:
        df_raw = pd.read_csv(file_path)
        rows_received = len(df_raw)

        df_clean, df_quarantine, report = clean_incidents(df_raw)
        rows_clean = len(df_clean)
        rows_quarantined = len(df_quarantine)
        cleaned_at = datetime.now(timezone.utc)

        # ── 2. Single transaction: raw archive + clean upsert + quarantine ───
        with sf() as session:
            with session.begin():
                # Insert raw rows (append-only audit log)
                raw_recs = _raw_records(df_raw, batch_id, started_at)
                session.execute(IncidentRaw.__table__.insert(), raw_recs)

                # Upsert clean rows (idempotent on incrowid)
                if rows_clean:
                    clean_recs = _clean_records(df_clean, batch_id, cleaned_at)
                    stmt = pg_insert(IncidentClean.__table__).values(clean_recs)
                    update_cols = {
                        c: stmt.excluded[c]
                        for c in clean_recs[0]
                        if c != "incrowid"
                    }
                    session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=["incrowid"],
                            set_=update_cols,
                        )
                    )

                # Insert quarantine rows
                if rows_quarantined:
                    q_recs = _quarantine_records(df_quarantine, batch_id, "bad_date")
                    session.execute(IncidentQuarantine.__table__.insert(), q_recs)

        # ── 3. Mark run as success ───────────────────────────────────────────
        finished_at = datetime.now(timezone.utc)
        with sf() as session:
            run = session.get(IngestionRun, batch_id)
            run.rows_received = rows_received
            run.rows_clean = rows_clean
            run.rows_quarantined = rows_quarantined
            run.status = "success"
            run.finished_at = finished_at
            session.commit()

        # ── 4. Fire post-ingest hook (e.g. background pipeline run) ─────────
        if on_success is not None:
            on_success()

    except Exception as exc:
        with sf() as session:
            run = session.get(IngestionRun, batch_id)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            session.commit()
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
