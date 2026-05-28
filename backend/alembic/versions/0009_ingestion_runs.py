"""Create ingestion_runs table in PostgreSQL

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-25

Apply with:  python scripts/apply_migrations.py
(The table is created by Base.metadata.create_all — no raw SQL needed here.)
"""

from typing import Sequence, Union

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table is created via Base.metadata.create_all(checkfirst=True)
    # in scripts/apply_migrations.py — no explicit DDL needed here.
    pass


def downgrade() -> None:
    # To remove manually:
    #   DROP TABLE IF EXISTS ingestion_runs;
    pass
