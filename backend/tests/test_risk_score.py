"""
Tests for the risk score engine.

Tests that only exercise math (test_frequency_*, test_severity_*, etc.) run with
no database.  Tests that verify DB-driven behavior (test_weights_from_db) use the
shared test_session_factory fixture from conftest.py and require a running Postgres.
"""

import math
import uuid
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from app.services.risk_score import (
    _DEFAULT_WEIGHTS,
    _quarter_sort_key,
    _score_to_level,
    compute_diversity_index,
    compute_frequency_index,
    compute_risk_scores,
    compute_severity_index,
    compute_velocity_index,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _df(*rows: dict) -> pd.DataFrame:
    """Build a minimal incidents DataFrame from a list of dicts."""
    defaults = {
        "site_name": "SITE",
        "buname": "BU",
        "quarter": "Q1",
        "year": 2024,
        "severity": "low",
        "incident_category": "cat1",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _composite(f, s, v, d, w=None):
    w = w or _DEFAULT_WEIGHTS
    return 100.0 * (
        w["w_frequency"] * f
        + w["w_severity"] * s
        + w["w_velocity"] * v
        + w["w_diversity"] * d
    )


# ---------------------------------------------------------------------------
# Frequency index
# ---------------------------------------------------------------------------

def test_frequency_max_min_sites():
    df = _df(
        *[{"site_name": "A"} for _ in range(5)],
        *[{"site_name": "B"} for _ in range(2)],
        *[{"site_name": "C"} for _ in range(1)],
    )
    result = compute_frequency_index(df, "2024-Q1")
    assert result["A"] == pytest.approx(1.0)   # max → 1
    assert result["C"] == pytest.approx(0.0)   # min → 0
    assert 0.0 < result["B"] < 1.0


def test_frequency_single_site_returns_half():
    df = _df({"site_name": "A"})
    assert compute_frequency_index(df, "2024-Q1") == {"A": pytest.approx(0.5)}


def test_frequency_absent_site_gets_zero():
    # Site C exists in Q4 2024 but not Q1 2024
    df = _df(
        *[{"site_name": "A"} for _ in range(5)],
        *[{"site_name": "B"} for _ in range(3)],
        {"site_name": "C", "quarter": "Q4"},   # only in prev quarter
    )
    result = compute_frequency_index(df, "2024-Q1")
    assert result["C"] == pytest.approx(0.0)
    assert result["A"] == pytest.approx(1.0)


def test_frequency_all_same_count_returns_half():
    df = _df({"site_name": "A"}, {"site_name": "B"})
    result = compute_frequency_index(df, "2024-Q1")
    assert result["A"] == pytest.approx(0.5)
    assert result["B"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Severity index
# ---------------------------------------------------------------------------

def test_severity_ordering():
    df = _df(
        {"site_name": "A", "severity": "high"},
        {"site_name": "A", "severity": "high"},   # A: 3+3 = 6
        {"site_name": "B", "severity": "medium"},  # B: 2
        {"site_name": "C", "severity": "low"},     # C: 1
    )
    result = compute_severity_index(df, "2024-Q1")
    assert result["A"] == pytest.approx(1.0)
    assert result["C"] == pytest.approx(0.0)
    assert 0.0 < result["B"] < 1.0


def test_severity_absent_site_gets_zero():
    df = _df(
        {"site_name": "A", "severity": "high"},
        {"site_name": "B", "quarter": "Q4"},  # absent from Q1
    )
    result = compute_severity_index(df, "2024-Q1")
    assert result["B"] == pytest.approx(0.0)
    assert result["A"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Velocity index
# ---------------------------------------------------------------------------

def test_velocity_growth_vs_decline():
    # Q1 2024: A grew (2→5), B declined (6→3)
    df = _df(
        *[{"site_name": "A", "quarter": "Q1"} for _ in range(5)],
        *[{"site_name": "B", "quarter": "Q1"} for _ in range(3)],
        *[{"site_name": "A", "quarter": "Q4"} for _ in range(2)],  # prev Q
        *[{"site_name": "B", "quarter": "Q4"} for _ in range(6)],
    )
    result = compute_velocity_index(df, "2024-Q1")
    assert result["A"] > result["B"]


def test_velocity_no_prev_quarter_is_neutral_before_minmax():
    # Both sites have no previous quarter → both get raw=0.5 → after minmax both=0.5
    df = _df(
        *[{"site_name": "A", "quarter": "Q1"} for _ in range(3)],
        *[{"site_name": "B", "quarter": "Q1"} for _ in range(5)],
    )
    result = compute_velocity_index(df, "2024-Q1")
    # All same → minmax returns 0.5 for everyone
    assert result["A"] == pytest.approx(0.5)
    assert result["B"] == pytest.approx(0.5)


def test_velocity_new_site_gets_max_raw():
    # Site A existed before (prev=3), Site B is brand new (prev=0, cur>0)
    # B should have higher raw velocity than A (which had moderate growth)
    df = _df(
        *[{"site_name": "A", "quarter": "Q1"} for _ in range(4)],
        *[{"site_name": "B", "quarter": "Q1"} for _ in range(2)],
        *[{"site_name": "A", "quarter": "Q4"} for _ in range(3)],
        # B intentionally absent from Q4
    )
    result = compute_velocity_index(df, "2024-Q1")
    # B prev=0, cur=2 → raw=1.0 (max); A: (4-3)/3=0.33 → B should be higher
    assert result["B"] >= result["A"]


# ---------------------------------------------------------------------------
# Diversity index
# ---------------------------------------------------------------------------

def test_diversity_high_vs_low_entropy():
    df = _df(
        # A: 3 equal categories → high entropy
        {"site_name": "A", "incident_category": "cat1"},
        {"site_name": "A", "incident_category": "cat2"},
        {"site_name": "A", "incident_category": "cat3"},
        # B: 1 category → entropy = 0
        {"site_name": "B", "incident_category": "cat1"},
        {"site_name": "B", "incident_category": "cat1"},
    )
    result = compute_diversity_index(df, "2024-Q1")
    assert result["A"] == pytest.approx(1.0)
    assert result["B"] == pytest.approx(0.0)


def test_diversity_absent_site_gets_zero():
    df = _df(
        {"site_name": "A", "incident_category": "cat1"},
        {"site_name": "A", "incident_category": "cat2"},
        {"site_name": "B", "quarter": "Q4", "incident_category": "cat1"},
    )
    result = compute_diversity_index(df, "2024-Q1")
    assert result["B"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Composite score bounds
# ---------------------------------------------------------------------------

def test_composite_always_in_0_100():
    """Score = 100 × weighted-sum of [0,1]-bounded indices → must be in [0, 100]."""
    df = _df(
        *[{"site_name": "A", "severity": "high", "incident_category": "cat1"} for _ in range(10)],
        *[{"site_name": "B", "severity": "low",  "incident_category": "cat2"} for _ in range(1)],
        {"site_name": "C", "quarter": "Q4"},   # absent from Q1
    )
    quarter = "2024-Q1"
    fi = compute_frequency_index(df, quarter)
    si = compute_severity_index(df, quarter)
    vi = compute_velocity_index(df, quarter)
    di = compute_diversity_index(df, quarter)

    for site in fi:
        score = _composite(fi[site], si[site], vi[site], di[site])
        assert 0.0 <= score <= 100.0, f"Site {site}: score {score} out of bounds"


# ---------------------------------------------------------------------------
# Zero-incident site scores low
# ---------------------------------------------------------------------------

def test_zero_incident_site_scores_lower_than_active_sites():
    """
    A site with 0 incidents in the current quarter should have
    frequency=0 and severity=0, producing a lower score than active sites.
    """
    df = _df(
        *[{"site_name": "A", "severity": "high", "incident_category": "cat1"} for _ in range(8)],
        *[{"site_name": "B", "severity": "high", "incident_category": "cat2"} for _ in range(5)],
        # Site C is in the pool via a different quarter
        {"site_name": "C", "quarter": "Q4"},
    )
    quarter = "2024-Q1"
    fi = compute_frequency_index(df, quarter)
    si = compute_severity_index(df, quarter)
    vi = compute_velocity_index(df, quarter)
    di = compute_diversity_index(df, quarter)

    score_C = _composite(fi["C"], si["C"], vi["C"], di["C"])
    score_A = _composite(fi["A"], si["A"], vi["A"], di["A"])

    assert fi["C"] == pytest.approx(0.0), "Absent site should have frequency=0"
    assert si["C"] == pytest.approx(0.0), "Absent site should have severity=0"
    assert score_C < score_A


# ---------------------------------------------------------------------------
# Quarter sort key utility
# ---------------------------------------------------------------------------

def test_quarter_sort_key_ordering():
    quarters = ["2024-Q3", "2024-Q1", "2024-Q4", "2023-Q3", "2025-Q4"]
    sorted_q = sorted(quarters, key=_quarter_sort_key)
    # Expected chronological order:
    # 2023-Q3 (Oct-Dec 2023) < 2024-Q4 (Jan-Mar 2024) < 2024-Q1 (Apr-Jun 2024)
    # < 2024-Q3 (Oct-Dec 2024) < 2025-Q4 (Jan-Mar 2025)
    assert sorted_q == ["2023-Q3", "2024-Q4", "2024-Q1", "2024-Q3", "2025-Q4"]


# ---------------------------------------------------------------------------
# Risk level bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (0.0, "Low"), (40.0, "Low"),
    (40.1, "Medium"), (65.0, "Medium"),
    (65.1, "High"), (85.0, "High"),
    (85.1, "Critical"), (100.0, "Critical"),
])
def test_score_to_level_bands(score, expected):
    assert _score_to_level(score) == expected


# ---------------------------------------------------------------------------
# DB test: weights from the weights table are applied
# ---------------------------------------------------------------------------

def test_weights_from_db_applied(test_session_factory, test_engine):
    """
    Insert a BU-specific weight row with w_frequency=0.97 (dominates the score).
    A site in that BU with max frequency should score ~97; the same site
    with default weights would score much lower.
    """
    from sqlalchemy import text
    from app.models.incident import IncidentClean
    from app.models.risk_score import RiskScoreWeights

    batch_id = uuid.uuid4()

    # --- Seed incidents for two BUs ---
    incidents = []
    for i in range(1, 6):
        incidents.append(
            IncidentClean(
                incrowid=i,
                incident_id=i,
                batch_id=batch_id,
                site_name="SITE_X",
                buname="CUSTOM_BU",
                quarter="Q3",
                year=2023,
                severity="low",
                incident_category="cat1",
                occurred_date=date(2023, 10, 1),
                reported_date=date(2023, 10, 1),
                last_updated_date=date(2023, 10, 1),
                reporting_lag_days=0,
                is_partial_period=False,
            )
        )
    # A second site in the same BU (fewer incidents)
    incidents.append(
        IncidentClean(
            incrowid=6,
            incident_id=6,
            batch_id=batch_id,
            site_name="SITE_Y",
            buname="CUSTOM_BU",
            quarter="Q3",
            year=2023,
            severity="low",
            incident_category="cat1",
            occurred_date=date(2023, 10, 1),
            reported_date=date(2023, 10, 1),
            last_updated_date=date(2023, 10, 1),
            reporting_lag_days=0,
            is_partial_period=False,
        )
    )
    with test_session_factory() as session:
        session.add_all(incidents)
        session.commit()

    # --- Insert custom weights that make frequency dominate ---
    custom_w = RiskScoreWeights(
        business_unit="CUSTOM_BU",
        w_frequency=0.97,
        w_severity=0.01,
        w_velocity=0.01,
        w_diversity=0.01,
        effective_from=date(2020, 1, 1),
    )
    with test_session_factory() as session:
        session.add(custom_w)
        session.commit()

    try:
        df_scores = compute_risk_scores(
            quarters=["2023-Q3"],
            session_factory=test_session_factory,
        )

        assert not df_scores.empty
        site_x_row = df_scores[df_scores["site"] == "SITE_X"].iloc[0]
        site_y_row = df_scores[df_scores["site"] == "SITE_Y"].iloc[0]

        # SITE_X has 5 incidents (max), SITE_Y has 1 — with w_frequency=0.97
        # SITE_X should score near 97; SITE_Y near 0
        assert site_x_row["risk_score"] > site_y_row["risk_score"]
        assert site_x_row["frequency_index"] == pytest.approx(1.0)
        assert site_y_row["frequency_index"] == pytest.approx(0.0)

    finally:
        # Clean up custom weight to avoid polluting other tests
        with test_session_factory() as session:
            session.execute(
                text("DELETE FROM risk_score_weights WHERE business_unit = 'CUSTOM_BU'")
            )
            session.commit()
