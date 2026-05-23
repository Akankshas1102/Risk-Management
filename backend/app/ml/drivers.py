"""
SHAP-based risk driver attribution with sparkline, QoQ trend, and pct change.

Builds a quarterly per-category pivot, trains XGBoost (lag-1 category counts → next
quarter total), and explains the most recent quarter's prediction with SHAP values.
Falls back to raw proportion-based impact when data is insufficient (<6 quarters).

Also computes per-driver sparklines (last N months of monthly counts) so the
frontend can render small trend charts without extra round-trips.

Public API
----------
compute_drivers_for_site(site, quarter, n_sparkline_months, session_factory)
    -> pd.DataFrame with columns: driver_name, category, impact_score,
       trend, pct_change_vs_last_qtr, sparkline_data, quarter, computed_at.

_build_quarterly_pivot(raw_df)   -> pd.DataFrame  (exposed for unit tests)
_apply_shap_or_fallback(pivot)   -> pd.DataFrame  (exposed for unit tests)
build_category_sparklines(site, categories, n_months, session_factory)
    -> dict[category, JSON str]  (exposed for tests / separate use)
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import shap
from sqlalchemy import select
from xgboost import XGBRegressor

from app.core.ssms import SSMSSession
from app.models.ol_incidents import OLIncident

warnings.filterwarnings("ignore", category=UserWarning)

_MIN_YEAR = "2020"
_MIN_QUARTERS_FOR_MODEL = 6   # below this → proportion fallback
_FISCAL_ORDER = {"Q4": 0, "Q1": 1, "Q2": 2, "Q3": 3}
_DEFAULT_SPARKLINE_MONTHS = 6


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_quarterly_cat_raw(site: str, session_factory=None) -> pd.DataFrame:
    sf = session_factory or SSMSSession
    with sf() as session:
        rows = session.execute(
            select(
                OLIncident.YEAR,
                OLIncident.QUARTER,
                OLIncident.INCIDENTCATNAME,
            )
            .where(
                OLIncident.SINAME == site,
                OLIncident.YEAR >= _MIN_YEAR,
                OLIncident.YEAR.isnot(None),
                OLIncident.QUARTER.isnot(None),
            )
        ).all()
    return pd.DataFrame(rows, columns=["YEAR", "QUARTER", "INCIDENTCATNAME"])


def _load_monthly_cat_raw(site: str, session_factory=None) -> pd.DataFrame:
    """
    Load per-month incident counts per category for a site.

    Returns DataFrame with columns [YEAR (int), MONTH (int), INCIDENTCATNAME, count].
    Only rows where YEAR and MONTH are not null are included.
    """
    sf = session_factory or SSMSSession
    with sf() as session:
        rows = session.execute(
            select(
                OLIncident.YEAR,
                OLIncident.MONTH,
                OLIncident.INCIDENTCATNAME,
            )
            .where(
                OLIncident.SINAME == site,
                OLIncident.YEAR >= _MIN_YEAR,
                OLIncident.YEAR.isnot(None),
                OLIncident.MONTH.isnot(None),
            )
        ).all()

    if not rows:
        return pd.DataFrame(columns=["YEAR", "MONTH", "INCIDENTCATNAME", "count"])

    raw = pd.DataFrame(rows, columns=["YEAR", "MONTH", "INCIDENTCATNAME"])
    raw["YEAR"] = pd.to_numeric(raw["YEAR"], errors="coerce").astype("Int64")
    raw["MONTH"] = pd.to_numeric(raw["MONTH"], errors="coerce").astype("Int64")
    raw = raw.dropna(subset=["YEAR", "MONTH"])
    raw["INCIDENTCATNAME"] = raw["INCIDENTCATNAME"].fillna("Unknown")

    counts = (
        raw.groupby(["YEAR", "MONTH", "INCIDENTCATNAME"])
        .size()
        .reset_index(name="count")
    )
    return counts


# ---------------------------------------------------------------------------
# Sparkline builder
# ---------------------------------------------------------------------------

def build_category_sparklines(
    site: str,
    categories: list[str],
    n_months: int = _DEFAULT_SPARKLINE_MONTHS,
    session_factory=None,
) -> dict[str, str]:
    """
    Return a dict mapping each category name to a JSON string of the last
    n_months monthly counts (oldest → newest), e.g. '{"sparkline": [2,0,5,3,7,4]}'.

    Stored value is a plain JSON array string: "[2,0,5,3,7,4]"

    Missing months in the range are zero-filled.
    Categories with no data at all get an array of zeros.
    """
    monthly = _load_monthly_cat_raw(site, session_factory)
    cat_set = set(categories)

    if monthly.empty:
        zero = json.dumps([0] * n_months)
        return {cat: zero for cat in categories}

    # Build a date-sorted full-range index: find global min/max month
    monthly["ds"] = pd.to_datetime(
        {"year": monthly["YEAR"].astype(int), "month": monthly["MONTH"].astype(int), "day": 1}
    )
    global_min = monthly["ds"].min()
    global_max = monthly["ds"].max()
    full_range = pd.date_range(global_min, global_max, freq="MS")

    # Pivot: index=ds, columns=category, values=count
    pivot = (
        monthly.groupby(["ds", "INCIDENTCATNAME"])["count"]
        .sum()
        .unstack(fill_value=0)
        .reindex(full_range, fill_value=0)
    )

    result: dict[str, str] = {}
    for cat in categories:
        if cat in pivot.columns:
            series = pivot[cat].tail(n_months)
        else:
            series = pd.Series([0] * n_months)

        # Ensure exactly n_months values; pad left with zeros if fewer rows
        vals = series.tolist()
        if len(vals) < n_months:
            vals = [0] * (n_months - len(vals)) + vals

        result[cat] = json.dumps([int(v) for v in vals])

    return result


# ---------------------------------------------------------------------------
# Pivot construction (exposed for unit tests)
# ---------------------------------------------------------------------------

def _build_quarterly_pivot(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Build a quarterly pivot table from raw incident rows.

    Returns a DataFrame where:
    - Index is a RangeIndex (rows sorted by fiscal quarter)
    - Columns: YEAR, QUARTER, sort_key, <category_cols...>, total
    - Each row represents one fiscal quarter; category columns hold counts.
    """
    if raw.empty:
        return pd.DataFrame()

    grouped = (
        raw.fillna({"INCIDENTCATNAME": "Unknown"})
        .groupby(["YEAR", "QUARTER", "INCIDENTCATNAME"])
        .size()
        .reset_index(name="cnt")
    )

    pivot = grouped.pivot_table(
        index=["YEAR", "QUARTER"],
        columns="INCIDENTCATNAME",
        values="cnt",
        fill_value=0,
        aggfunc="sum",
    ).reset_index()
    pivot.columns.name = None

    cat_cols = [c for c in pivot.columns if c not in ("YEAR", "QUARTER")]
    pivot["total"] = pivot[cat_cols].sum(axis=1)
    pivot["sort_key"] = pivot.apply(
        lambda r: int(r["YEAR"]) * 10 + _FISCAL_ORDER.get(r["QUARTER"], 0), axis=1
    )
    pivot = pivot.sort_values("sort_key").reset_index(drop=True)
    return pivot


