"""
Test fixtures for integration tests.

Requires a running PostgreSQL instance.  Set TEST_DATABASE_URL (or DATABASE_URL)
before running:

    TEST_DATABASE_URL=postgresql://user:pass@localhost/test_risk pytest backend/tests/
"""

import os
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Allow imports from backend/
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import Base
import app.models.incident    # noqa: F401 — registers all tables
import app.models.risk_score  # noqa: F401


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

def _test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("No TEST_DATABASE_URL or DATABASE_URL set — skipping DB tests.")
    return url


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(_test_db_url())
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    return sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


_DB_FIXTURE_NAMES = frozenset({"test_engine", "test_session_factory"})

@pytest.fixture(autouse=True)
def truncate_tables(request):
    """
    Wipe all test data between tests so each test starts clean.
    Only connects to the DB when the test actually uses a DB fixture —
    pure-math tests run without any DB interaction.
    """
    yield
    if not _DB_FIXTURE_NAMES.intersection(request.fixturenames):
        return
    try:
        engine = request.getfixturevalue("test_engine")
        with engine.connect() as conn:
            conn.execute(
                text(
                    "TRUNCATE TABLE risk_scores, incidents_quarantine, incidents_clean, "
                    "incidents_raw, ingestion_runs RESTART IDENTITY CASCADE"
                )
            )
            conn.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sample CSV fixture
# ---------------------------------------------------------------------------

_CSV_HEADER = (
    "INCROWID,VNAME,BUNAME,SINAME,PRIORITY,STATUS,INCIDENTTYPENAME,INCIDENTCATNAME,"
    "INCIDENTTITLE,INCIDENTDETAILS,OCCUREDDATE,OCCUREDTIME,REPORTEDDATE,REPORTEDTIME,"
    "LASTUPDATEDDATE,LASTUPDATEDTIME,MONTH,QUARTER,YEAR,LNAME,LEVELNAME,ZNAME,"
    "INCIDENTID,REPORTEDBY,INCIDENTTYPENAME_DISPLAY,INCIDENTCATNAME_DISPLAY,"
    "INCIDENTCOUNT,MONTHNAME,VCODE,BUCODE,SICODE,DSRDATE"
)

def _row(
    incrowid, year="2024", quarter="Q3", month="10", monthname="OCT",
    occureddate="2024-10-01", reporteddate="2024-10-02",
    levelname="Low", status="CLOSED",
):
    return (
        f"{incrowid},VEDANTA LIMITED,ALUMINIUM SECTOR,ENABLING,LOW,{status},"
        f"SECURITY INCIDENTS,ASSET/PROPERTY,Test incident {incrowid},,{occureddate},"
        f"10:00,{reporteddate},10:30,2024-10-15,09:00,{month},Q{quarter[-1]},"
        f"{year},HYDRO-1,{levelname},HYDRO-1,{incrowid},Test User,"
        f"SCR-INC,ASSET,1,{monthname},VL,AL,EN,{occureddate}"
    )


@pytest.fixture()
def sample_csv(tmp_path) -> Path:
    """
    10-row CSV:
    - 8 valid rows (YEAR=2024)
    - 1 row with YEAR=1899 (dropped by cleaner — bad year)
    - 1 row with OCCUREDDATE=not-a-date (quarantined — bad date)
    Expected after ingestion: rows_received=10, rows_clean=8, rows_quarantined=1.
    """
    rows = [_CSV_HEADER]
    for i in range(1, 9):
        rows.append(_row(incrowid=i))
    # Bad year row
    rows.append(_row(incrowid=9, year="1899", occureddate="1899-12-31", reporteddate="2024-01-01"))
    # Bad date row
    rows.append(_row(incrowid=10, occureddate="not-a-date"))

    csv_file = tmp_path / "sample_incidents.csv"
    csv_file.write_text("\n".join(rows))
    return csv_file
