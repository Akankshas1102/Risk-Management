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
    _build_quarterly_lag_features,
    build_bu_monthly_series,
    build_bu_quarterly_series,
    build_lag_features,
    build_site_monthly_series,
    build_site_quarterly_series,
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
MIN_MONTHS = 12          # legacy (kept for backtest module compatibility)
MIN_QUARTERS = 4         # below this → BU-level fallback (quarterly path)
HOLDOUT_MONTHS = 3       # legacy
HOLDOUT_QUARTERS = 2     # last 2 quarters held out for evaluation
_FEATURE_COLS = ["month_of_year", "quarter_num", "lag_1", "lag_3", "lag_6", "lag_12",
                 "rolling_3m", "rolling_6m"]
_QUARTERLY_FEATURE_COLS = ["fiscal_q", "lag_1", "lag_2", "lag_4", "rolling_2q"]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mape(actual: np.ndarray, predicted: np.ndarray) -> Optional[float]:
    """Classic MAPE — kept for backward compatibility."""
    mask = actual > 0
    if not mask.any():
        return None
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def _smape(actual: np.ndarray, predicted: np.ndarray) -> Optional[float]:
    """
    Symmetric Mean Absolute Percentage Error (sMAPE).

    Formula: mean( 2 * |actual - predicted| / (|actual| + |predicted|) ) * 100

    Why we use this instead of MAPE:
    - MAPE divides by actual only.  A month with actual=1 predicted=4 produces
      300% error, which destroys the average for sparse sites.
    - sMAPE divides by the SUM of magnitudes, so it's bounded at 200% per point
      and treats over- and under-prediction symmetrically.

    Returns None if every (actual+predicted) pair is zero (no signal at all).
    """
    denom = np.abs(actual) + np.abs(predicted)
    mask = denom > 0
    if not mask.any():
        return None
    return float(np.mean(2.0 * np.abs(actual[mask] - predicted[mask]) / denom[mask]) * 100)


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


def _confidence_band_q(series_df: pd.DataFrame) -> str:
    """Quarterly version: 4 quarters = 1 year of history."""
    n_q = len(series_df)
    if n_q < MIN_QUARTERS:
        return "low"
    if n_q < 8:
        return "medium"
    return "high"


def _has_sufficient_data_q(series_df: pd.DataFrame) -> bool:
    return series_df["y"].sum() >= MIN_INCIDENTS and len(series_df) >= MIN_QUARTERS


# ---------------------------------------------------------------------------
# Prophet
# ---------------------------------------------------------------------------

def train_prophet(series_df: pd.DataFrame, holdout_n: int = HOLDOUT_MONTHS) -> dict:
    """
    Train Prophet on a [ds, y] series (monthly OR quarterly — caller chooses
    holdout_n: 3 for monthly, 2 for quarterly).

    Performs a time-based train/holdout split, evaluates RMSE/sMAPE on the
    holdout, then retrains on the FULL series so the returned model is ready
    for future forecasting.

    Returns
    -------
    dict with keys: success, model, rmse, mape, n_training, last_date
    or:             success=False, error
    """
    if not _PROPHET_OK:
        return {"success": False, "error": "Prophet not installed"}
    if len(series_df) < holdout_n + 2:
        return {"success": False, "error": f"too few rows: {len(series_df)}"}

    try:
        train, holdout = _time_split(series_df, holdout_n=holdout_n)

        def _make_prophet():
            return Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                seasonality_mode="additive",
                interval_width=0.80,
            )

        # ── evaluation on holdout ──────────────────────────────────────────
        # Detect monthly vs quarterly cadence from the spacing of ds values
        median_gap_days = float((train["ds"].diff().dropna().dt.days).median() or 30)
        freq = "QS-JAN" if median_gap_days >= 80 else "MS"

        m_eval = _make_prophet()
        m_eval.fit(train)
        future_eval = m_eval.make_future_dataframe(periods=holdout_n, freq=freq)
        fc_eval = m_eval.predict(future_eval).tail(holdout_n)
        preds_eval = np.clip(fc_eval["yhat"].values, 0, None)

        rmse = _rmse(holdout["y"].values, preds_eval)
        mape = _smape(holdout["y"].values, preds_eval)

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

