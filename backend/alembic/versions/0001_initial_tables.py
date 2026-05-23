"""initial tables

Revision ID: 0001
Revises:
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("filename", sa.Text()),
        sa.Column("rows_received", sa.Integer()),
        sa.Column("rows_clean", sa.Integer()),
        sa.Column("rows_quarantined", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.PrimaryKeyConstraint("batch_id"),
    )

    op.create_table(
        "incidents_raw",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        # All original CSV columns — nullable Text keeps the raw data faithful
        sa.Column("incrowid", sa.Text()),
        sa.Column("vname", sa.Text()),
        sa.Column("buname", sa.Text()),
        sa.Column("siname", sa.Text()),
        sa.Column("priority", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("incidenttypename", sa.Text()),
        sa.Column("incidentcatname", sa.Text()),
        sa.Column("incidenttitle", sa.Text()),
        sa.Column("incidentdetails", sa.Text()),
        sa.Column("occureddate", sa.Text()),
        sa.Column("occuredtime", sa.Text()),
        sa.Column("reporteddate", sa.Text()),
        sa.Column("reportedtime", sa.Text()),
        sa.Column("lastupdateddate", sa.Text()),
        sa.Column("lastupdatedtime", sa.Text()),
        sa.Column("month", sa.Text()),
        sa.Column("quarter", sa.Text()),
        sa.Column("year", sa.Text()),
        sa.Column("lname", sa.Text()),
        sa.Column("levelname", sa.Text()),
        sa.Column("zname", sa.Text()),
        sa.Column("incidentid", sa.Text()),
        sa.Column("reportedby", sa.Text()),
        sa.Column("incidenttypename_display", sa.Text()),
        sa.Column("incidentcatname_display", sa.Text()),
        sa.Column("incidentcount", sa.Text()),
        sa.Column("monthname", sa.Text()),
        sa.Column("vcode", sa.Text()),
        sa.Column("bucode", sa.Text()),
        sa.Column("sicode", sa.Text()),
        sa.Column("dsrdate", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_raw_batch_id", "incidents_raw", ["batch_id"])
    op.create_index("ix_incidents_raw_incrowid", "incidents_raw", ["incrowid"])

    op.create_table(
        "incidents_clean",
        sa.Column("incrowid", sa.Integer(), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cleaned_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("incident_id", sa.Integer()),
        sa.Column("vname", sa.Text()),
        sa.Column("vcode", sa.Text()),
        sa.Column("buname", sa.Text()),
        sa.Column("bucode", sa.Text()),
        sa.Column("site_name", sa.Text()),
        sa.Column("sicode", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("incident_type", sa.Text()),
        sa.Column("incident_type_display", sa.Text()),
        sa.Column("incident_category", sa.Text()),
        sa.Column("incident_category_display", sa.Text()),
        sa.Column("incident_title", sa.Text()),
        sa.Column("incident_details", sa.Text()),
        sa.Column("occurred_date", sa.Date()),
        sa.Column("occurred_time", sa.Text()),
        sa.Column("reported_date", sa.Date()),
        sa.Column("reported_time", sa.Text()),
        sa.Column("last_updated_date", sa.Date()),
        sa.Column("last_updated_time", sa.Text()),
        sa.Column("month", sa.Integer()),
        sa.Column("month_name", sa.Text()),
        sa.Column("quarter", sa.Text()),
        sa.Column("year", sa.Integer()),
        sa.Column("levelname_raw", sa.Text()),
        sa.Column("severity", sa.Text()),
        sa.Column("lname", sa.Text()),
        sa.Column("zone", sa.Text()),
        sa.Column("reported_by", sa.Text()),
        sa.Column("incident_count", sa.Integer()),
        sa.Column("dsr_date", sa.Date()),
        sa.Column("reporting_lag_days", sa.Integer()),
        sa.Column("is_partial_period", sa.Boolean()),
        sa.PrimaryKeyConstraint("incrowid"),
    )
    op.create_index("ix_incidents_clean_year_quarter", "incidents_clean", ["year", "quarter"])
    op.create_index("ix_incidents_clean_site_name", "incidents_clean", ["site_name"])
    op.create_index("ix_incidents_clean_severity", "incidents_clean", ["severity"])

    op.create_table(
        "incidents_quarantine",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("row_data", JSONB()),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_quarantine_batch_id", "incidents_quarantine", ["batch_id"])


def downgrade() -> None:
    op.drop_table("incidents_quarantine")
    op.drop_table("incidents_clean")
    op.drop_table("incidents_raw")
    op.drop_table("ingestion_runs")
