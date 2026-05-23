"""
Risk score computation engine.

Public API
----------
compute_frequency_index(df, quarter)  -> dict[site, float]
compute_severity_index(df, quarter)   -> dict[site, float]
compute_velocity_index(df, quarter)   -> dict[site, float]
compute_diversity_index(df, quarter)  -> dict[site, float]
compute_risk_scores(quarters, ...)    -> pd.DataFrame
persist_risk_scores(df, ...)          -> None

All index functions return values in [0, 1] via min-max normalization
within the quarter's peer group.  The composite score is therefore
bounded to [0, 100] by construction.
"""

import math
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from app.core.database import SessionLocal
from app.models.incident import IncidentClean
from app.models.risk_score import RiskScore, RiskScoreWeights


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

# Fiscal quarter order within a calendar year (chronological):
# Q4 (Jan–Mar) → Q1 (Apr–Jun) → Q2 (Jul–Sep) → Q3 (Oct–Dec)
_FISCAL_ORDER: list[str] = ["Q4", "Q1", "Q2", "Q3"]


# ---------------------------------------------------------------------------
# Quarter utilities
# ---------------------------------------------------------------------------

def _quarter_sort_key(quarter_str: str) -> int:
    """
    Return a sortable integer for fiscal-year quarters.
    '2024-Q4' → 20240, '2024-Q1' → 20241, '2024-Q2' → 20242, '2024-Q3' → 20243.
    Integers are globally comparable across years.
    """
    year_str, q = quarter_str.split("-")
    return int(year_str) * 10 + _FISCAL_ORDER.index(q)


def _prev_quarter(year: int, q: str) -> tuple[int, str]:
    """
    Return the immediately preceding fiscal quarter.
    Q4 of year Y is preceded by Q3 of year Y-1.
    """
    idx = _FISCAL_ORDER.index(q)
    if idx == 0:  # Q4 → look back to Q3 of previous year
        return year - 1, "Q3"
    return year, _FISCAL_ORDER[idx - 1]


def _current_quarter_str() -> str:
    """Return the currently open quarter as 'YYYY-Qn' (fiscal convention)."""
    today = date.today()
    m = today.month
    q = (m - 4) // 3 + 1 if m >= 4 else 4
    return f"{today.year}-Q{q}"


# ---------------------------------------------------------------------------
# Min-max normalization helper
# ---------------------------------------------------------------------------

def _minmax(values: dict[str, float], single_site_default: float = 0.5) -> dict[str, float]:
    """
    Min-max normalize a {site: raw_value} dict to [0, 1].
    Returns `single_site_default` for every site when there is only one site
    or when all values are equal (normalization is undefined in both cases).
    """
    if len(values) <= 1:
        return {s: single_site_default for s in values}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {s: single_site_default for s in values}
    return {s: (v - lo) / (hi - lo) for s, v in values.items()}


# ---------------------------------------------------------------------------
# Sub-index functions  (all accept the FULL df, not just the filtered quarter)
# ---------------------------------------------------------------------------

def compute_frequency_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """
    Incident count per site, min-max normalized within the quarter.
    Sites that have no incidents in this quarter receive a count of 0.
    Single-site quarters return 0.5.

    Parameters
    ----------
    df : full incidents_clean DataFrame (all quarters)
    quarter : 'YYYY-Qn' string
    """
    year_str, q = quarter.split("-")
    year = int(year_str)
    all_sites = set(df["site_name"].dropna().unique())

    q_df = df[(df["year"] == year) & (df["quarter"] == q)]
    counts: dict[str, float] = q_df.groupby("site_name").size().to_dict()
    for site in all_sites:
        counts.setdefault(site, 0.0)

    return _minmax(counts)


def compute_severity_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """
    Weighted severity sum per site (High=3, Medium=2, Low=1), min-max normalized.
    Sites absent from the quarter receive a weighted sum of 0.
    """
    year_str, q = quarter.split("-")
    year = int(year_str)
    all_sites = set(df["site_name"].dropna().unique())

    q_df = df[(df["year"] == year) & (df["quarter"] == q)].copy()
    q_df["_w"] = q_df["severity"].map(SEVERITY_WEIGHTS).fillna(1.0)
    sev_sums: dict[str, float] = q_df.groupby("site_name")["_w"].sum().to_dict()
    for site in all_sites:
        sev_sums.setdefault(site, 0.0)

    return _minmax(sev_sums)


def compute_velocity_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """
    Quarter-over-quarter growth rate, clipped to [-1, 1] then scaled to [0, 1],
    then min-max normalized within the quarter's peer group.

    Sites with no previous-quarter data receive a neutral velocity (raw = 0.0 → 0.5).
    A site new to the data (prev = 0, cur > 0) gets the maximum raw velocity (1.0).
    """
    year_str, q = quarter.split("-")
    year = int(year_str)
    all_sites = set(df["site_name"].dropna().unique())

    prev_year, prev_q = _prev_quarter(year, q)

    cur_counts: dict[str, int] = (
        df[(df["year"] == year) & (df["quarter"] == q)]
        .groupby("site_name").size().to_dict()
    )
    prev_counts: dict[str, int] = (
        df[(df["year"] == prev_year) & (df["quarter"] == prev_q)]
        .groupby("site_name").size().to_dict()
    )

    raw: dict[str, float] = {}
    for site in all_sites:
        cur = cur_counts.get(site, 0)
        prev = prev_counts.get(site, 0)
        if prev == 0 and cur == 0:
            raw[site] = 0.0          # no activity either period → neutral
        elif prev == 0:
            raw[site] = 1.0          # new activity → max growth
        else:
            raw[site] = (cur - prev) / prev

    clipped = {s: max(-1.0, min(1.0, v)) for s, v in raw.items()}
    scaled = {s: (v + 1.0) / 2.0 for s, v in clipped.items()}

    return _minmax(scaled)