def train_xgboost(features_df: pd.DataFrame, holdout_n: int | None = None) -> dict:
    """
    Train XGBRegressor on a lag-feature DataFrame.

    Auto-detects whether the feature columns are monthly (_FEATURE_COLS) or
    quarterly (_QUARTERLY_FEATURE_COLS) and picks whichever set is present.

    Same time-based holdout evaluation + full retrain pattern as Prophet.
    """
    # Detect feature schema (monthly vs quarterly)
    monthly_avail   = [c for c in _FEATURE_COLS           if c in features_df.columns]
    quarterly_avail = [c for c in _QUARTERLY_FEATURE_COLS if c in features_df.columns]
    avail_cols = quarterly_avail if len(quarterly_avail) >= 3 else monthly_avail

    if holdout_n is None:
        holdout_n = HOLDOUT_QUARTERS if quarterly_avail else HOLDOUT_MONTHS

    if len(features_df) < holdout_n + 2:
        return {"success": False, "error": f"too few rows after lag drop: {len(features_df)}"}

    train, holdout = _time_split(features_df, holdout_n=holdout_n)

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
# Quarterly XGBoost recursive forecasting
# ---------------------------------------------------------------------------

def _quarter_start_to_fiscal(ds: pd.Timestamp) -> str:
    """Map a fiscal-quarter START Timestamp to 'YYYY-Qn' (the same format
    used everywhere else in the project)."""
    return _month_to_fiscal_quarter(ds.year, ds.month)


def _xgb_forecast_quarterly(result: dict, n_quarters: int) -> pd.DataFrame:
    """
    Recursively predict n quarters ahead using a fitted XGBoost model
    that was trained on a quarterly lag-feature DataFrame.
    Returns DataFrame [ds, yhat].
    """
    model = result["model"]
    feature_cols = result["feature_cols"]
    series = result["series"].copy()
    y_history = list(series["y"].values.astype(float))
    last_ds = series["ds"].max()

    predictions = []
    for _ in range(n_quarters):
        next_ds = last_ds + pd.DateOffset(months=3)
        n = len(y_history)

        # fiscal_q: 1=Q4(Jan) 2=Q1(Apr) 3=Q2(Jul) 4=Q3(Oct)
        fiscal_q = {1: 1, 4: 2, 7: 3, 10: 4}.get(next_ds.month, 1)

        row = {
            "fiscal_q": float(fiscal_q),
            "lag_1": y_history[n - 1] if n >= 1 else 0.0,
            "lag_2": y_history[n - 2] if n >= 2 else 0.0,
            "lag_4": y_history[n - 4] if n >= 4 else 0.0,
            "rolling_2q": float(np.mean(y_history[max(0, n - 2):n])) if n > 0 else 0.0,
        }
        X = pd.DataFrame([[row[c] for c in feature_cols]], columns=feature_cols)
        pred = max(0.0, float(model.predict(X)[0]))

        predictions.append({"ds": next_ds, "yhat": pred})
        y_history.append(pred)
        last_ds = next_ds

    return pd.DataFrame(predictions)


# ---------------------------------------------------------------------------
# Main forecasting entry point
# ---------------------------------------------------------------------------

