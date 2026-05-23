"""
Incident data cleaning pipeline.

Entry point: clean_incidents(df) → (clean_df, report_dict)
No I/O — callers handle reading and writing.
"""

from datetime import date
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Placeholder site-name map.  Replace values with real canonical names later;
# the keys are whatever the raw SINAME strings look like after strip/upper.
SITE_NAME_MAP: dict[str, str] = {}

# LEVELNAME values that map to a canonical severity string
_SEVERITY_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "level 1 (minor)": "minor",
    "level 2 (major)": "major",
}

# The 1899-12-31 epoch sentinel used for unresolvable legacy dates
_BAD_YEAR_CUTOFF = 2000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_site_name(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "UNKNOWN"
    key = str(raw).strip().upper()
    return SITE_NAME_MAP.get(key, key)


def _normalise_severity(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "unknown"
    return _SEVERITY_MAP.get(str(raw).strip().lower(), "unknown")


def _parse_date_col(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%Y-%m-%d", errors="coerce").dt.date


def _current_quarter(today: date) -> tuple[int, str]:
    """
    Return (calendar_year, 'Q#') matching the fiscal quarter convention in the data.
    Fiscal year starts April 1: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.
    The YEAR column in the data stores the calendar year of the incident.
    """
    m = today.month
    if m >= 4:
        q = (m - 4) // 3 + 1   # Apr→1, Jul→2, Oct→3
    else:
        q = 4                   # Jan-Mar → Q4 of the same calendar year
    return today.year, f"Q{q}"


def _flag_partial_period(df: pd.DataFrame, today: date) -> pd.Series:
    """True for rows whose (YEAR, QUARTER) is the currently open quarter."""
    cur_year, cur_q = _current_quarter(today)
    return (df["YEAR"] == cur_year) & (df["QUARTER"] == cur_q)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_incidents(
    df: pd.DataFrame,
    today: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """
    Clean a raw incidents DataFrame loaded directly from the source CSV.

    Parameters
    ----------
    df:
        Raw DataFrame — columns must match the CSV schema.
    today:
        Reference date for partial-period flagging. Defaults to date.today().

    Returns
    -------
    clean_df:
        Cleaned DataFrame with renamed, typed, and derived columns.
    quarantine_df:
        Rows removed due to unparseable critical dates (still in raw column format).
    report:
        Counts and metadata describing what was dropped / quarantined.
    """
    if today is None:
        today = date.today()

    rows_in = len(df)
    dropped_bad_year: list[int] = []
    quarantined_bad_date: list[int] = []

    # ── 1. Drop rows with sentinel year (1899) ──────────────────────────────
    bad_year_mask = df["YEAR"] < _BAD_YEAR_CUTOFF
    dropped_bad_year = df.loc[bad_year_mask, "INCROWID"].tolist()
    df = df[~bad_year_mask].copy()

    # ── 2. Parse date columns ───────────────────────────────────────────────
    for col in ("OCCUREDDATE", "REPORTEDDATE", "LASTUPDATEDDATE", "DSRDATE"):
        df[col] = _parse_date_col(df[col])

    # ── 3. Quarantine rows where critical dates failed to parse ─────────────
    bad_date_mask = df["OCCUREDDATE"].isna() | df["REPORTEDDATE"].isna()
    quarantined_df = df[bad_date_mask].copy()
    quarantined_bad_date = quarantined_df["INCROWID"].tolist()
    df = df[~bad_date_mask].copy()

    # ── 4. Derived columns ──────────────────────────────────────────────────
    df["reporting_lag_days"] = (
        pd.to_datetime(df["REPORTEDDATE"]) - pd.to_datetime(df["OCCUREDDATE"])
    ).dt.days.astype(int)

    df["is_partial_period"] = _flag_partial_period(df, today)

    # ── 5. Normalise categoricals ───────────────────────────────────────────
    df["site_name"] = df["SINAME"].apply(_normalise_site_name)
    df["severity"] = df["LEVELNAME"].apply(_normalise_severity)

    # ── 6. Drop and rename columns ──────────────────────────────────────────
    df = df.drop(columns=["PRIORITY", "SINAME"])  # PRIORITY is constant

    rename_map = {
        "INCROWID": "incrow_id",
        "INCIDENTID": "incident_id",
        "VNAME": "vname",
        "VCODE": "vcode",
        "BUNAME": "buname",
        "BUCODE": "bucode",
        "SICODE": "sicode",
        "STATUS": "status",
        "INCIDENTTYPENAME": "incident_type",
        "INCIDENTTYPENAME_DISPLAY": "incident_type_display",
        "INCIDENTCATNAME": "incident_category",
        "INCIDENTCATNAME_DISPLAY": "incident_category_display",
        "INCIDENTTITLE": "incident_title",
        "INCIDENTDETAILS": "incident_details",
        "OCCUREDDATE": "occurred_date",
        "OCCUREDTIME": "occurred_time",
        "REPORTEDDATE": "reported_date",
        "REPORTEDTIME": "reported_time",
        "LASTUPDATEDDATE": "last_updated_date",
        "LASTUPDATEDTIME": "last_updated_time",
        "MONTH": "month",
        "MONTHNAME": "month_name",
        "QUARTER": "quarter",
        "YEAR": "year",
        "LEVELNAME": "levelname_raw",
        "LNAME": "lname",
        "ZNAME": "zone",
        "REPORTEDBY": "reported_by",
        "INCIDENTCOUNT": "incident_count",
        "DSRDATE": "dsr_date",
    }
    df = df.rename(columns=rename_map)

    rows_out = len(df)

    report: dict[str, Any] = {
        "rows_in": rows_in,
        "rows_out": rows_out,
        "rows_dropped_bad_year": len(dropped_bad_year),
        "incrowids_dropped_bad_year": dropped_bad_year,
        "rows_quarantined_bad_date": len(quarantined_bad_date),
        "incrowids_quarantined": quarantined_bad_date,
        "rows_with_negative_lag": int((df["reporting_lag_days"] < 0).sum()),
        "rows_partial_period": int(df["is_partial_period"].sum()),
        "reference_date": today.isoformat(),
    }

    return df, quarantined_df, report
