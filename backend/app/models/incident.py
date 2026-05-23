import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    batch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False)
    filename = Column(Text)
    rows_received = Column(Integer)
    rows_clean = Column(Integer)
    rows_quarantined = Column(Integer)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    error_message = Column(Text)


class IncidentRaw(Base):
    """One row per source CSV row — all values stored as Text for faithful archival."""

    __tablename__ = "incidents_raw"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    # Original CSV columns (lowercased)
    incrowid = Column(Text)
    vname = Column(Text)
    buname = Column(Text)
    siname = Column(Text)
    priority = Column(Text)
    status = Column(Text)
    incidenttypename = Column(Text)
    incidentcatname = Column(Text)
    incidenttitle = Column(Text)
    incidentdetails = Column(Text)
    occureddate = Column(Text)
    occuredtime = Column(Text)
    reporteddate = Column(Text)
    reportedtime = Column(Text)
    lastupdateddate = Column(Text)
    lastupdatedtime = Column(Text)
    month = Column(Text)
    quarter = Column(Text)
    year = Column(Text)
    lname = Column(Text)
    levelname = Column(Text)
    zname = Column(Text)
    incidentid = Column(Text)
    reportedby = Column(Text)
    incidenttypename_display = Column(Text)
    incidentcatname_display = Column(Text)
    incidentcount = Column(Text)
    monthname = Column(Text)
    vcode = Column(Text)
    bucode = Column(Text)
    sicode = Column(Text)
    dsrdate = Column(Text)


class IncidentClean(Base):
    __tablename__ = "incidents_clean"

    incrowid = Column(Integer, primary_key=True)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    cleaned_at = Column(DateTime(timezone=True), server_default=func.now())

    incident_id = Column(Integer)
    vname = Column(Text)
    vcode = Column(Text)
    buname = Column(Text)
    bucode = Column(Text)
    site_name = Column(Text)
    sicode = Column(Text)
    status = Column(Text)
    incident_type = Column(Text)
    incident_type_display = Column(Text)
    incident_category = Column(Text)
    incident_category_display = Column(Text)
    incident_title = Column(Text)
    incident_details = Column(Text)
    occurred_date = Column(Date)
    occurred_time = Column(Text)
    reported_date = Column(Date)
    reported_time = Column(Text)
    last_updated_date = Column(Date)
    last_updated_time = Column(Text)
    month = Column(Integer)
    month_name = Column(Text)
    quarter = Column(Text)
    year = Column(Integer)
    levelname_raw = Column(Text)
    severity = Column(Text)
    lname = Column(Text)
    zone = Column(Text)
    reported_by = Column(Text)
    incident_count = Column(Integer)
    dsr_date = Column(Date)
    reporting_lag_days = Column(Integer)
    is_partial_period = Column(Boolean)


class IncidentQuarantine(Base):
    __tablename__ = "incidents_quarantine"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    row_data = Column(JSONB)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