def predict_next_n_quarters(
    site: str,
    n: int = 3,
    session_factory=None,
) -> pd.DataFrame:
    """
    Forecast the next n complete fiscal quarters for a site (QUARTERLY pipeline).

    - Sites with <50 incidents OR <4 quarters of history use a BU-level
      Prophet model scaled by the site's historical share of the BU.
    - If Prophet fails, falls back to XGBoost alone.
    - If XGBoost also fails, returns zero predictions (model_name='none').

    Returns
    -------
    DataFrame with columns: target_quarter, predicted_count, lower_ci, upper_ci,
                            model_name, confidence_band, training_data_through.
    """
    # Build the quarterly series for the site (partial current quarter excluded).
    series_df = build_site_quarterly_series(site, session_factory)

    is_sufficient = not series_df.empty and _has_sufficient_data_q(series_df)
    band = _confidence_band_q(series_df)

    # ── select training series ────────────────────────────────────────────
    if is_sufficient:
        train_series = series_df
        scale_factor = 1.0
        last_date = series_df["ds"].max()
    else:
        # BU-level fallback: scale BU predictions by site's historical share
        bu = get_site_bu(site, session_factory)
        bu_series = build_bu_quarterly_series(bu, session_factory) if bu else series_df
        train_series = bu_series if not bu_series.empty else series_df
        site_total = float(series_df["y"].sum()) if not series_df.empty else 1.0
        bu_total = float(bu_series["y"].sum()) if not bu_series.empty else 1.0
        scale_factor = (site_total / bu_total) if bu_total > 0 else 0.05
        last_date = train_series["ds"].max() if not train_series.empty else (
            series_df["ds"].max() if not series_df.empty else pd.Timestamp.now()
        )
        band = "low"

    if train_series.empty or last_date is pd.NaT:
        return _zero_predictions(site, n, band)

    # Generate next-N target quarter labels and the "training through" quarter
    target_quarters: list[str] = []
    cursor = last_date
    seen: set[str] = set()
    while len(target_quarters) < n:
        cursor = cursor + pd.DateOffset(months=3)
        q = _quarter_start_to_fiscal(cursor)
        if q not in seen:
            target_quarters.append(q)
            seen.add(q)
    training_through = _quarter_start_to_fiscal(last_date)

    # ── train models (both on quarterly series) ──────────────────────────
    p_result = train_prophet(train_series, holdout_n=HOLDOUT_QUARTERS)
    xgb_features = _build_quarterly_lag_features(train_series)
    x_result = train_xgboost(xgb_features, holdout_n=HOLDOUT_QUARTERS) \
        if not xgb_features.empty else {"success": False}

    # Cap any forecast at 1.5× the historical max quarter (prevents wild spikes)
    hist_max = float(train_series["y"].max()) if not train_series.empty else 0.0
    cap = max(1.0, hist_max * 1.5)

    prophet_q: dict[str, dict] = {}
    xgb_q: dict[str, dict] = {}

    if p_result["success"]:
        future = p_result["model"].make_future_dataframe(periods=n, freq="QS-JAN")
        fc = p_result["model"].predict(future).tail(n).copy()
        fc["yhat"]       = np.clip(fc["yhat"],       0, cap)
        fc["yhat_lower"] = np.clip(fc["yhat_lower"], 0, cap)
        fc["yhat_upper"] = np.clip(fc["yhat_upper"], 0, cap)
        fc["ds"] = pd.to_datetime(fc["ds"])
        for _, r in fc.iterrows():
            tq = _quarter_start_to_fiscal(r["ds"])
            prophet_q[tq] = {
                "yhat":  float(r["yhat"]),
                "lower": float(r["yhat_lower"]),
                "upper": float(r["yhat_upper"]),
            }

    if x_result["success"]:
        xgb_fc = _xgb_forecast_quarterly(x_result, n)
        sigma = x_result["rmse"]
        for _, r in xgb_fc.iterrows():
            tq = _quarter_start_to_fiscal(pd.Timestamp(r["ds"]))
            yhat  = min(float(r["yhat"]), cap)
            lower = max(0.0, yhat - 1.65 * sigma)
            upper = min(cap, yhat + 1.65 * sigma)
            xgb_q[tq] = {"yhat": yhat, "lower": lower, "upper": upper}

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