# ---------------------------------------------------------------------------
# SHAP / fallback computation (exposed for unit tests)
# ---------------------------------------------------------------------------

def _apply_shap_or_fallback(pivot: pd.DataFrame) -> pd.DataFrame:
    """
    Given a sorted quarterly pivot, return a DataFrame with columns:
    category, impact_score (0–100), current_count, prev_count.

    Uses SHAP if enough quarters are available; otherwise uses proportion share.
    """
    meta_cols = {"YEAR", "QUARTER", "sort_key", "total"}
    cat_cols = [c for c in pivot.columns if c not in meta_cols]

    if len(pivot) < _MIN_QUARTERS_FOR_MODEL:
        latest = pivot.iloc[-1]
        total = max(float(latest["total"]), 1.0)
        records = [
            {
                "category": cat,
                "impact_score": round(float(latest[cat]) / total * 100, 2),
                "current_count": float(latest[cat]),
                "prev_count": float(pivot.iloc[-2][cat]) if len(pivot) >= 2 else 0.0,
            }
            for cat in cat_cols
        ]
        return pd.DataFrame(records)

    X = pivot[cat_cols].iloc[:-1].reset_index(drop=True)
    y = pivot["total"].iloc[1:].reset_index(drop=True)

    if len(X) >= 4:
        X_train, y_train = X.iloc[:-1], y.iloc[:-1]
    else:
        X_train, y_train = X, y

    model = XGBRegressor(
        n_estimators=100, max_depth=2, learning_rate=0.1,
        subsample=0.9, random_state=42, verbosity=0,
    )
    model.fit(X_train, y_train)

    explainer = shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
    X_current = X.iloc[[-1]]
    sv = explainer.shap_values(X_current)
    abs_shap = np.abs(sv[0])

    max_sv = abs_shap.max()
    if max_sv > 0:
        normalised = abs_shap / max_sv * 100
    else:
        fi = model.feature_importances_
        normalised = fi / fi.max() * 100 if fi.max() > 0 else fi

    latest = pivot.iloc[-1]
    prev = pivot.iloc[-2] if len(pivot) >= 2 else pivot.iloc[-1]

    records = [
        {
            "category": cat,
            "impact_score": round(float(normalised[i]), 2),
            "current_count": float(latest[cat]),
            "prev_count": float(prev[cat]),
        }
        for i, cat in enumerate(cat_cols)
    ]
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Trend computation
# ---------------------------------------------------------------------------

