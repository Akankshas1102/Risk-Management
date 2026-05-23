"""
Forecasting engine: Prophet + XGBoost ensemble.

Public API
----------
train_prophet(series_df)            -> dict
train_xgboost(features_df)          -> dict
predict_next_n_quarters(site, n)    -> pd.DataFrame
"""

from __future__ import annotations

import logging
import math
import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from xgboost import XGBRegressor

from app.ml.features import (
    _build_lag_features_from_series,
    build_bu_monthly_series,
    build_lag_features,
    build_site_monthly_series,
    get_site_bu,
)

# Suppress Prophet/Stan verbose output
warnings.filterwarnings("ignore", message="Importing plotly failed")
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

try:
    from prophet import Prophet

    _PROPHET_OK = True
except ImportError:
    _PROPHET_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_INCIDENTS = 50       # below this → BU-level fallback
MIN_MONTHS = 12          # below this → BU-level fallback
HOLDOUT_MONTHS = 3       # time-based holdout for evaluation
_FEATURE_COLS = ["month_of_year", "quarter_num", "lag_1", "lag_3", "lag_6", "lag_12",
                 "rolling_3m", "rolling_6m"]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mape(actual: np.ndarray, predicted: np.ndarray) -> Optional[float]:
    mask = actual > 0
    if not mask.any():
        return None
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def _rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(math.sqrt(mean_squared_error(actual, predicted)))


def _time_split(df: pd.DataFrame, holdout_n: int = HOLDOUT_MONTHS):
    """Time-based split — NEVER random."""
    return df.iloc[:-holdout_n].copy(), df.iloc[-holdout_n:].copy()


def _month_to_fiscal_quarter(year: int, month: int) -> str:
    """Convert (year, month) to fiscal quarter string 'YYYY-Qn'."""
    if month >= 4:
        q = (month - 4) // 3 + 1
    else:
        q = 4
    return f"{year}-Q{q}"


def _next_n_quarters_after(last_ts: pd.Timestamp, n: int) -> list[str]:
    """Return n consecutive fiscal quarters beginning the month after last_ts."""
    cur = last_ts + pd.DateOffset(months=1)
    quarters: list[str] = []
    seen: set[str] = set()
    while len(quarters) < n:
        q = _month_to_fiscal_quarter(cur.year, cur.month)
        if q not in seen:
            quarters.append(q)
            seen.add(q)
        cur += pd.DateOffset(months=1)
    return quarters


def _fiscal_quarter_months(quarter_str: str) -> list[tuple[int, int]]:
    """Return (year, month) pairs for every month in a fiscal quarter."""
    year = int(quarter_str[:4])
    q = quarter_str[-1]
    starts = {"1": 4, "2": 7, "3": 10, "4": 1}
    start_m = starts[q]
    return [(year, start_m + i) for i in range(3)]


def _confidence_band(series_df: pd.DataFrame) -> str:
    n_months = len(series_df)
    if n_months < MIN_MONTHS:
        return "low"
    if n_months < 24:
        return "medium"
    return "high"


def _has_sufficient_data(series_df: pd.DataFrame) -> bool:
    return series_df["y"].sum() >= MIN_INCIDENTS and len(series_df) >= MIN_MONTHS


# ---------------------------------------------------------------------------
# Prophet
# ---------------------------------------------------------------------------

