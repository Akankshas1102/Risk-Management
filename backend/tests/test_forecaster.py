"""
Forecasting unit tests.  No database calls — all tests use synthetic DataFrames.
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.ml.features import _build_lag_features_from_series, _df_to_monthly_series
from app.ml.forecaster import (
    MIN_INCIDENTS,
    MIN_MONTHS,
    _confidence_band,
    _has_sufficient_data,
    _month_to_fiscal_quarter,
    _next_n_quarters_after,
    _zero_predictions,
    predict_next_n_quarters,
    train_prophet,
    train_xgboost,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_series(n_months: int, base: int = 10, noise: bool = True) -> pd.DataFrame:
    """Synthetic monthly [ds, y] series."""
    dates = pd.date_range("2022-01-01", periods=n_months, freq="MS")
    rng = np.random.default_rng(42)
    counts = base + (rng.integers(0, 5, n_months) if noise else np.zeros(n_months))
    return pd.DataFrame({"ds": dates, "y": counts.astype(float)})


def _make_raw_df(n_months: int, base: int = 10) -> pd.DataFrame:
    """Synthetic raw incident row-count DataFrame (YEAR/MONTH columns)."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n_months):
        year = 2022 + i // 12
        month = (i % 12) + 1
        cnt = base + int(rng.integers(0, 5))
        rows.extend([{"YEAR": str(year), "MONTH": month}] * cnt)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Feature building shapes
# ---------------------------------------------------------------------------

class TestFeatureBuilding:
    def test_df_to_monthly_series_shape(self):
        raw = _make_raw_df(24)
        series = _df_to_monthly_series(raw)
        assert list(series.columns) == ["ds", "y"]
        assert len(series) == 24

    def test_df_to_monthly_series_fills_gaps(self):
        """A raw DF missing some months should have those months filled with y=0."""
        raw = pd.DataFrame({"YEAR": ["2023", "2023", "2024"], "MONTH": [1, 3, 1]})
        series = _df_to_monthly_series(raw)
        months = set(series["ds"].dt.month.tolist())
        # Jan 2023 → Mar 2023 → … → Jan 2024 = 13 months
        assert len(series) == 13
        # Feb 2023 was missing; should be 0
        feb_row = series[series["ds"] == pd.Timestamp("2023-02-01")]
        assert feb_row["y"].values[0] == 0

    def test_lag_features_columns(self):
        series = _make_series(24)
        lags = [1, 3, 6, 12]
        df = _build_lag_features_from_series(series, lags)
        for lag in lags:
            assert f"lag_{lag}" in df.columns
        assert "rolling_3m" in df.columns
        assert "rolling_6m" in df.columns
        assert "month_of_year" in df.columns

    def test_lag_features_no_nan(self):
        series = _make_series(30)
        df = _build_lag_features_from_series(series, [1, 3, 6, 12])
        assert df.isnull().sum().sum() == 0

    def test_lag_features_shrinks_by_max_lag(self):
        series = _make_series(30)
        df = _build_lag_features_from_series(series, [1, 3, 6, 12])
        # After dropping NaN rows and rolling windows, max lag=12 means we lose
        # at least 12 rows from the front plus rolling_6m lookback
        assert len(df) <= len(series) - 12

    def test_two_sites_different_lengths(self):
        """Ensure feature builder handles short series without crashing."""
        short = _make_series(15)
        df = _build_lag_features_from_series(short, [1, 3, 6, 12])
        assert "lag_12" in df.columns   # column exists even if few rows remain
        assert len(df) >= 0             # might be empty for very short series


# ---------------------------------------------------------------------------
# 2. Fallback kicks in for low-history sites
# ---------------------------------------------------------------------------

class TestFallbackLogic:
    def test_has_sufficient_data_true(self):
        series = _make_series(24, base=5)  # 24 months, ~120 total incidents
        assert _has_sufficient_data(series)

    def test_has_sufficient_data_false_low_incidents(self):
        series = _make_series(24, base=1, noise=False)   # 24 months, only 24 incidents
        series["y"] = 1.0
        assert not _has_sufficient_data(series)

    def test_has_sufficient_data_false_low_months(self):
        series = _make_series(6, base=20)  # enough incidents but < 12 months
        assert not _has_sufficient_data(series)

    def test_confidence_band_low(self):
        series = _make_series(6)
        assert _confidence_band(series) == "low"

    def test_confidence_band_medium(self):
        series = _make_series(18)
        assert _confidence_band(series) == "medium"

    def test_confidence_band_high(self):
        series = _make_series(30)
        assert _confidence_band(series) == "high"

    def test_zero_predictions_structure(self):
        df = _zero_predictions("TEST_SITE", n=3, band="low")
        assert len(df) == 3
        assert list(df["predicted_count"]) == [0.0, 0.0, 0.0]
        assert all(df["confidence_band"] == "low")
        assert all(df["model_name"] == "none")


# ---------------------------------------------------------------------------
# 3. predict_next_n_quarters returns exactly n rows
# ---------------------------------------------------------------------------

