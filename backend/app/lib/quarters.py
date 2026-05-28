"""
Fiscal-quarter labelling — the ONE place every other module gets quarter
strings, sort keys, and conversions from.

Convention used everywhere a quarter is *displayed* or *stored as a label*:

    Q1 = Apr-Jun  (start of fiscal year)
    Q2 = Jul-Sep
    Q3 = Oct-Dec
    Q4 = Jan-Mar  (end of fiscal year — wraps into next calendar year)

The label format is ``YYYY-Qn`` where YYYY is the fiscal-year **start** year.
So January 2026 is part of fiscal year 2025-26 → label ``2025-Q4``.
This makes labels read in true chronological order:

    2025-Q1 → 2025-Q2 → 2025-Q3 → 2025-Q4 → 2026-Q1

Note on the source CSV (``ol_incidents``):
    The raw ``YEAR`` and ``QUARTER`` columns store the *calendar* year of
    the month plus the fiscal quarter letter, so Jan 2026 has
    ``YEAR=2026, QUARTER='Q4'``.  Those columns are NOT touched by this
    helper — they stay exactly as the CSV provides them.  Every place that
    needs a display label calls ``csv_to_label`` to convert.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fiscal-quarter ordinal — Q1 first, Q4 last in the fiscal year.
_Q_ORDER = ["Q1", "Q2", "Q3", "Q4"]

# Calendar-month range printed alongside each fiscal quarter.
_Q_MONTHS = {
    "Q1": ("Apr", "Jun"),
    "Q2": ("Jul", "Sep"),
    "Q3": ("Oct", "Dec"),
    "Q4": ("Jan", "Mar"),
}

# First calendar month of each fiscal quarter (used to compute Timestamps).
_Q_START_MONTH = {"Q1": 4, "Q2": 7, "Q3": 10, "Q4": 1}


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------

def fiscal_year_for(year: int, month: int) -> int:
    """
    Return the FISCAL-YEAR-START year for a (calendar year, month) pair.

    Apr 2025 → 2025  (FY 2025-26 starts in Apr 2025)
    Jan 2026 → 2025  (still inside FY 2025-26)
    Apr 2026 → 2026  (FY 2026-27 starts)
    """
    return year if month >= 4 else year - 1


def fiscal_quarter_letter(month: int) -> str:
    """Map a calendar month (1-12) to its fiscal-quarter letter Q1..Q4."""
    if 4 <= month <= 6:
        return "Q1"
    if 7 <= month <= 9:
        return "Q2"
    if 10 <= month <= 12:
        return "Q3"
    return "Q4"   # Jan, Feb, Mar


def from_year_month(year: int, month: int) -> str:
    """
    Build the canonical ``YYYY-Qn`` label for a (calendar year, month) pair.

    Uses fiscal-year-start convention everywhere:
        Apr 2025 → '2025-Q1'
        Jan 2026 → '2025-Q4'
        Apr 2026 → '2026-Q1'
    """
    fy = fiscal_year_for(year, month)
    q = fiscal_quarter_letter(month)
    return f"{fy}-{q}"


def from_timestamp(ts: pd.Timestamp) -> str:
    """Same as from_year_month but takes a pandas Timestamp."""
    return from_year_month(ts.year, ts.month)


def csv_to_label(year_csv: int, quarter_csv: str) -> str:
    """
    Convert the *raw CSV columns* (YEAR + QUARTER) to the canonical label.

    The CSV stores YEAR as the calendar year of the row's OCCUREDDATE plus
    QUARTER as 'Q1' | 'Q2' | 'Q3' | 'Q4' (already fiscal).  For Q4 the CSV
    keeps the calendar year of Jan/Feb/Mar — meaning Jan 2026 has
    YEAR=2026, QUARTER='Q4', which under the fiscal-year-start convention
    must be re-labelled as '2025-Q4'.
    """
    year_csv = int(year_csv)
    if quarter_csv == "Q4":
        # CSV's Jan-Mar Q4 ⇒ fiscal year started in the previous calendar year
        return f"{year_csv - 1}-Q4"
    return f"{year_csv}-{quarter_csv}"


# ---------------------------------------------------------------------------
# Sort key
# ---------------------------------------------------------------------------

def sort_key(label: str) -> int:
    """
    Comparable integer for canonical labels.  Larger = later in time.

    '2025-Q1' → 20251
    '2025-Q4' → 20254   (Jan-Mar 2026)
    '2026-Q1' → 20261
    """
    fy_str, q = label.split("-")
    return int(fy_str) * 10 + (_Q_ORDER.index(q) + 1)


def quarter_start_timestamp(label: str) -> pd.Timestamp:
    """First day of the fiscal quarter as a pandas Timestamp."""
    fy_str, q = label.split("-")
    fy = int(fy_str)
    start_month = _Q_START_MONTH[q]
    cal_year = fy + 1 if q == "Q4" else fy
    return pd.Timestamp(year=cal_year, month=start_month, day=1)


def calendar_months_label(label: str) -> str:
    """
    Return a human-friendly calendar range for a fiscal label.

    '2025-Q4' → 'Jan-Mar 2026'
    '2025-Q1' → 'Apr-Jun 2025'
    """
    fy_str, q = label.split("-")
    fy = int(fy_str)
    cal_year = fy + 1 if q == "Q4" else fy
    m_start, m_end = _Q_MONTHS[q]
    return f"{m_start}-{m_end} {cal_year}"


def with_calendar(label: str) -> str:
    """Return ``'2025-Q4 (Jan-Mar 2026)'`` style string."""
    return f"{label} ({calendar_months_label(label)})"


# ---------------------------------------------------------------------------
# Current / previous helpers
# ---------------------------------------------------------------------------

def current_label(today: Optional[date] = None) -> str:
    """The label of the quarter that is currently in progress."""
    today = today or date.today()
    return from_year_month(today.year, today.month)


def previous_label(label: str) -> str:
    """Step one fiscal quarter back."""
    fy_str, q = label.split("-")
    fy = int(fy_str)
    idx = _Q_ORDER.index(q)
    if idx == 0:
        return f"{fy - 1}-Q4"
    return f"{fy}-{_Q_ORDER[idx - 1]}"


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "fiscal_year_for",
    "fiscal_quarter_letter",
    "from_year_month",
    "from_timestamp",
    "csv_to_label",
    "sort_key",
    "quarter_start_timestamp",
    "calendar_months_label",
    "with_calendar",
    "current_label",
    "previous_label",
]
