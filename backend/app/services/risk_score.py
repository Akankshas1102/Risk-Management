"""
Risk score computation utilities.

Pure-math functions imported by ``pipeline_steps.step_risk_scores()`` to
compute composite site risk scores from an ``ol_incidents`` DataFrame.

Quarter labelling and chronology: every helper that needs a quarter label,
sort key, or "previous quarter" delegates to ``app.lib.quarters`` (the
single source of truth).  This module never builds quarter strings itself.
"""

import math

import pandas as pd

from app.lib import quarters as Q


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, float] = {"high": 3.0, "medium": 2.0, "low": 1.0}

_DEFAULT_WEIGHTS: dict[str, float] = {
    "w_frequency": 0.35,
    "w_severity": 0.30,
    "w_velocity": 0.20,
    "w_diversity": 0.15,
}


# ---------------------------------------------------------------------------
# Quarter helpers — thin wrappers over app.lib.quarters
# ---------------------------------------------------------------------------

def _quarter_sort_key(quarter_str: str) -> int:
    """Sort key for fiscal labels (chronological)."""
    return Q.sort_key(quarter_str)


def _prev_quarter_label(label: str) -> str:
    return Q.previous_label(label)


def _current_quarter_str() -> str:
    return Q.current_label()


# ---------------------------------------------------------------------------
# Min-max normalisation helper
# ---------------------------------------------------------------------------

def _minmax(values: dict[str, float], single_site_default: float = 0.5) -> dict[str, float]:
    if len(values) <= 1:
        return {s: single_site_default for s in values}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {s: single_site_default for s in values}
    return {s: (v - lo) / (hi - lo) for s, v in values.items()}


# ---------------------------------------------------------------------------
# Sub-index functions
# ---------------------------------------------------------------------------
# Each takes the FULL DataFrame plus the canonical quarter label (e.g.
# '2025-Q4').  The DataFrame must have a column ``quarter_str`` already
# normalised to the canonical label — pipeline_steps.step_risk_scores adds
# it via Q.csv_to_label().
# ---------------------------------------------------------------------------

def compute_frequency_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """Incident count per site, min-max normalised within the quarter."""
    all_sites = set(df["site_name"].dropna().unique())
    q_df = df[df["quarter_str"] == quarter]
    counts: dict[str, float] = q_df.groupby("site_name").size().to_dict()
    for site in all_sites:
        counts.setdefault(site, 0.0)
    return _minmax(counts)


def compute_severity_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """Weighted severity sum per site (High=3, Medium=2, Low=1), min-max normalised."""
    all_sites = set(df["site_name"].dropna().unique())
    q_df = df[df["quarter_str"] == quarter].copy()
    q_df["_w"] = q_df["severity"].map(SEVERITY_WEIGHTS).fillna(1.0)
    sev_sums: dict[str, float] = q_df.groupby("site_name")["_w"].sum().to_dict()
    for site in all_sites:
        sev_sums.setdefault(site, 0.0)
    return _minmax(sev_sums)


def compute_velocity_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """
    Quarter-over-quarter growth, clipped to [-1, 1] then scaled to [0, 1],
    then min-max normalised within the peer group.
    """
    all_sites = set(df["site_name"].dropna().unique())
    prev_q = Q.previous_label(quarter)

    cur_counts = df[df["quarter_str"] == quarter].groupby("site_name").size().to_dict()
    prev_counts = df[df["quarter_str"] == prev_q].groupby("site_name").size().to_dict()

    raw: dict[str, float] = {}
    for site in all_sites:
        cur = cur_counts.get(site, 0)
        prev = prev_counts.get(site, 0)
        if prev == 0 and cur == 0:
            raw[site] = 0.0
        elif prev == 0:
            raw[site] = 1.0
        else:
            raw[site] = (cur - prev) / prev

    clipped = {s: max(-1.0, min(1.0, v)) for s, v in raw.items()}
    scaled = {s: (v + 1.0) / 2.0 for s, v in clipped.items()}
    return _minmax(scaled)


def compute_diversity_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """Shannon entropy of incident categories per site, min-max normalised."""
    all_sites = set(df["site_name"].dropna().unique())
    q_df = df[df["quarter_str"] == quarter]

    entropies: dict[str, float] = {}
    for site in all_sites:
        site_df = q_df[q_df["site_name"] == site]
        if site_df.empty:
            entropies[site] = 0.0
            continue
        probs = site_df["incident_category"].value_counts(normalize=True)
        entropies[site] = -sum(p * math.log(p) for p in probs if p > 0)
    return _minmax(entropies)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_RISK_BANDS: list[tuple[float, str]] = [
    (40.0, "Low"),
    (65.0, "Medium"),
    (85.0, "High"),
    (100.0, "Critical"),
]


def _score_to_level(score: float) -> str:
    for threshold, label in _RISK_BANDS:
        if score <= threshold:
            return label
    return "Critical"
