"""
scripts/load_csv_to_db.py
=========================
Load OL_INCIDENTS CSV into the PostgreSQL vedanta_risk database.

Usage
-----
    cd backend
    python ../scripts/load_csv_to_db.py

What it does
------------
1. Reads data/raw/OL_INCIDENTS_20260518_142042.csv
2. Lowercases all column names (Postgres convention)
3. Adds derived columns: month, quarter, year (if not already present)
4. Drops the existing ol_incidents table and recreates it via the ORM model
5. Loads all rows using pandas to_sql (fast, bulk insert)

Re-running this script is safe — it fully replaces ol_incidents each time.

Requirements
------------
    pip install psycopg2-binary pandas sqlalchemy

Postgres must be running and the vedanta_risk database must exist:
    CREATE DATABASE vedanta_risk;   -- run once in pgAdmin or psql
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow imports from backend/app when run from repo root or scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import pandas as pd
from sqlalchemy import text

from app.core.database import engine, SessionLocal
from app.models.ol_incidents import OLIncident, Base
import app.models.predictions  # noqa: F401 — registers PredictionsCache, ModelRun
import app.models.drivers      # noqa: F401 — registers RiskDriver, Recommendation
import app.models.pipeline     # noqa: F401 — registers PipelineRun, RiskScore
import app.models.backtest     # noqa: F401 — registers BacktestResult
import app.models.ingestion    # noqa: F401 — registers IngestionRun

# ── CSV path ──────────────────────────────────────────────────────────────────
# Prefer the cleaned CSV produced by scripts/clean_csv.py.
# Falls back to the raw export if the cleaned file isn't present.
_CLEAN_PATH = REPO_ROOT / "data" / "raw" / "OL_INCIDENTS_clean.csv"
_RAW_PATH   = REPO_ROOT / "data" / "raw" / "OL_INCIDENTS_20260518_142042.csv"
CSV_PATH    = _CLEAN_PATH if _CLEAN_PATH.exists() else _RAW_PATH


def _derive_quarter(month: int) -> str:
    """Map calendar month (1–12) to fiscal quarter string Q1–Q4."""
    # Vedanta fiscal year: Q4=Jan-Mar, Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec
    mapping = {
        1: "Q4", 2: "Q4", 3: "Q4",
        4: "Q1", 5: "Q1", 6: "Q1",
        7: "Q2", 8: "Q2", 9: "Q2",
        10: "Q3", 11: "Q3", 12: "Q3",
    }
    return mapping.get(month, "Q1")


def load_csv(csv_path: Path = CSV_PATH) -> None:
    print(f"Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  Rows loaded: {len(df):,}")

    # ── Normalise column names to lowercase ───────────────────────────────
    df.columns = [c.strip().lower() for c in df.columns]
    print(f"  Columns: {list(df.columns)}")

    # ── Derive month / quarter / year if missing or empty ─────────────────
    # occureddate is expected as "YYYY-MM-DD" string
    if "occureddate" in df.columns:
        dates = pd.to_datetime(df["occureddate"], errors="coerce")

        if "month" not in df.columns or df["month"].isna().all():
            df["month"] = dates.dt.month.astype("Int64")

        if "year" not in df.columns or df["year"].isna().all():
            df["year"] = dates.dt.year.astype(str)
            df.loc[df["year"] == "<NA>", "year"] = None

        if "quarter" not in df.columns or df["quarter"].isna().all():
            df["quarter"] = dates.dt.month.map(_derive_quarter)

    # ── Keep only columns that the ORM model knows about ─────────────────
    orm_columns = {c.key for c in OLIncident.__table__.columns}
    extra = set(df.columns) - orm_columns
    if extra:
        print(f"  Dropping {len(extra)} unrecognised columns: {sorted(extra)}")
        df = df.drop(columns=list(extra))

    missing = orm_columns - set(df.columns) - {"incrowid"}
    if missing:
        print(f"  Adding {len(missing)} missing columns as NULL: {sorted(missing)}")
        for col in missing:
            df[col] = None

    # ── Ensure incrowid is numeric (primary key) ──────────────────────────
    if "incrowid" in df.columns:
        df["incrowid"] = pd.to_numeric(df["incrowid"], errors="coerce")
        before = len(df)
        df = df.dropna(subset=["incrowid"])
        df["incrowid"] = df["incrowid"].astype(int)
        if len(df) < before:
            print(f"  Dropped {before - len(df)} rows with null incrowid")

    # ── Drop duplicates on primary key ────────────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["incrowid"])
    if len(df) < before:
        print(f"  Dropped {before - len(df)} duplicate incrowid rows")

    # ── Create / recreate the ol_incidents table ──────────────────────────
    print("Creating tables in Postgres (drop + recreate ol_incidents)...")
    OLIncident.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine)  # creates ALL model tables
    print("  Tables created.")

    # ── Bulk insert via pandas to_sql ─────────────────────────────────────
    print(f"Inserting {len(df):,} rows into ol_incidents...")
    df.to_sql(
        "ol_incidents",
        engine,
        if_exists="append",     # table already created above
        index=False,
        chunksize=2000,
        method="multi",
    )
    print("  Done.")

    # ── Quick verification ────────────────────────────────────────────────
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM ol_incidents")).scalar()
    print(f"  Rows in ol_incidents: {count:,}")


if __name__ == "__main__":
    load_csv()
