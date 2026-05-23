"""pipeline_runs and risk_scores tables (SQL Server)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-19

Apply with:  python scripts/apply_ssms_migrations.py
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[pipeline_runs]') AND type = N'U'
        )
        CREATE TABLE pipeline_runs (
            id            BIGINT IDENTITY(1,1) NOT NULL,
            trigger       NVARCHAR(50),
            started_at    DATETIME2,
            finished_at   DATETIME2,
            status        NVARCHAR(20),
            steps_run     NVARCHAR(MAX),
            error_summary NVARCHAR(2000),
            CONSTRAINT pk_pipeline_runs PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.indexes
                       WHERE name = 'ix_pipeline_runs_started_at'
                         AND object_id = OBJECT_ID('pipeline_runs'))
        CREATE INDEX ix_pipeline_runs_started_at ON pipeline_runs (started_at DESC)
        """
    )

    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[risk_scores]') AND type = N'U'
        )
        CREATE TABLE risk_scores (
            id                BIGINT IDENTITY(1,1) NOT NULL,
            site              NVARCHAR(500) NOT NULL,
            business_unit     NVARCHAR(500),
            quarter           NVARCHAR(10)  NOT NULL,
            quarter_sort_key  INT,
            risk_score        FLOAT,
            risk_level        NVARCHAR(20),
            frequency_index   FLOAT,
            severity_index    FLOAT,
            velocity_index    FLOAT,
            diversity_index   FLOAT,
            computed_at       DATETIME2,
            CONSTRAINT pk_risk_scores PRIMARY KEY (id),
            CONSTRAINT uq_risk_scores_site_quarter UNIQUE (site, quarter)
        )
        """
    )
    op.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.indexes
                       WHERE name = 'ix_risk_scores_quarter_sort_key'
                         AND object_id = OBJECT_ID('risk_scores'))
        CREATE INDEX ix_risk_scores_quarter_sort_key ON risk_scores (quarter_sort_key DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pipeline_runs")
    op.execute("DROP TABLE IF EXISTS risk_scores")