def _compute_trend(current: float, prev: float) -> tuple[str, float]:
    """Return (trend, pct_change)."""
    if prev <= 0:
        return ("up" if current > 0 else "flat"), 0.0
    pct = (current - prev) / prev * 100
    if pct > 5:
        return "up", round(pct, 1)
    if pct < -5:
        return "down", round(pct, 1)
    return "flat", round(pct, 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_drivers_for_site(
    site: str,
    quarter: Optional[str] = None,
    n_sparkline_months: int = _DEFAULT_SPARKLINE_MONTHS,
    session_factory=None,
) -> pd.DataFrame:
    """
    Compute risk drivers for a site using SHAP-based attribution.

    Parameters
    ----------
    site              : Site name (SINAME in OL_INCIDENTS).
    quarter           : Target quarter 'YYYY-Qn'.  Defaults to most recent complete.
    n_sparkline_months: How many recent months to include in each driver's sparkline.
    session_factory   : Override SSMSSession (for tests).

    Returns
    -------
    DataFrame sorted by impact_score descending, with columns:
        driver_name, category, impact_score, trend, pct_change_vs_last_qtr,
        sparkline_data (JSON str, e.g. "[2,0,5,3,7,4]"),
        quarter, computed_at.
    """
    raw = _load_quarterly_cat_raw(site, session_factory)
    if raw.empty:
        return pd.DataFrame()

    pivot = _build_quarterly_pivot(raw)
    if pivot.empty:
        return pd.DataFrame()

    # Resolve target quarter
    if quarter:
        year_s, q_s = quarter.split("-")
        row_mask = (pivot["YEAR"] == year_s) & (pivot["QUARTER"] == q_s)
        if row_mask.sum() == 0:
            return pd.DataFrame()
        idx = pivot.index[row_mask][0]
        pivot = pivot.iloc[: idx + 1].copy()

    resolved_quarter = f"{pivot.iloc[-1]['YEAR']}-{pivot.iloc[-1]['QUARTER']}"

    impact_df = _apply_shap_or_fallback(pivot)
    if impact_df.empty:
        return pd.DataFrame()

    # Compute sparklines for every category in one batch DB call
    all_categories = impact_df["category"].tolist()
    sparklines = build_category_sparklines(
        site, all_categories, n_sparkline_months, session_factory
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    records = []
    for _, row in impact_df.iterrows():
        trend, pct = _compute_trend(row["current_count"], row["prev_count"])
        cat = row["category"]
        records.append(
            {
                "driver_name": cat,
                "category": cat,
                "impact_score": row["impact_score"],
                "trend": trend,
                "pct_change_vs_last_qtr": pct,
                "sparkline_data": sparklines.get(cat, json.dumps([0] * n_sparkline_months)),
                "quarter": resolved_quarter,
                "computed_at": now,
            }
        )

    df = pd.DataFrame(records)
    return df.sort_values("impact_score", ascending=False).reset_index(drop=True)
