"""predictions cache and model runs (SQL Server)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-19

NOTE: This migration was originally written for SQL Server (IF NOT EXISTS guards).
The active deployment is PostgreSQL — apply via:
    python scripts/apply_migrations.py
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[predictions_cache]') AND type = N'U'
        )
        CREATE TABLE predictions_cache (
            id          BIGINT IDENTITY(1,1) NOT NULL,
            site        NVARCHAR(500)  NOT NULL,
            business_unit NVARCHAR(500),
            target_quarter NVARCHAR(10) NOT NULL,
            predicted_count FLOAT,
            lower_ci    FLOAT,
            upper_ci    FLOAT,
            model_name  NVARCHAR(50),
            trained_at  DATETIME2,
            training_data_through NVARCHAR(10),
            confidence_band NVARCHAR(10),
            CONSTRAINT pk_predictions_cache PRIMARY KEY (id),
            CONSTRAINT uq_predictions_site_quarter UNIQUE (site, target_quarter)
        )
        """
    )

    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[model_runs]') AND type = N'U'
        )
        CREATE TABLE model_runs (
            id           BIGINT IDENTITY(1,1) NOT NULL,
            model_name   NVARCHAR(50)  NOT NULL,
            site         NVARCHAR(500),
            trained_at   DATETIME2,
            training_rows INT,
            holdout_rmse  FLOAT,
            holdout_mape  FLOAT,
            is_champion   BIT DEFAULT 0,
            notes         NVARCHAR(2000),
            CONSTRAINT pk_model_runs PRIMARY KEY (id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS predictions_cache")
    op.execute("DROP TABLE IF EXISTS model_runs")
