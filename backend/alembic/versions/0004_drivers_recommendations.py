"""risk drivers and recommendations tables (SQL Server)

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-19

Apply with:   python scripts/apply_migrations.py
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[risk_drivers]') AND type = N'U'
        )
        CREATE TABLE risk_drivers (
            id                    BIGINT IDENTITY(1,1) NOT NULL,
            site                  NVARCHAR(500) NOT NULL,
            quarter               NVARCHAR(10)  NOT NULL,
            driver_name           NVARCHAR(500),
            category              NVARCHAR(500),
            impact_score          FLOAT,
            trend                 NVARCHAR(10),
            pct_change_vs_last_qtr FLOAT,
            computed_at           DATETIME2,
            CONSTRAINT pk_risk_drivers PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.indexes
                       WHERE name = 'ix_risk_drivers_site_quarter'
                         AND object_id = OBJECT_ID('risk_drivers'))
        CREATE INDEX ix_risk_drivers_site_quarter ON risk_drivers (site, quarter)
        """
    )

    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[recommendations]') AND type = N'U'
        )
        CREATE TABLE recommendations (
            id              BIGINT IDENTITY(1,1) NOT NULL,
            site            NVARCHAR(500) NOT NULL,
            quarter         NVARCHAR(10)  NOT NULL,
            action_text     NVARCHAR(2000),
            priority        NVARCHAR(10),
            impact_estimate NVARCHAR(500),
            suggested_owner NVARCHAR(500),
            status          NVARCHAR(50) DEFAULT 'open',
            source          NVARCHAR(10) DEFAULT 'rules',
            created_at      DATETIME2,
            CONSTRAINT pk_recommendations PRIMARY KEY (id),
            CONSTRAINT uq_rec_site_quarter_action
                UNIQUE (site, quarter, action_text)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommendations")
    op.execute("DROP TABLE IF EXISTS risk_drivers")
