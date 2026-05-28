"""Add abs_pct_error to backtest_results; add n_quarters_history to model_runs

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-23

Apply with:  python scripts/apply_migrations.py
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. abs_pct_error on backtest_results
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'backtest_results')
              AND name = 'abs_pct_error'
        )
        ALTER TABLE backtest_results ADD abs_pct_error FLOAT NULL
        """
    )

    # 2. n_quarters_history on model_runs
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'model_runs')
              AND name = 'n_quarters_history'
        )
        ALTER TABLE model_runs ADD n_quarters_history INT NULL
        """
    )

    # 3. Backfill abs_pct_error for existing rows
    op.execute(
        """
        UPDATE backtest_results
        SET abs_pct_error =
            CASE
                WHEN actual IS NOT NULL AND actual > 0 AND predicted IS NOT NULL
                THEN ABS((actual - predicted) / actual) * 100.0
                ELSE NULL
            END
        WHERE abs_pct_error IS NULL
        """
    )

    # 4. Backfill n_quarters_history for existing champion rows
    op.execute(
        """
        UPDATE mr
        SET mr.n_quarters_history = sub.nq
        FROM model_runs mr
        JOIN (
            SELECT site, COUNT(DISTINCT quarter) AS nq
            FROM risk_scores
            GROUP BY site
        ) sub ON sub.site = mr.site
        WHERE mr.is_champion = 1
          AND mr.n_quarters_history IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('backtest_results') AND name='abs_pct_error') "
        "ALTER TABLE backtest_results DROP COLUMN abs_pct_error"
    )
    op.execute(
        "IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('model_runs') AND name='n_quarters_history') "
        "ALTER TABLE model_runs DROP COLUMN n_quarters_history"
    )
