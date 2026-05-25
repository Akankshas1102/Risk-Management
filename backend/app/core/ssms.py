"""
Database connection — PostgreSQL (vedanta_risk).

All names (SSMSSession, ssms_engine, get_ssms_db, SSMSBase) are kept as-is so
existing API files (api/analytics.py, api/admin.py, etc.) continue to work
without modification.  The underlying database is now PostgreSQL, not SQL Server.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

ssms_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
)
SSMSSession = sessionmaker(bind=ssms_engine, autocommit=False, autoflush=False)


def get_ssms_db():
    db = SSMSSession()
    try:
        yield db
    finally:
        db.close()
