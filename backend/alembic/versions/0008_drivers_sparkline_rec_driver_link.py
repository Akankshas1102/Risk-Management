"""Add sparkline_data to risk_drivers; add driver_link to recommendations

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-24

Apply with:  python scripts/apply_migrations.py
(ALTER TABLE statements were originally applied via pyodbc against SQL Server.)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sparkline_data: JSON array of last-6-months counts per driver category
    # stored as NVARCHAR(MAX) — SQL Server has no native JSONB
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'risk_drivers') AND name = 'sparkline_data'
        )
        ALTER TABLE risk_drivers ADD sparkline_data NVARCHAR(MAX) NULL
        """
    )

    # driver_link: which category triggered the recommendation rule
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'recommendations') AND name = 'driver_link'
        )
        ALTER TABLE recommendations ADD driver_link NVARCHAR(500) NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('risk_drivers') AND name='sparkline_data') "
        "ALTER TABLE risk_drivers DROP COLUMN sparkline_data"
    )
    op.execute(
        "IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('recommendations') AND name='driver_link') "
        "ALTER TABLE recommendations DROP COLUMN driver_link"
    )