def compute_diversity_index(df: pd.DataFrame, quarter: str) -> dict[str, float]:
    """
    Shannon entropy of incident categories per site, min-max normalized.
    Sites with no incidents receive entropy = 0.
    Single-site quarters return 0.5.
    """
    year_str, q = quarter.split("-")
    year = int(year_str)
    all_sites = set(df["site_name"].dropna().unique())

    q_df = df[(df["year"] == year) & (df["quarter"] == q)]

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


def _load_weights(session) -> dict[Any, dict[str, float]]:
    """
    Load active weight rows from risk_score_weights.
    Returns {business_unit: {w_frequency, ...}}.  None key = global default.
    """
    today = date.today()
    rows = session.execute(
        select(RiskScoreWeights)
        .where(
            RiskScoreWeights.effective_from <= today,
            (RiskScoreWeights.effective_to.is_(None))
            | (RiskScoreWeights.effective_to >= today),
        )
        .order_by(RiskScoreWeights.effective_from.desc())
    ).scalars().all()

    weights: dict[Any, dict[str, float]] = {}
    for row in rows:
        bu = row.business_unit  # may be None (global default)
        if bu not in weights:   # keep most-recently-effective row per BU
            weights[bu] = {
                "w_frequency": float(row.w_frequency),
                "w_severity": float(row.w_severity),
                "w_velocity": float(row.w_velocity),
                "w_diversity": float(row.w_diversity),
            }

    if None not in weights:
        weights[None] = _DEFAULT_WEIGHTS.copy()

    return weights


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def compute_risk_scores(
    quarters: list[str] | None = None,
    include_partial: bool = False,
    session_factory: sessionmaker | None = None,
) -> pd.DataFrame:
    """
    Compute composite risk scores for all (or specified) quarters.

    Parameters
    ----------
    quarters : list of 'YYYY-Qn' strings to compute; None = all complete quarters.
    include_partial : if True, also compute the current incomplete quarter.
    session_factory : override SessionLocal (useful in tests).

    Returns
    -------
    DataFrame with columns: site, business_unit, quarter, quarter_sort_key,
    risk_score, risk_level, frequency_index, severity_index, velocity_index,
    diversity_index.
    """
    sf = session_factory or SessionLocal

    # Load incidents_clean from DB
    with sf() as session:
        rows = session.execute(
            select(
                IncidentClean.site_name,
                IncidentClean.buname,
                IncidentClean.quarter,
                IncidentClean.year,
                IncidentClean.severity,
                IncidentClean.incident_category,
            )
        ).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["site_name", "buname", "quarter", "year", "severity", "incident_category"],
    )
    df["quarter_str"] = df["year"].astype(str) + "-" + df["quarter"]

    available = sorted(df["quarter_str"].unique(), key=_quarter_sort_key)

    if not include_partial:
        current_q = _current_quarter_str()
        available = [q for q in available if q != current_q]

    if quarters is not None:
        available = [q for q in available if q in quarters]

    if not available:
        return pd.DataFrame()

    # Load weights
    with sf() as session:
        weights_map = _load_weights(session)

    # Site → dominant business unit
    site_bu: dict[str, str | None] = (
        df.groupby("site_name")["buname"]
        .agg(lambda x: x.mode().iloc[0] if len(x.mode()) else None)
        .to_dict()
    )

    results: list[dict] = []
    for qstr in available:
        f_idx = compute_frequency_index(df, qstr)
        sev_idx = compute_severity_index(df, qstr)
        vel_idx = compute_velocity_index(df, qstr)
        div_idx = compute_diversity_index(df, qstr)

        for site in f_idx:
            bu = site_bu.get(site)
            w = weights_map.get(bu) or weights_map.get(None) or _DEFAULT_WEIGHTS

            fi = f_idx[site]
            si = sev_idx.get(site, 0.5)
            vi = vel_idx.get(site, 0.5)
            di = div_idx.get(site, 0.5)

            score = 100.0 * (
                w["w_frequency"] * fi
                + w["w_severity"] * si
                + w["w_velocity"] * vi
                + w["w_diversity"] * di
            )
            score = round(max(0.0, min(100.0, score)), 4)

            results.append(
                {
                    "site": site,
                    "business_unit": bu,
                    "quarter": qstr,
                    "quarter_sort_key": _quarter_sort_key(qstr),
                    "risk_score": score,
                    "risk_level": _score_to_level(score),
                    "frequency_index": round(fi, 6),
                    "severity_index": round(si, 6),
                    "velocity_index": round(vi, 6),
                    "diversity_index": round(di, 6),
                }
            )

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_risk_scores(
    df: pd.DataFrame,
    session_factory: sessionmaker | None = None,
) -> None:
    """Upsert risk scores to the risk_scores table (conflict on site + quarter)."""
    if df.empty:
        return

    sf = session_factory or SessionLocal
    computed_at = datetime.now(timezone.utc)

    records = [
        {**row.to_dict(), "computed_at": computed_at}
        for _, row in df.iterrows()
    ]

    stmt = pg_insert(RiskScore.__table__).values(records)
    update_cols = {
        c: stmt.excluded[c]
        for c in records[0]
        if c not in ("site", "quarter")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_risk_scores_site_quarter",
        set_=update_cols,
    )

    with sf() as session:
        session.execute(stmt)
        session.commit()
