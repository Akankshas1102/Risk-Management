"""
Fiscal-quarter labelling — the ONE place every other module gets quarter
strings, sort keys, and conversions from.

Convention (CALENDAR-YEAR + fiscal-quarter letter — matches the raw CSV and
every other module: analytics, forecaster, backtest, predictions, drivers):

    Q1 = Apr-Jun
    Q2 = Jul-Sep
    Q3 = Oct-Dec
    Q4 = Jan-Mar   (falls at the START of the calendar year)

The label format is ``YYYY-Qn`` where YYYY is the **calendar** year of the
months in that quarter.  So January 2026 is labelled ``2026-Q4`` — exactly as
the source CSV stores it (YEAR=2026, QUARTER='Q4').  No re-basing is done, so
``risk_scores`` lines up with ``predictions_cache`` / ``backtest_results`` /
the analytics endpoints, which all use this same calendar labelling.

Chronological order WITHIN a calendar year is:

    Q4 (Jan-Mar) → Q1 (Apr-Jun) → Q2 (Jul-Sep) → Q3 (Oct-Dec)

which ``sort_key`` reproduces (Q4 sorts first within a year).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Chronological order of fiscal quarters WITHIN one calendar year.
# Q4 (Jan-Mar) is earliest, Q3 (Oct-Dec) is latest.
_Q_CHRONO = ["Q4", "Q1", "Q2", "Q3"]

# Calendar-month range printed alongside each fiscal quarter.
_Q_MONTHS = {
    "Q1": ("Apr", "Jun"),
    "Q2": ("Jul", "Sep"),
    "Q3": ("Oct", "Dec"),
    "Q4": ("Jan", "Mar"),
}

# First calendar month of each fiscal quarter (within the same calendar year).
_Q_START_MONTH = {"Q4": 1, "Q1": 4, "Q2": 7, "Q3": 10}


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------

def fiscal_year_for(year: int, month: int) -> int:
    """
    FISCAL-YEAR-START year for a (calendar year, month) pair.

    Informational only — labels in this module use the CALENDAR year, not this.
    Apr 2025 → 2025, Jan 2026 → 2025.  Kept for callers that genuinely need the
    Apr-Mar fiscal-year grouping.
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
    Canonical ``YYYY-Qn`` label for a (calendar year, month) pair, using the
    CALENDAR year (matches the CSV + analytics + forecaster).

        Apr 2025 → '2025-Q1'
        Jan 2026 → '2026-Q4'
        Apr 2026 → '2026-Q1'
    """
    return f"{year}-{fiscal_quarter_letter(month)}"


def from_timestamp(ts: pd.Timestamp) -> str:
    """Same as from_year_month but takes a pandas Timestamp."""
    return from_year_month(ts.year, ts.month)


def csv_to_label(year_csv: int, quarter_csv: str) -> str:
    """
    Convert the raw CSV columns (YEAR + QUARTER) to the canonical label.

    The CSV already stores the calendar year plus the fiscal-quarter letter
    (Jan 2026 → YEAR=2026, QUARTER='Q4'), which IS the canonical label here —
    so this is a direct join with NO re-basing.

        csv_to_label(2026, 'Q4') → '2026-Q4'
        csv_to_label(2025, 'Q1') → '2025-Q1'
    """
    return f"{int(year_csv)}-{quarter_csv}"


# ---------------------------------------------------------------------------
# Sort key
# ---------------------------------------------------------------------------

def sort_key(label: str) -> int:
    """
    Comparable integer for canonical labels.  Larger = later in time.

        '2026-Q4' → 20260   (Jan-Mar 2026)
        '2026-Q1' → 20261   (Apr-Jun 2026)
        '2026-Q2' → 20262
        '2026-Q3' → 20263   (Oct-Dec 2026)
        '2027-Q4' → 20270   (Jan-Mar 2027)
    """
    year_str, q = label.split("-")
    return int(year_str) * 10 + _Q_CHRONO.index(q)


def quarter_start_timestamp(label: str) -> pd.Timestamp:
    """First day of the fiscal quarter as a pandas Timestamp (calendar year)."""
    year_str, q = label.split("-")
    return pd.Timestamp(year=int(year_str), month=_Q_START_MONTH[q], day=1)


def calendar_months_label(label: str) -> str:
    """
    Human-friendly calendar range for a label.

        '2026-Q4' → 'Jan-Mar 2026'
        '2025-Q1' → 'Apr-Jun 2025'
    """
    year_str, q = label.split("-")
    m_start, m_end = _Q_MONTHS[q]
    return f"{m_start}-{m_end} {year_str}"


def with_calendar(label: str) -> str:
    """Return ``'2026-Q4 (Jan-Mar 2026)'`` style string."""
    return f"{label} ({calendar_months_label(label)})"


# ---------------------------------------------------------------------------
# Current / previous helpers
# ---------------------------------------------------------------------------

def current_label(today: Optional[date] = None) -> str:
    """The label of the quarter that is currently in progress."""
    today = today or date.today()
    return from_year_month(today.year, today.month)


def previous_label(label: str) -> str:
    """
    Step one fiscal quarter back, chronologically.

        '2026-Q4' → '2025-Q3'   (Jan-Mar 2026 ← Oct-Dec 2025)
        '2026-Q1' → '2026-Q4'
        '2026-Q2' → '2026-Q1'
        '2026-Q3' → '2026-Q2'
    """
    year_str, q = label.split("-")
    year = int(year_str)
    idx = _Q_CHRONO.index(q)
    if idx == 0:           # Q4 → previous calendar year's Q3
        return f"{year - 1}-Q3"
    return f"{year}-{_Q_CHRONO[idx - 1]}"


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
