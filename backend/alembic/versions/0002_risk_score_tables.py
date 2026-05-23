"""risk score tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_score_weights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("business_unit", sa.Text()),
        sa.Column("w_frequency", sa.Numeric(5, 4), nullable=False),
        sa.Column("w_severity", sa.Numeric(5, 4), nullable=False),
        sa.Column("w_velocity", sa.Numeric(5, 4), nullable=False),
        sa.Column("w_diversity", sa.Numeric(5, 4), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "risk_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("business_unit", sa.Text()),
        sa.Column("quarter", sa.String(10), nullable=False),
        sa.Column("quarter_sort_key", sa.Integer()),
        sa.Column("risk_score", sa.Numeric(7, 4)),
        sa.Column("risk_level", sa.String(20)),
        sa.Column("frequency_index", sa.Numeric(8, 6)),
        sa.Column("severity_index", sa.Numeric(8, 6)),
        sa.Column("velocity_index", sa.Numeric(8, 6)),
        sa.Column("diversity_index", sa.Numeric(8, 6)),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site", "quarter", name="uq_risk_scores_site_quarter"),
    )
    op.create_index("ix_risk_scores_site", "risk_scores", ["site"])
    op.create_index("ix_risk_scores_quarter", "risk_scores", ["quarter"])
    op.create_index("ix_risk_scores_risk_level", "risk_scores", ["risk_level"])
    op.create_index("ix_risk_scores_quarter_sort_key", "risk_scores", ["quarter_sort_key"])

    # Seed global default weights
    op.execute(
        """
        INSERT INTO risk_score_weights
            (business_unit, w_frequency, w_severity, w_velocity, w_diversity, effective_from)
        VALUES
            (NULL, 0.35, 0.30, 0.20, 0.15, '2026-01-01')
        """
    )


def downgrade() -> None:
    op.drop_table("risk_scores")
    op.drop_table("risk_score_weights")
