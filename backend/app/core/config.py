from pathlib import Path
from pydantic_settings import BaseSettings

# Project root is 3 levels above this file: backend/app/core/config.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    # SQL Server (vedanta) — used by the analytics API
    SSMS_DATABASE_URL: str = (
        "mssql+pyodbc://sa:m00se_1234@localhost/vedanta"
        "?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes"
    )
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    # Cron expression for the nightly automatic retrain (UTC).
    # Default: daily at 02:00.  Override via RETRAIN_CRON env var.
    # Format: "minute hour day_of_month month day_of_week"
    RETRAIN_CRON: str = "0 2 * * *"

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


settings = Settings()
