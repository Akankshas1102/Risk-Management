"""
SHAP-based risk driver attribution.

Builds a quarterly per-category pivot, trains XGBoost (lag-1 category counts → next
quarter total), and explains the most recent quarter's prediction with SHAP values.
Falls back to raw proportion-based impact when data is insufficient (<6 quarters).

Public API
----------
compute_drivers_for_site(site, quarter, session_factory)  -> pd.DataFrame
_build_quarterly_pivot(raw_df)                            -> pd.DataFrame  (for tests)
_apply_shap_or_fallback(pivot)                            -> pd.DataFrame  (for tests)
"""

from __future__ import annotations

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

    # Count per (year, quarter, category)
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

    # Add total and fiscal sort key
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
        # Proportion fallback: impact = share of total in most recent quarter
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

    # Build lag-1 features: X[i] = category counts in quarter i, y[i] = total in i+1
    X = pivot[cat_cols].iloc[:-1].reset_index(drop=True)
    y = pivot["total"].iloc[1:].reset_index(drop=True)

    # Train XGBoost (time-based: leave last row as "current", train on rest)
    if len(X) >= 4:
        X_train, y_train = X.iloc[:-1], y.iloc[:-1]
    else:
        X_train, y_train = X, y

    model = XGBRegressor(
        n_estimators=100,
        max_depth=2,
        learning_rate=0.1,
        subsample=0.9,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    # Compute SHAP on the most recent available row (current quarter)
    explainer = shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
    X_current = X.iloc[[-1]]  # shape (1, n_features)
    sv = explainer.shap_values(X_current)  # shape (1, n_features)
    abs_shap = np.abs(sv[0])               # shape (n_features,)

    # Normalise to 0–100
    max_sv = abs_shap.max()
    if max_sv > 0:
        normalised = abs_shap / max_sv * 100
    else:
        # Fallback to feature importance if all SHAP values are zero
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
    session_factory=None,
) -> pd.DataFrame:
    """
    Compute risk drivers for a site using SHAP-based attribution.

    Parameters
    ----------
    site : Site name (SINAME in OL_INCIDENTS).
    quarter : Target quarter 'YYYY-Qn'.  Defaults to the most recent complete
              quarter available for the site.
    session_factory : Override SSMSSession (for tests).

    Returns
    -------
    DataFrame with columns: driver_name, category, impact_score, trend,
    pct_change_vs_last_qtr, quarter, computed_at.
    Sorted by impact_score descending.
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
        # Truncate pivot to end at the requested quarter
        idx = pivot.index[row_mask][0]
        pivot = pivot.iloc[: idx + 1].copy()

    resolved_quarter = f"{pivot.iloc[-1]['YEAR']}-{pivot.iloc[-1]['QUARTER']}"

    impact_df = _apply_shap_or_fallback(pivot)
    if impact_df.empty:
        return pd.DataFrame()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    records = []
    for _, row in impact_df.iterrows():
        trend, pct = _compute_trend(row["current_count"], row["prev_count"])
        records.append(
            {
                "driver_name": row["category"],
                "category": row["category"],
                "impact_score": row["impact_score"],
                "trend": trend,
                "pct_change_vs_last_qtr": pct,
                "quarter": resolved_quarter,
                "computed_at": now,
            }
        )

    df = pd.DataFrame(records)
    return df.sort_values("impact_score", ascending=False).reset_index(drop=True)
