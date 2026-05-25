"""SQL Server ORM model for ingestion_runs.

Tracks every CSV upload attempt (batch_id, status, row counts, timestamps).
This is the SQL Server mirror of what was previously stored in Postgres;
it is the sole store for ingestion history going forward.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from app.models.ol_incidents import SSMSBase


class IngestionRunSSMS(SSMSBase):
    """One row per CSV upload attempt."""

    __tablename__ = "ingestion_runs"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id        = Column(String(36),  nullable=False, unique=True)  # UUID as string
    source          = Column(String(50),  nullable=False)               # 'csv_upload' | 'initial_load'
    filename        = Column(String(500))
    rows_received   = Column(Integer)
    rows_clean      = Column(Integer)
    rows_quarantined= Column(Integer)
    status          = Column(String(20),  nullable=False)               # running / success / failed
    started_at      = Column(DateTime)                                  # UTC, no tz
    finished_at     = Column(DateTime)
    error_message   = Column(Text)