def train_prophet(series_df: pd.DataFrame) -> dict:
    """
    Train Prophet on a [ds, y] monthly series.

    Performs a time-based train/holdout split (last 3 months = holdout),
    evaluates RMSE/MAPE on the holdout, then retrains on the FULL series
    so the returned model is ready for future forecasting.

    Returns
    -------
    dict with keys: success, model, rmse, mape, n_training, last_date
    or:             success=False, error
    """
    if not _PROPHET_OK:
        return {"success": False, "error": "Prophet not installed"}
    if len(series_df) < HOLDOUT_MONTHS + 4:
        return {"success": False, "error": f"too few months: {len(series_df)}"}

    try:
        train, holdout = _time_split(series_df)

        def _make_prophet():
            return Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                seasonality_mode="additive",
                interval_width=0.80,
            )

        # ── evaluation on holdout ──────────────────────────────────────────
        m_eval = _make_prophet()
        m_eval.fit(train)
        future_eval = m_eval.make_future_dataframe(periods=HOLDOUT_MONTHS, freq="MS")
        fc_eval = m_eval.predict(future_eval).tail(HOLDOUT_MONTHS)
        preds_eval = np.clip(fc_eval["yhat"].values, 0, None)

        rmse = _rmse(holdout["y"].values, preds_eval)
        mape = _mape(holdout["y"].values, preds_eval)

        # ── full retrain for forecasting ───────────────────────────────────
        m_full = _make_prophet()
        m_full.fit(series_df)

        return {
            "success": True,
            "model": m_full,
            "rmse": rmse,
            "mape": mape,
            "n_training": len(series_df),
            "last_date": series_df["ds"].max(),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# XGBoost
# ---------------------------------------------------------------------------

def train_xgboost(features_df: pd.DataFrame) -> dict:
    """
    Train XGBRegressor on a lag-feature DataFrame.

    Same time-based holdout evaluation + full retrain pattern as Prophet.
    """
    avail_cols = [c for c in _FEATURE_COLS if c in features_df.columns]
    if len(features_df) < HOLDOUT_MONTHS + 4:
        return {"success": False, "error": f"too few rows after lag drop: {len(features_df)}"}

    train, holdout = _time_split(features_df)

    def _make_xgb():
        return XGBRegressor(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )

    # ── evaluation ────────────────────────────────────────────────────────
    m_eval = _make_xgb()
    m_eval.fit(train[avail_cols], train["y"])
    preds_eval = np.clip(m_eval.predict(holdout[avail_cols]), 0, None)

    rmse = _rmse(holdout["y"].values, preds_eval)
    mape = _mape(holdout["y"].values, preds_eval)

    # ── full retrain ──────────────────────────────────────────────────────
    m_full = _make_xgb()
    m_full.fit(features_df[avail_cols], features_df["y"])

    return {
        "success": True,
        "model": m_full,
        "feature_cols": avail_cols,
        "rmse": rmse,
        "mape": mape,
        "n_training": len(features_df),
        "last_date": features_df["ds"].max(),
        "series": features_df[["ds", "y"]].copy(),   # needed for recursive prediction
    }


# ---------------------------------------------------------------------------
# XGBoost recursive multi-step prediction
# ---------------------------------------------------------------------------

def _xgb_forecast(result: dict, n_months: int) -> pd.DataFrame:
    """
    Recursively predict n_months ahead using the fitted XGBoost model.
    Uses previously predicted values as inputs to future lag features.
    Returns DataFrame with columns: ds, yhat.
    """
    model = result["model"]
    feature_cols = result["feature_cols"]
    series = result["series"].copy()

    y_history = list(series["y"].values.astype(float))
    last_ds = series["ds"].max()

    predictions = []
    for _ in range(n_months):
        next_ds = last_ds + pd.DateOffset(months=1)
        n = len(y_history)

        row: dict[str, float] = {
            "month_of_year": float(next_ds.month),
            "quarter_num": float(
                1 if next_ds.month <= 3 else
                (2 if next_ds.month <= 6 else
                 (3 if next_ds.month <= 9 else 4))
            ),
            "lag_1":  y_history[n - 1]  if n >= 1  else 0.0,
            "lag_3":  y_history[n - 3]  if n >= 3  else 0.0,
            "lag_6":  y_history[n - 6]  if n >= 6  else 0.0,
            "lag_12": y_history[n - 12] if n >= 12 else 0.0,
            "rolling_3m": float(np.mean(y_history[max(0, n-3):n])) if n > 0 else 0.0,
            "rolling_6m": float(np.mean(y_history[max(0, n-6):n])) if n > 0 else 0.0,
        }
        X = pd.DataFrame([[row[c] for c in feature_cols]], columns=feature_cols)
        pred = max(0.0, float(model.predict(X)[0]))

        predictions.append({"ds": next_ds, "yhat": pred})
        y_history.append(pred)
        last_ds = next_ds

    return pd.DataFrame(predictions)


# ---------------------------------------------------------------------------
# Quarterly aggregation
# ---------------------------------------------------------------------------

def _aggregate_to_quarters(
    monthly_df: pd.DataFrame,
    quarters: list[str],
    lower_col: str = "yhat_lower",
    upper_col: str = "yhat_upper",
) -> dict[str, dict]:
    """
    Sum monthly predictions into fiscal quarters.
    Returns {quarter_str: {yhat, lower, upper}}.
    """
    monthly_df = monthly_df.copy()
    monthly_df["fq"] = monthly_df["ds"].apply(
        lambda d: _month_to_fiscal_quarter(d.year, d.month)
    )
    result = {}
    for fq in quarters:
        rows = monthly_df[monthly_df["fq"] == fq]
        if rows.empty:
            result[fq] = {"yhat": 0.0, "lower": 0.0, "upper": 0.0}
        else:
            yhat = max(0.0, float(rows["yhat"].sum()))
            # Use CI columns if available; otherwise ±0 (XGBoost case filled separately)
            lower = max(0.0, float(rows[lower_col].sum())) if lower_col in rows else yhat
            upper = max(0.0, float(rows[upper_col].sum())) if upper_col in rows else yhat
            result[fq] = {"yhat": yhat, "lower": lower, "upper": upper}
    return result


def _xgb_ci(quarterly_pred: float, rmse: float, n_months: int = 3) -> tuple[float, float]:
    """Approximate 90% CI from per-month RMSE (assumes independence across months)."""
    sigma = math.sqrt(n_months) * rmse
    return max(0.0, quarterly_pred - 1.65 * sigma), quarterly_pred + 1.65 * sigma


# ---------------------------------------------------------------------------
# Main forecasting entry point
# ---------------------------------------------------------------------------

def predict_next_n_quarters(
    site: str,
    n: int = 3,
    session_factory=None,
) -> pd.DataFrame:
    """
    Forecast the next n complete fiscal quarters for a site.

    - Sites with <50 incidents OR <12 months of history use a BU-level
      Prophet model scaled by the site's historical share of the BU.
    - If Prophet fails, falls back to XGBoost alone.
    - If XGBoost also fails, returns zero predictions (model_name='none').

    Returns
    -------
    DataFrame with columns: target_quarter, predicted_count, lower_ci, upper_ci,
                            model_name, confidence_band, training_data_through.
    """
    n_forecast_months = n * 3

    series_df = build_site_monthly_series(site, session_factory)
    lag_df = _build_lag_features_from_series(series_df) if not series_df.empty else pd.DataFrame()

    is_sufficient = not series_df.empty and _has_sufficient_data(series_df)
    band = _confidence_band(series_df)

    # ── select training series ────────────────────────────────────────────
    if is_sufficient:
        train_series = series_df
        scale_factor = 1.0
        last_date = series_df["ds"].max()
    else:
        # BU-level fallback: scale BU predictions by site's historical share
        bu = get_site_bu(site, session_factory)
        bu_series = build_bu_monthly_series(bu, session_factory) if bu else series_df
        train_series = bu_series if not bu_series.empty else series_df
        site_total = float(series_df["y"].sum()) if not series_df.empty else 1.0
        bu_total = float(bu_series["y"].sum()) if not bu_series.empty else 1.0
        scale_factor = (site_total / bu_total) if bu_total > 0 else 0.05
        # Use the BU training series end as the anchor so sparse sites don't
        # produce predictions for quarters that are already in the past.
        last_date = train_series["ds"].max() if not train_series.empty else (
            series_df["ds"].max() if not series_df.empty else pd.Timestamp.now()
        )
        band = "low"

    if train_series.empty or last_date is pd.NaT:
        return _zero_predictions(site, n, band)

    target_quarters = _next_n_quarters_after(last_date, n)
    training_through = _month_to_fiscal_quarter(last_date.year, last_date.month)

    # ── train models ─────────────────────────────────────────────────────
    p_result = train_prophet(train_series)
    xgb_features = _build_lag_features_from_series(train_series)
    x_result = train_xgboost(xgb_features) if not xgb_features.empty else {"success": False}

    # ── generate monthly forecasts ────────────────────────────────────────
    prophet_q: dict[str, dict] = {}
    xgb_q: dict[str, dict] = {}

    if p_result["success"]:
        future = p_result["model"].make_future_dataframe(
            periods=n_forecast_months, freq="MS"
        )
        fc = p_result["model"].predict(future).tail(n_forecast_months).copy()
        fc["yhat"] = np.clip(fc["yhat"], 0, None)
        fc["yhat_lower"] = np.clip(fc["yhat_lower"], 0, None)
        fc["yhat_upper"] = np.clip(fc["yhat_upper"], 0, None)
        # ds might be datetime[ns] — normalise
        fc["ds"] = pd.to_datetime(fc["ds"])
        prophet_q = _aggregate_to_quarters(fc, target_quarters, "yhat_lower", "yhat_upper")

    if x_result["success"]:
        xgb_monthly = _xgb_forecast(x_result, n_forecast_months)
        xgb_monthly["ds"] = pd.to_datetime(xgb_monthly["ds"])
        # Add synthetic CI columns before aggregation
        sigma_m = x_result["rmse"]
        xgb_monthly["yhat_lower"] = (xgb_monthly["yhat"] - 1.65 * sigma_m).clip(lower=0)
        xgb_monthly["yhat_upper"] = xgb_monthly["yhat"] + 1.65 * sigma_m
        xgb_q = _aggregate_to_quarters(xgb_monthly, target_quarters, "yhat_lower", "yhat_upper")

    # ── ensemble / select best ────────────────────────────────────────────
    rows = []
    for tq in target_quarters:
        pq = prophet_q.get(tq)
        xq = xgb_q.get(tq)

        if pq and xq:
            pred = (pq["yhat"] + xq["yhat"]) / 2 * scale_factor
            lower = min(pq["lower"], xq["lower"]) * scale_factor
            upper = max(pq["upper"], xq["upper"]) * scale_factor
            model_name = "ensemble"
        elif pq:
            pred = pq["yhat"] * scale_factor
            lower, upper = pq["lower"] * scale_factor, pq["upper"] * scale_factor
            model_name = "prophet" if is_sufficient else "bu_prophet"
        elif xq:
            pred = xq["yhat"] * scale_factor
            lower, upper = xq["lower"] * scale_factor, xq["upper"] * scale_factor
            model_name = "xgboost"
        else:
            pred, lower, upper = 0.0, 0.0, 0.0
            model_name = "none"

        rows.append({
            "target_quarter": tq,
            "predicted_count": round(pred, 1),
            "lower_ci": round(lower, 1),
            "upper_ci": round(upper, 1),
            "model_name": model_name,
            "confidence_band": band,
            "training_data_through": training_through,
            "_prophet_rmse": p_result.get("rmse"),
            "_prophet_mape": p_result.get("mape"),
            "_prophet_n": p_result.get("n_training"),
            "_xgb_rmse": x_result.get("rmse"),
            "_xgb_mape": x_result.get("mape"),
            "_xgb_n": x_result.get("n_training"),
        })

    return pd.DataFrame(rows)


def _zero_predictions(site: str, n: int, band: str) -> pd.DataFrame:
    """Fallback: return n rows of zeros when no training data is available."""
    from datetime import date
    today = pd.Timestamp(date.today())
    quarters = _next_n_quarters_after(today, n)
    return pd.DataFrame([
        {
            "target_quarter": q,
            "predicted_count": 0.0,
            "lower_ci": 0.0,
            "upper_ci": 0.0,
            "model_name": "none",
            "confidence_band": "low",
            "training_data_through": None,
            "_prophet_rmse": None, "_prophet_mape": None, "_prophet_n": 0,
            "_xgb_rmse": None, "_xgb_mape": None, "_xgb_n": 0,
        }
        for q in quarters
    ])
