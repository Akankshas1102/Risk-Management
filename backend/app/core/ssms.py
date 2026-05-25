"""
Backward-compat shim — api/ files import get_ssms_db / SSMSSession from here.
All real database logic lives in core/database.py.
Do not add new code here.
"""

from app.core.database import engine as ssms_engine          # noqa: F401
from app.core.database import SessionLocal as SSMSSession    # noqa: F401
from app.core.database import get_db as get_ssms_db          # noqa: F401

__all__ = ["ssms_engine", "SSMSSession", "get_ssms_db"]
