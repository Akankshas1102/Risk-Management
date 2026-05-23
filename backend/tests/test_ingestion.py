"""Integration tests for ingest_csv."""

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from app.services.ingestion import ingest_csv


def test_ingest_csv_row_counts(sample_csv, test_session_factory, test_engine):
    """
    10-row CSV with 1 bad-year row and 1 bad-date row should produce:
    - 10 rows in incidents_raw (raw archive is append-only, keeps everything)
    - 8 rows in incidents_clean
    - 1 row in incidents_quarantine
    - 1 ingestion_run with status=success
    """
    summary = ingest_csv(str(sample_csv), source="test", session_factory=test_session_factory)

    assert summary["rows_received"] == 10
    assert summary["rows_clean"] == 8
    assert summary["rows_quarantined"] == 1
    assert summary["rows_dropped_bad_year"] == 1
    assert summary["status"] == "success"
    assert UUID(summary["batch_id"])  # valid UUID

    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM incidents_raw")).scalar() == 10
        assert conn.execute(text("SELECT COUNT(*) FROM incidents_clean")).scalar() == 8
        assert conn.execute(text("SELECT COUNT(*) FROM incidents_quarantine")).scalar() == 1
        run_status = conn.execute(
            text("SELECT status FROM ingestion_runs WHERE batch_id = :bid"),
            {"bid": summary["batch_id"]},
        ).scalar()
        assert run_status == "success"


def test_ingest_csv_idempotent(sample_csv, test_session_factory, test_engine):
    """
    Re-ingesting the same file should not duplicate incidents_clean rows
    (upsert on incrowid), but incidents_raw grows (audit log).
    """
    ingest_csv(str(sample_csv), source="test", session_factory=test_session_factory)
    ingest_csv(str(sample_csv), source="test", session_factory=test_session_factory)

    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM incidents_raw")).scalar() == 20
        assert conn.execute(text("SELECT COUNT(*) FROM incidents_clean")).scalar() == 8
        assert conn.execute(text("SELECT COUNT(*) FROM ingestion_runs")).scalar() == 2


def test_ingest_csv_missing_file(test_session_factory):
    """A missing file should raise, and the run record should be marked failed."""
    with pytest.raises(Exception):
        ingest_csv("/nonexistent/path.csv", source="test", session_factory=test_session_factory)
