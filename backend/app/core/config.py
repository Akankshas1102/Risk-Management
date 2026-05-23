from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    # SQL Server (vedanta) — used by the analytics API
    SSMS_DATABASE_URL: str = (
        "mssql+pyodbc://sa:m00se_1234@localhost/vedanta"
        "?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes"
    )
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
