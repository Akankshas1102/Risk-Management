"""
Compatibility shim — re-exports get_db from ssms.py.

The Postgres engine and SessionLocal were the original data store.
Phase 2C (2026-05-25) retired the Postgres stack; SQL Server (vedanta) is now
the sole database.  This file is kept so api/risk_scores.py (and any other
Vinay-owned API file that does `from app.core.database import get_db`) continues
to work without modification.

Do NOT add new Postgres dependencies here.
"""

from app.core.ssms import get_ssms_db as get_db  # noqa: F401

# SessionLocal is kept as a no-op alias so legacy import lines don't crash
# at import time.  It should NOT be used to open new sessions.
from app.core.ssms import SSMSSession as SessionLocal  # noqa: F401

__all__ = ["get_db", "SessionLocal"]