class TestPredictNextNQuarters:
    """
    These tests mock the DB by patching build_site_monthly_series and
    build_bu_monthly_series to return synthetic data, so no DB is required.
    """

    def _run(self, series: pd.DataFrame, n: int = 3) -> pd.DataFrame:
        """Run predict_next_n_quarters with synthetic data injected via monkeypatching."""
        from unittest.mock import patch

        with (
            patch("app.ml.forecaster.build_site_monthly_series", return_value=series),
            patch("app.ml.forecaster.build_bu_monthly_series", return_value=series),
            patch("app.ml.forecaster.get_site_bu", return_value="TEST_BU"),
            patch("app.ml.forecaster._build_lag_features_from_series",
                  side_effect=_build_lag_features_from_series),
        ):
            return predict_next_n_quarters("FAKE_SITE", n=n)

    def test_returns_exactly_n_rows_sufficient_data(self):
        series = _make_series(36, base=8)
        for n in (1, 2, 3, 4):
            df = self._run(series, n=n)
            assert len(df) == n, f"Expected {n} rows, got {len(df)}"

    def test_returns_n_rows_insufficient_data(self):
        """Low-history site triggers BU fallback but still returns n rows."""
        short = _make_series(8, base=2)
        df = self._run(short, n=3)
        assert len(df) == 3

    def test_columns_present(self):
        series = _make_series(30, base=8)
        df = self._run(series, n=3)
        for col in ("target_quarter", "predicted_count", "lower_ci", "upper_ci",
                    "model_name", "confidence_band"):
            assert col in df.columns, f"Missing column: {col}"

    def test_predicted_count_non_negative(self):
        series = _make_series(30, base=8)
        df = self._run(series, n=3)
        assert (df["predicted_count"] >= 0).all()
        assert (df["lower_ci"] >= 0).all()

    def test_upper_ci_gte_predicted(self):
        series = _make_series(30, base=8)
        df = self._run(series, n=3)
        # upper_ci should be >= predicted_count for all rows
        assert (df["upper_ci"] >= df["predicted_count"]).all()

    def test_target_quarters_are_distinct(self):
        series = _make_series(30, base=8)
        df = self._run(series, n=4)
        assert len(df["target_quarter"].unique()) == 4

    def test_fallback_confidence_band_is_low(self):
        """Sites with insufficient data must always return confidence_band='low'."""
        short = _make_series(6, base=2)
        df = self._run(short, n=3)
        assert all(df["confidence_band"] == "low")


# ---------------------------------------------------------------------------
# 4. Quarter utilities
# ---------------------------------------------------------------------------

class TestQuarterUtils:
    def test_month_to_fiscal_quarter(self):
        assert _month_to_fiscal_quarter(2024, 1) == "2024-Q4"   # Jan → Q4
        assert _month_to_fiscal_quarter(2024, 4) == "2024-Q1"   # Apr → Q1
        assert _month_to_fiscal_quarter(2024, 7) == "2024-Q2"   # Jul → Q2
        assert _month_to_fiscal_quarter(2024, 10) == "2024-Q3"  # Oct → Q3

    def test_next_n_quarters_count(self):
        ts = pd.Timestamp("2026-03-01")  # end of Q4 2026 (Jan-Mar)
        qs = _next_n_quarters_after(ts, 3)
        assert len(qs) == 3
        assert qs[0] == "2026-Q1"  # Apr–Jun 2026

    def test_next_n_quarters_no_duplicates(self):
        ts = pd.Timestamp("2025-12-01")
        qs = _next_n_quarters_after(ts, 5)
        assert len(set(qs)) == 5


# ---------------------------------------------------------------------------
# 5. Model training (lightweight smoke tests, no DB)
# ---------------------------------------------------------------------------

class TestModelTraining:
    def test_prophet_trains_on_sufficient_data(self):
        series = _make_series(30, base=5)
        result = train_prophet(series)
        assert result["success"], result.get("error")
        assert result["rmse"] >= 0
        assert result["n_training"] > 0

    def test_prophet_fails_gracefully_on_tiny_series(self):
        tiny = _make_series(4)
        result = train_prophet(tiny)
        assert not result["success"]
        assert "error" in result

    def test_xgboost_trains_on_sufficient_data(self):
        series = _make_series(36, base=5)
        features = _build_lag_features_from_series(series, [1, 3, 6, 12])
        result = train_xgboost(features)
        assert result["success"], result.get("error")
        assert result["rmse"] >= 0

    def test_xgboost_fails_gracefully_on_tiny_features(self):
        tiny = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=3, freq="MS"),
                              "y": [1.0, 2.0, 3.0],
                              "lag_1": [0, 1, 2],
                              "month_of_year": [1, 2, 3],
                              "quarter_num": [1, 1, 1],
                              "rolling_3m": [0, 0, 0],
                              "rolling_6m": [0, 0, 0]})
        result = train_xgboost(tiny)
        assert not result["success"]
