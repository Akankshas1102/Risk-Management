"""backtest_results table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-20

Apply with:  python scripts/apply_ssms_migrations.py
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[backtest_results]') AND type = N'U'
        )
        CREATE TABLE backtest_results (
            id           BIGINT IDENTITY(1,1) NOT NULL,
            site         NVARCHAR(500) NOT NULL,
            month        NVARCHAR(10)  NOT NULL,   -- "YYYY-MM"
            actual       FLOAT,
            predicted    FLOAT,
            model_name   NVARCHAR(50),
            computed_at  DATETIME2,
            CONSTRAINT pk_backtest_results PRIMARY KEY (id),
            CONSTRAINT uq_backtest_site_month UNIQUE (site, month)
        )
        """
    )
    op.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.indexes
                       WHERE name = 'ix_backtest_site'
                         AND object_id = OBJECT_ID('backtest_results'))
        CREATE INDEX ix_backtest_site ON backtest_results (site)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backtest_results")
