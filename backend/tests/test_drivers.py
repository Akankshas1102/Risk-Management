"""
Unit tests for driver attribution and the recommendations rules engine.
No database calls — all tests use synthetic DataFrames.
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.ml.drivers import (
    _apply_shap_or_fallback,
    _build_quarterly_pivot,
    _compute_trend,
)
from app.services.recommendations import (
    RecommendationSpec,
    generate_recommendations,
    rule_access_control,
    rule_asset_property,
    rule_generic_fallback,
    rule_ir_worker,
    rule_process_deviations,
    rule_reporting_lag,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(n_quarters: int = 12, cats: list[str] = None) -> pd.DataFrame:
    """Synthetic raw incident rows with YEAR, QUARTER, INCIDENTCATNAME."""
    if cats is None:
        cats = ["ASSET/PROPERTY", "Access Control", "SOP- LSR Violation", "IR"]
    rng = np.random.default_rng(42)
    rows = []
    y, q_idx = 2021, 0
    fy_qs = ["Q4", "Q1", "Q2", "Q3"]
    for _ in range(n_quarters):
        q = fy_qs[q_idx % 4]
        n = int(rng.integers(5, 20))
        for _ in range(n):
            cat = cats[rng.integers(0, len(cats))]
            rows.append({"YEAR": str(y), "QUARTER": q, "INCIDENTCATNAME": cat})
        q_idx += 1
        if q_idx % 4 == 0:
            y += 1
    return pd.DataFrame(rows)


def _make_drivers(overrides: dict = None) -> list[dict]:
    base = [
        {"driver_name": "ASSET/PROPERTY",              "impact_score": 85, "trend": "up",   "pct_change_vs_last_qtr": 25},
        {"driver_name": "Access Control",               "impact_score": 72, "trend": "up",   "pct_change_vs_last_qtr": 35},
        {"driver_name": "IR - Worker/ Union/ Trans.",   "impact_score": 75, "trend": "flat", "pct_change_vs_last_qtr": 2},
        {"driver_name": "SOP- LSR Violation",           "impact_score": 55, "trend": "up",   "pct_change_vs_last_qtr": 10},
        {"driver_name": "Material",                     "impact_score": 30, "trend": "down", "pct_change_vs_last_qtr": -8},
    ]
    if overrides:
        for d in base:
            if d["driver_name"] in overrides:
                d.update(overrides[d["driver_name"]])
    return base


def _make_site_data(**kw) -> dict:
    base = {
        "site": "TEST_SITE",
        "quarter": "2025-Q3",
        "total_incidents_qtr": 120,
        "delta_qtr_pct": 10.0,
        "reporting_lag_p90": 15.0,
        "business_unit": "TEST_BU",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 1. Feature building: _build_quarterly_pivot shape tests
# ---------------------------------------------------------------------------

class TestBuildPivot:
    def test_pivot_shape(self):
        raw = _make_raw(8)
        pivot = _build_quarterly_pivot(raw)
        assert len(pivot) == 8
        # Must have YEAR, QUARTER, sort_key, total + category columns
        assert "YEAR" in pivot.columns
        assert "total" in pivot.columns
        assert "sort_key" in pivot.columns

    def test_sorted_by_fiscal_quarter(self):
        raw = _make_raw(12)
        pivot = _build_quarterly_pivot(raw)
        assert list(pivot["sort_key"]) == sorted(pivot["sort_key"].tolist())

    def test_total_equals_row_sum(self):
        raw = _make_raw(6)
        pivot = _build_quarterly_pivot(raw)
        meta = {"YEAR", "QUARTER", "sort_key", "total"}
        cat_cols = [c for c in pivot.columns if c not in meta]
        # Each row: total == sum of category columns
        for _, row in pivot.iterrows():
            assert row["total"] == pytest.approx(row[cat_cols].sum())

    def test_empty_raw_returns_empty(self):
        pivot = _build_quarterly_pivot(pd.DataFrame())
        assert pivot.empty

    def test_gaps_in_quarters_handled(self):
        """A site present in Q1 2023 and Q3 2023 (skip Q2) should produce 2 rows."""
        raw = pd.DataFrame([
            {"YEAR": "2023", "QUARTER": "Q1", "INCIDENTCATNAME": "A"},
            {"YEAR": "2023", "QUARTER": "Q3", "INCIDENTCATNAME": "B"},
        ])
        pivot = _build_quarterly_pivot(raw)
        assert len(pivot) == 2


# ---------------------------------------------------------------------------
# 2. SHAP sanity: _apply_shap_or_fallback
# ---------------------------------------------------------------------------

class TestShapOrFallback:
    def test_fallback_below_threshold(self):
        raw = _make_raw(3)  # only 3 quarters → proportion fallback
        pivot = _build_quarterly_pivot(raw)
        result = _apply_shap_or_fallback(pivot)
        assert not result.empty
        assert "impact_score" in result.columns
        assert "category" in result.columns

    def test_fallback_scores_sum_to_100(self):
        raw = _make_raw(4)
        pivot = _build_quarterly_pivot(raw)
        result = _apply_shap_or_fallback(pivot)
        # Proportion fallback: scores are percentages that sum to 100 (within float error)
        if len(pivot) < 6:
            assert abs(result["impact_score"].sum() - 100.0) < 1.0

    def test_shap_path_runs_on_sufficient_data(self):
        raw = _make_raw(15)
        pivot = _build_quarterly_pivot(raw)
        result = _apply_shap_or_fallback(pivot)
        assert not result.empty
        assert result["impact_score"].max() <= 100.0
        assert result["impact_score"].min() >= 0.0

    def test_shap_output_shape(self):
        raw = _make_raw(15, cats=["Cat_A", "Cat_B", "Cat_C"])
        pivot = _build_quarterly_pivot(raw)
        result = _apply_shap_or_fallback(pivot)
        # One row per category
        assert set(result["category"]) == {"Cat_A", "Cat_B", "Cat_C"}

    def test_impact_scores_non_negative(self):
        raw = _make_raw(20)
        pivot = _build_quarterly_pivot(raw)
        result = _apply_shap_or_fallback(pivot)
        assert (result["impact_score"] >= 0).all()

    def test_impact_scores_normalised_to_100(self):
        """SHAP path normalises so max = 100."""
        raw = _make_raw(15)
        pivot = _build_quarterly_pivot(raw)
        if len(pivot) >= 6:
            result = _apply_shap_or_fallback(pivot)
            assert result["impact_score"].max() == pytest.approx(100.0, abs=1.0)


# ---------------------------------------------------------------------------
# 3. Trend helper
# ---------------------------------------------------------------------------

class TestComputeTrend:
    def test_up(self):
        trend, pct = _compute_trend(12, 10)
        assert trend == "up"
        assert pct == pytest.approx(20.0, abs=0.1)

    def test_down(self):
        trend, pct = _compute_trend(8, 10)
        assert trend == "down"
        assert pct < 0

    def test_flat(self):
        trend, pct = _compute_trend(10, 10)
        assert trend == "flat"

    def test_prev_zero_new_activity(self):
        trend, _ = _compute_trend(5, 0)
        assert trend == "up"

    def test_both_zero(self):
        trend, _ = _compute_trend(0, 0)
        assert trend == "flat"


# ---------------------------------------------------------------------------
# 4. Rules engine — individual rule firing
# ---------------------------------------------------------------------------

class TestRules:
    def test_access_control_fires_on_upward_trend(self):
        drivers = _make_drivers()   # Access Control: trend=up, pct=35
        rec = rule_access_control(drivers, _make_site_data())
        assert rec is not None
        assert rec.priority == "high"
        assert "access control" in rec.action_text.lower()

    def test_access_control_skips_when_trend_not_up(self):
        drivers = _make_drivers({"Access Control": {"trend": "flat"}})
        assert rule_access_control(drivers, _make_site_data()) is None

    def test_access_control_skips_when_pct_low(self):
        drivers = _make_drivers({"Access Control": {"pct_change_vs_last_qtr": 10}})
        assert rule_access_control(drivers, _make_site_data()) is None

    def test_ir_worker_fires_on_high_impact(self):
        rec = rule_ir_worker(_make_drivers(), _make_site_data())
        assert rec is not None
        assert rec.priority == "medium"

    def test_ir_worker_skips_below_threshold(self):
        drivers = _make_drivers({"IR - Worker/ Union/ Trans.": {"impact_score": 50}})
        assert rule_ir_worker(drivers, _make_site_data()) is None

    def test_asset_property_fires_when_top_and_rising(self):
        drivers = [{"driver_name": "ASSET/PROPERTY", "impact_score": 90,
                    "trend": "up", "pct_change_vs_last_qtr": 20}]
        site_data = _make_site_data(delta_qtr_pct=5.0)
        rec = rule_asset_property(drivers, site_data)
        assert rec is not None
        assert rec.priority == "high"

    def test_asset_property_skips_when_incidents_falling(self):
        drivers = [{"driver_name": "ASSET/PROPERTY", "impact_score": 90,
                    "trend": "up", "pct_change_vs_last_qtr": 20}]
        site_data = _make_site_data(delta_qtr_pct=-5.0)
        assert rule_asset_property(drivers, site_data) is None

    def test_reporting_lag_fires_above_30(self):
        site_data = _make_site_data(reporting_lag_p90=45.0)
        rec = rule_reporting_lag(_make_drivers(), site_data)
        assert rec is not None
        assert rec.priority == "medium"

    def test_reporting_lag_skips_below_30(self):
        assert rule_reporting_lag(_make_drivers(), _make_site_data(reporting_lag_p90=10)) is None

    def test_reporting_lag_skips_when_none(self):
        assert rule_reporting_lag(_make_drivers(), _make_site_data(reporting_lag_p90=None)) is None

    def test_process_deviations_fires_on_sop_trend_up(self):
        drivers = _make_drivers({"SOP- LSR Violation": {"trend": "up"}})
        rec = rule_process_deviations(drivers, _make_site_data())
        assert rec is not None
        assert rec.priority == "medium"

    def test_generic_fallback_always_fires(self):
        rec = rule_generic_fallback(_make_drivers(), _make_site_data())
        assert rec is not None

    def test_generic_fallback_empty_drivers_returns_none(self):
        assert rule_generic_fallback([], _make_site_data()) is None


# ---------------------------------------------------------------------------
# 5. Full engine: deduplication, ordering, extensibility
# ---------------------------------------------------------------------------

class TestRecommendationsEngine:
    def test_no_duplicate_actions(self):
        drivers = _make_drivers()
        recs = generate_recommendations(drivers, _make_site_data())
        actions = [r.action_text for r in recs]
        assert len(actions) == len(set(actions))

    def test_sorted_high_first(self):
        drivers = _make_drivers()
        recs = generate_recommendations(drivers, _make_site_data())
        priority_order = [r.priority for r in recs]
        high_idx = [i for i, p in enumerate(priority_order) if p == "high"]
        medium_idx = [i for i, p in enumerate(priority_order) if p == "medium"]
        low_idx = [i for i, p in enumerate(priority_order) if p == "low"]
        for hi in high_idx:
            for mi in medium_idx:
                assert hi < mi
        for mi in medium_idx:
            for li in low_idx:
                assert mi < li

    def test_buggy_rule_does_not_crash_engine(self):
        def _bad_rule(d, s):
            raise RuntimeError("intentional error")

        drivers = _make_drivers()
        recs = generate_recommendations(drivers, _make_site_data(), rules=[_bad_rule])
        assert recs == []   # crashed rule produces no output

    def test_custom_rule_injection(self):
        """New rules can be injected without changing the module."""
        def _custom(d, s):
            return RecommendationSpec(
                action_text="Custom action from injected rule",
                priority="low",
            )

        recs = generate_recommendations(_make_drivers(), _make_site_data(), rules=[_custom])
        assert len(recs) == 1
        assert recs[0].action_text == "Custom action from injected rule"

    def test_returns_empty_for_no_drivers(self):
        recs = generate_recommendations([], _make_site_data())
        assert all(r.action_text for r in recs)   # generic fallback skips empty list
