"""
SQL Server (vedanta) engine — used by the analytics API.
Kept separate from database.py so PostgreSQL-based models are unaffected.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

ssms_engine = create_engine(settings.SSMS_DATABASE_URL, pool_pre_ping=True, pool_size=5)
SSMSSession = sessionmaker(bind=ssms_engine, autocommit=False, autoflush=False)


def get_ssms_db():
    db = SSMSSession()
    try:
        yield db
    finally:
        db.close()
