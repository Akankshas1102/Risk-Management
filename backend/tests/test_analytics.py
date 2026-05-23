"""
Happy-path integration tests for the analytics API.
These tests hit the real vedanta SQL Server database (OL_INCIDENTS table).
They assert on response structure and sensible values rather than exact counts,
since the underlying data may grow over time.

Run with:
    cd backend && pytest tests/test_analytics.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.ssms import get_ssms_db, SSMSSession

# Use a fixed quarter that is guaranteed to have data in OL_INCIDENTS
_TEST_QUARTER = "2024-Q1"   # Apr-Jun 2024 — confirmed present in the DB
_TEST_SITE = "ENABLING"     # highest-volume site
_TEST_BU = "ALUMINIUM SECTOR"

client = TestClient(app)


def _ok_json(url: str) -> dict | list:
    resp = client.get(url)
    assert resp.status_code == 200, f"{url} → {resp.status_code}: {resp.text[:300]}"
    return resp.json()


# ---------------------------------------------------------------------------
# 1. /api/sites
# ---------------------------------------------------------------------------

def test_sites_returns_list():
    data = _ok_json(f"/api/sites?quarter={_TEST_QUARTER}")
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "site" in first
    assert "incident_count" in first
    assert first["incident_count"] > 0


def test_sites_bu_filter_narrows_results():
    all_sites = _ok_json(f"/api/sites?quarter={_TEST_QUARTER}")
    bu_sites = _ok_json(f"/api/sites?quarter={_TEST_QUARTER}&business_unit={_TEST_BU}")
    assert len(bu_sites) <= len(all_sites)
    if bu_sites:
        assert all(s["business_unit"] == _TEST_BU for s in bu_sites)


# ---------------------------------------------------------------------------
# 2. /api/kpis
# ---------------------------------------------------------------------------

def test_kpis_for_site():
    data = _ok_json(f"/api/kpis?site={_TEST_SITE}&quarter={_TEST_QUARTER}")
    assert data["quarter"] == _TEST_QUARTER
    assert data["site"] == _TEST_SITE
    assert data["total_incidents_qtr"] > 0
    # delta may be None if no previous quarter data; either is valid
    assert data["predicted_next_qtr"] is None   # placeholder
    assert data["confidence_score"] is None      # placeholder


def test_kpis_all_sites():
    data = _ok_json(f"/api/kpis?quarter={_TEST_QUARTER}")
    assert data["total_incidents_qtr"] > 0
    assert data["top_category"] is not None
    assert 0.0 < data["top_category_share"] <= 1.0


def test_kpis_defaults_to_latest_quarter():
    data = _ok_json("/api/kpis")
    assert data["quarter"] is not None
    assert "-Q" in data["quarter"]


# ---------------------------------------------------------------------------
# 3. /api/incidents/by-type
# ---------------------------------------------------------------------------

def test_by_type_returns_known_types():
    data = _ok_json(f"/api/incidents/by-type?quarter={_TEST_QUARTER}")
    types = {d["incident_type"] for d in data}
    assert "SECURITY INCIDENTS" in types
    assert all(d["count"] > 0 for d in data)


def test_by_type_site_filter():
    data = _ok_json(f"/api/incidents/by-type?site={_TEST_SITE}&quarter={_TEST_QUARTER}")
    assert len(data) > 0
    total = sum(d["count"] for d in data)
    # Total for site must be less than or equal to all-sites total
    all_data = _ok_json(f"/api/incidents/by-type?quarter={_TEST_QUARTER}")
    all_total = sum(d["count"] for d in all_data)
    assert total <= all_total


# ---------------------------------------------------------------------------
# 4. /api/incidents/by-category
# ---------------------------------------------------------------------------

def test_by_category_max_16_items():
    data = _ok_json(f"/api/incidents/by-category?quarter={_TEST_QUARTER}")
    # At most 15 named + 1 "Other"
    assert len(data) <= 16
    categories = [d["category"] for d in data]
    assert len(set(categories)) == len(categories)  # no duplicates


def test_by_category_counts_sum_correctly():
    all_cats = _ok_json(f"/api/incidents/by-category?quarter={_TEST_QUARTER}")
    by_type = _ok_json(f"/api/incidents/by-type?quarter={_TEST_QUARTER}")
    assert sum(d["count"] for d in all_cats) == sum(d["count"] for d in by_type)


# ---------------------------------------------------------------------------
# 5. /api/incidents/by-site
# ---------------------------------------------------------------------------

def test_by_site_returns_list():
    data = _ok_json(f"/api/incidents/by-site?quarter={_TEST_QUARTER}")
    assert isinstance(data, list)
    assert len(data) > 0
    sites = [d["site"] for d in data]
    assert _TEST_SITE in sites


def test_by_site_totals_match_kpis():
    data = _ok_json(f"/api/incidents/by-site?quarter={_TEST_QUARTER}")
    site_count = next((d["count"] for d in data if d["site"] == _TEST_SITE), None)
    kpi = _ok_json(f"/api/kpis?site={_TEST_SITE}&quarter={_TEST_QUARTER}")
    assert site_count == kpi["total_incidents_qtr"]


# ---------------------------------------------------------------------------
# 6. /api/incidents/trend
# ---------------------------------------------------------------------------

def test_trend_returns_time_series():
    data = _ok_json(f"/api/incidents/trend?site={_TEST_SITE}&months=12")
    assert isinstance(data, list)
    assert len(data) > 0
    point = data[0]
    assert "year" in point and "month" in point
    assert "count" in point and "all_sites_avg" in point
    assert point["all_sites_avg"] >= 0
    assert 1 <= point["month"] <= 12


def test_trend_months_param_respected():
    data_12 = _ok_json(f"/api/incidents/trend?site={_TEST_SITE}&months=12")
    data_6 = _ok_json(f"/api/incidents/trend?site={_TEST_SITE}&months=6")
    assert len(data_12) >= len(data_6)


# ---------------------------------------------------------------------------
# 7. /api/incidents/heatmap
# ---------------------------------------------------------------------------

def test_heatmap_returns_scores():
    data = _ok_json(f"/api/incidents/heatmap?quarter={_TEST_QUARTER}")
    assert isinstance(data, list)
    assert len(data) > 0
    point = data[0]
    assert 0.0 <= point["likelihood_score"] <= 1.0
    assert 0.0 <= point["impact_score"] <= 1.0
    assert point["risk_band"] in ("Low", "Medium", "High", "Critical")


def test_heatmap_highest_site_has_max_likelihood():
    data = _ok_json(f"/api/incidents/heatmap?quarter={_TEST_QUARTER}")
    # Sites are returned ordered by frequency desc, so first has max likelihood
    likelihoods = [d["likelihood_score"] for d in data]
    # Max likelihood should be 1.0 (min-max normalization)
    assert max(likelihoods) == pytest.approx(1.0)
    assert min(likelihoods) == pytest.approx(0.0)
