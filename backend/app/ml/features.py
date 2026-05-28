"""
Feature engineering for forecasting models.

Public API
----------
build_site_monthly_series(site, session_factory=None)  -> pd.DataFrame  [ds, y]
build_bu_monthly_series(bu, session_factory=None)      -> pd.DataFrame  [ds, y]
build_lag_features(site, lags, session_factory=None)   -> pd.DataFrame  (XGBoost)

Internal helpers exposed for unit testing (no DB calls):
_df_to_monthly_series(raw_df)          -> pd.DataFrame  [ds, y]
_build_lag_features_from_series(df)    -> pd.DataFrame
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.ol_incidents import OLIncident

_MIN_YEAR = "2020"
_DEFAULT_LAGS = [1, 3, 6, 12]

# Module-level cache so every site in a training run shares one DB round-trip.
_global_max_date_cache: Optional[pd.Timestamp] = None


def get_global_max_date(session_factory=None) -> pd.Timestamp:
    """
    Return the latest (YEAR, MONTH) pair present in OL_INCIDENTS as a Timestamp.
    Uses ORDER BY so MAX(YEAR)+MAX(MONTH) mis-combination is avoided.
    Result is cached module-level for the lifetime of the process.
    """
    global _global_max_date_cache
    if _global_max_date_cache is not None:
        return _global_max_date_cache

    sf = session_factory or SessionLocal
    from sqlalchemy import cast, Integer as SAInteger, desc
    with sf() as session:
        row = session.execute(
            select(
                cast(OLIncident.YEAR, SAInteger).label("year"),
                OLIncident.MONTH.label("month"),
            )
            .where(
                OLIncident.YEAR >= _MIN_YEAR,
                OLIncident.YEAR.isnot(None),
                OLIncident.MONTH.isnot(None),
            )
            .order_by(
                desc(cast(OLIncident.YEAR, SAInteger)),
                desc(OLIncident.MONTH),
            )
            .limit(1)
        ).first()
    if row and row.year and row.month:
        _global_max_date_cache = pd.Timestamp(year=int(row.year), month=int(row.month), day=1)
    else:
        _global_max_date_cache = pd.Timestamp.now().replace(day=1)
    return _global_max_date_cache


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

def _load_raw(
    *,
    site: Optional[str] = None,
    business_unit: Optional[str] = None,
    session_factory=None,
) -> pd.DataFrame:
    sf = session_factory or SessionLocal
    conds = [
        OLIncident.YEAR >= _MIN_YEAR,
        OLIncident.YEAR.isnot(None),
        OLIncident.MONTH.isnot(None),
    ]
    if site:
        conds.append(OLIncident.SINAME == site)
    if business_unit:
        conds.append(OLIncident.BUNAME == business_unit)

    with sf() as session:
        rows = session.execute(
            select(OLIncident.YEAR, OLIncident.MONTH, OLIncident.SINAME, OLIncident.BUNAME)
            .where(*conds)
        ).all()

    return pd.DataFrame(rows, columns=["YEAR", "MONTH", "SINAME", "BUNAME"])


# ---------------------------------------------------------------------------
# Series construction (exposed for unit tests — no DB dependency)
# ---------------------------------------------------------------------------

def _df_to_monthly_series(
    raw: pd.DataFrame,
    pad_to: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """
    Convert a raw incident rows DataFrame to a continuous [ds, y] monthly series.

    Parameters
    ----------
    raw    : DataFrame with at least YEAR (str/int) and MONTH (int) columns.
    pad_to : If set and later than the series' own max date, the series is
             extended to this date with y=0 rows.  Use to align sparse sites/BUs
             to the global OL_INCIDENTS data end so prediction anchors are current.

    Returns
    -------
    DataFrame with columns [ds, y].  ds = first day of month (Timestamp).
    Months with zero incidents in the range are filled with y=0.
    """
    if raw.empty:
        return pd.DataFrame(columns=["ds", "y"])

    raw = raw.copy()
    raw["YEAR"] = raw["YEAR"].astype(int)

    counts = (
        raw.groupby(["YEAR", "MONTH"])
        .size()
        .reset_index(name="y")
    )
    counts["ds"] = pd.to_datetime(
        {"year": counts["YEAR"], "month": counts["MONTH"], "day": 1}
    )
    counts = counts[["ds", "y"]].sort_values("ds").reset_index(drop=True)

    if len(counts) < 2:
        return counts

    # Extend to pad_to if the series ends earlier (zero-pad the gap)
    end = counts["ds"].max()
    if pad_to is not None and pd.Timestamp(pad_to) > end:
        end = pd.Timestamp(pad_to)

    # Fill missing months in the range with 0
    full_range = pd.date_range(counts["ds"].min(), end, freq="MS")
    counts = (
        counts.set_index("ds")
        .reindex(full_range, fill_value=0)
        .reset_index()
        .rename(columns={"index": "ds"})
    )
    counts.columns = ["ds", "y"]
    return counts


def _build_lag_features_from_series(
    series: pd.DataFrame,
    lags: list[int] = None,
) -> pd.DataFrame:
    """
    Add calendar and lag features to a [ds, y] DataFrame for XGBoost.

    Returned columns: ds, y, month_of_year, quarter_num,
                      lag_1, lag_3, lag_6, lag_12 (as requested),
                      rolling_3m, rolling_6m.
    Rows with any NaN in lag columns are dropped (appears at the start of the series).
    """
    if lags is None:
        lags = _DEFAULT_LAGS

    df = series.copy()
    df["month_of_year"] = df["ds"].dt.month
    # 1=Q4(Jan-Mar) 2=Q1(Apr-Jun) 3=Q2(Jul-Sep) 4=Q3(Oct-Dec) — numeric for the model
    df["quarter_num"] = df["ds"].dt.month.map(
        lambda m: 1 if m <= 3 else (2 if m <= 6 else (3 if m <= 9 else 4))
    )

    for lag in lags:
        df[f"lag_{lag}"] = df["y"].shift(lag)

    df["rolling_3m"] = df["y"].shift(1).rolling(3).mean()
    df["rolling_6m"] = df["y"].shift(1).rolling(6).mean()

    return df.dropna().reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_site_monthly_series(site: str, session_factory=None) -> pd.DataFrame:
    """
    [ds, y] monthly series for a site.  Missing months filled with y=0.
    Automatically zero-padded to the global OL_INCIDENTS max date so that
    sparse sites are anchored to the current data end, not to their own last incident.
    """
    raw = _load_raw(site=site, session_factory=session_factory)
    pad_to = get_global_max_date(session_factory)
    return _df_to_monthly_series(raw, pad_to=pad_to)


def build_bu_monthly_series(business_unit: str, session_factory=None) -> pd.DataFrame:
    """
    [ds, y] monthly series for an entire business unit (all sites aggregated).
    Zero-padded to the global OL_INCIDENTS max date.
    """
    raw = _load_raw(business_unit=business_unit, session_factory=session_factory)
    pad_to = get_global_max_date(session_factory)
    return _df_to_monthly_series(raw, pad_to=pad_to)


def build_lag_features(
    site: str,
    lags: list[int] = None,
    session_factory=None,
) -> pd.DataFrame:
    """
    Build an XGBoost feature DataFrame for a site.
    Columns: ds, y, month_of_year, quarter_num, lag_1, ..., rolling_3m, rolling_6m.
    """
    series = build_site_monthly_series(site, session_factory)
    return _build_lag_features_from_series(series, lags or _DEFAULT_LAGS)


def get_site_bu(site: str, session_factory=None) -> Optional[str]:
    """Return the dominant business unit for a site."""
    sf = session_factory or SessionLocal
    with sf() as session:
        row = session.execute(
            select(OLIncident.BUNAME)
            .where(OLIncident.SINAME == site, OLIncident.BUNAME.isnot(None))
            .limit(1)
        ).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# QUARTERLY series builders (new — used by quarterly forecaster)
# ---------------------------------------------------------------------------

def _current_fiscal_quarter_start() -> pd.Timestamp:
    """
    Return the first day of the CURRENT (potentially incomplete) fiscal quarter
    as a calendar Timestamp.

    Fiscal quarters used in this project:
      Q4 = Jan-Mar  (start = year-01-01)
      Q1 = Apr-Jun  (start = year-04-01)
      Q2 = Jul-Sep  (start = year-07-01)
      Q3 = Oct-Dec  (start = year-10-01)
    """
    today = pd.Timestamp.today().normalize()
    m = today.month
    if m <= 3:
        return pd.Timestamp(year=today.year, month=1, day=1)
    if m <= 6:
        return pd.Timestamp(year=today.year, month=4, day=1)
    if m <= 9:
        return pd.Timestamp(year=today.year, month=7, day=1)
    return pd.Timestamp(year=today.year, month=10, day=1)


def _df_to_quarterly_series(
    raw: pd.DataFrame,
    pad_to: Optional[pd.Timestamp] = None,
    exclude_partial: bool = True,
) -> pd.DataFrame:
    """
    Aggregate raw incident rows to a continuous quarterly [ds, y] series.

    Parameters
    ----------
    raw             : DataFrame with YEAR (str/int) and MONTH (int) columns.
    pad_to          : Latest month to pad to (zero-fill any missing quarters).
    exclude_partial : Drop the currently-open quarter so the model never trains
                      on incomplete months (which would otherwise drag predictions down).

    Returns
    -------
    DataFrame [ds, y] where ds = first day of the FISCAL quarter and y = sum of
    incidents in that quarter.  Missing quarters in the range are zero-filled.
    """
    if raw.empty:
        return pd.DataFrame(columns=["ds", "y"])

    raw = raw.copy()
    raw["YEAR"] = raw["YEAR"].astype(int)
    raw["ds_month"] = pd.to_datetime(
        {"year": raw["YEAR"], "month": raw["MONTH"], "day": 1}
    )

    # Map each month -> fiscal-quarter start (Q4=Jan, Q1=Apr, Q2=Jul, Q3=Oct)
    def _q_start(d: pd.Timestamp) -> pd.Timestamp:
        m = d.month
        if m <= 3:
            return pd.Timestamp(year=d.year, month=1, day=1)
        if m <= 6:
            return pd.Timestamp(year=d.year, month=4, day=1)
        if m <= 9:
            return pd.Timestamp(year=d.year, month=7, day=1)
        return pd.Timestamp(year=d.year, month=10, day=1)

    raw["q_start"] = raw["ds_month"].apply(_q_start)

    counts = (
        raw.groupby("q_start")
        .size()
        .reset_index(name="y")
        .rename(columns={"q_start": "ds"})
        .sort_values("ds")
        .reset_index(drop=True)
    )

    if len(counts) == 0:
        return counts

    # Pad missing quarters in the observed range with 0
    end = counts["ds"].max()
    if pad_to is not None:
        pad_quarter_start = _q_start(pd.Timestamp(pad_to))
        if pad_quarter_start > end:
            end = pad_quarter_start

    full_range = pd.date_range(counts["ds"].min(), end, freq="QS-JAN")
    # QS-JAN gives quarters starting Jan/Apr/Jul/Oct which matches our fiscal layout.
    counts = (
        counts.set_index("ds")
        .reindex(full_range, fill_value=0)
        .reset_index()
        .rename(columns={"index": "ds"})
    )
    counts.columns = ["ds", "y"]

    # Drop the currently-open quarter — it's still receiving incidents so its
    # count would otherwise be artificially low and would train the model
    # to predict declining counts.
    if exclude_partial:
        partial_start = _current_fiscal_quarter_start()
        counts = counts[counts["ds"] < partial_start].reset_index(drop=True)

    return counts


def _build_quarterly_lag_features(
    series: pd.DataFrame,
    lags: list[int] = None,
) -> pd.DataFrame:
    """
    Add lag and seasonal features to a quarterly [ds, y] DataFrame for XGBoost.

    Lags are in *quarters* — lag_4 = 4 quarters ago = year-over-year.
    Returned columns: ds, y, fiscal_q (1-4), lag_1, lag_2, lag_4, rolling_2q.
    Rows with any NaN (at the start) are dropped.
    """
    if lags is None:
        lags = [1, 2, 4]

    df = series.copy()

    # fiscal_q: 1=Q4 (Jan), 2=Q1 (Apr), 3=Q2 (Jul), 4=Q3 (Oct)
    def _fiscal_q_num(d: pd.Timestamp) -> int:
        m = d.month
        return {1: 1, 4: 2, 7: 3, 10: 4}.get(m, 1)

    df["fiscal_q"] = df["ds"].apply(_fiscal_q_num)

    for lag in lags:
        df[f"lag_{lag}"] = df["y"].shift(lag)

    df["rolling_2q"] = df["y"].shift(1).rolling(2).mean()

    return df.dropna().reset_index(drop=True)


def build_site_quarterly_series(site: str, session_factory=None, pad: bool = True) -> pd.DataFrame:
    """
    [ds, y] quarterly series for a site.  Internal gaps filled with 0, and the
    currently-open (partial) quarter is always EXCLUDED.

    pad=True  (default) — trailing-pad with zero quarters out to the global
        OL_INCIDENTS data end.  Use for FORECASTING so prediction quarters
        anchor to the current quarter (sparse sites don't predict the past).

    pad=False — stop at the site's own last real quarter (no trailing zeros).
        Use for BACKTEST / holdout evaluation so the held-out window is the
        site's actual last quarters of data, not padding.
    """
    raw = _load_raw(site=site, session_factory=session_factory)
    pad_to = get_global_max_date(session_factory) if pad else None
    return _df_to_quarterly_series(raw, pad_to=pad_to, exclude_partial=True)


def build_bu_quarterly_series(business_unit: str, session_factory=None, pad: bool = True) -> pd.DataFrame:
    """
    [ds, y] quarterly series for a whole BU (all sites aggregated).
    See build_site_quarterly_series for the meaning of `pad`.
    """
    raw = _load_raw(business_unit=business_unit, session_factory=session_factory)
    pad_to = get_global_max_date(session_factory) if pad else None
    return _df_to_quarterly_series(raw, pad_to=pad_to, exclude_partial=True)
