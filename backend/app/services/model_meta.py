"""
model_meta service — shared logic for champion model metadata.

Called by the predictions API layer (backend/app/api/predictions.py) to
retrieve per-site model information without duplicating DB query logic.

Public API
----------
get_model_meta(site, db) -> ModelMetaDict
    Return a typed dict with champion model stats for a site.

get_backtest_summary(site, db) -> BacktestSummaryDict
    Return aggregate accuracy stats from the backtest_results table.

get_backtest_rows(site, db) -> list[BacktestRowDict]
    Return raw per-month (actual, predicted, abs_pct_error) rows.

TypedDicts
----------
ModelMetaDict     — mirrors the ModelMeta Pydantic schema in app/schemas/predictions.py
BacktestSummaryDict — aggregate accuracy stats (mean_ape, pct_within_20, n_months)
BacktestRowDict   — one row from backtest_results
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TypedDict

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.backtest import BacktestResult
from app.models.predictions import ModelRun


# ---------------------------------------------------------------------------
# TypedDicts (contract between this service and the predictions API layer)
# ---------------------------------------------------------------------------

class ModelMetaDict(TypedDict, total=False):
    site: str
    champion_model: Optional[str]      # "prophet" | "xgboost" | "ensemble" | "bu_prophet" | None
    holdout_rmse: Optional[float]
    holdout_mape: Optional[float]      # percentage, e.g. 22.3 means 22.3 %
    training_rows: Optional[int]
    last_trained_at: Optional[datetime]
    n_quarters_history: Optional[int]  # distinct quarters in risk_scores for this site


class BacktestSummaryDict(TypedDict):
    site: str
    n_months: int                      # number of backtest rows evaluated
    mean_ape: Optional[float]          # mean absolute percentage error across all months
    pct_within_20: Optional[float]     # % of months where abs_pct_error <= 20 %
    pct_within_30: Optional[float]     # % of months where abs_pct_error <= 30 %


class BacktestRowDict(TypedDict):
    month: str                         # "YYYY-MM"
    actual: Optional[float]
    predicted: Optional[float]
    abs_pct_error: Optional[float]
    model_name: Optional[str]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_model_meta(site: str, db: Session) -> ModelMetaDict:
    """
    Return champion model metadata for a site by querying model_runs.

    Falls back to all-None values (not an error) when the site has no champion row
    — this happens for VLCTPP and similar sites with insufficient training data.

    Parameters
    ----------
    site : Site name exactly as stored in model_runs / predictions_cache.
    db   : An active SQLAlchemy Session.

    Returns
    -------
    ModelMetaDict (TypedDict) — safe to spread into a Pydantic ModelMeta(...) constructor.
    """
    champ: Optional[ModelRun] = db.execute(
        select(ModelRun)
        .where(ModelRun.site == site, ModelRun.is_champion == True)  # noqa: E712
        .order_by(ModelRun.trained_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if champ is None:
        return ModelMetaDict(
            site=site,
            champion_model=None,
            holdout_rmse=None,
            holdout_mape=None,
            training_rows=None,
            last_trained_at=None,
            n_quarters_history=None,
        )

    # n_quarters_history: prefer the stored value; fall back to a live COUNT if missing
    n_q: int = champ.n_quarters_history or 0
    if n_q == 0:
        n_q = db.execute(
            text("SELECT COUNT(DISTINCT quarter) FROM risk_scores WHERE site = :s"),
            {"s": site},
        ).scalar() or 0

    return ModelMetaDict(
        site=site,
        champion_model=champ.model_name,
        holdout_rmse=round(champ.holdout_rmse, 3) if champ.holdout_rmse is not None else None,
        holdout_mape=round(champ.holdout_mape, 2) if champ.holdout_mape is not None else None,
        training_rows=champ.training_rows,
        last_trained_at=champ.trained_at,
        n_quarters_history=int(n_q),
    )


def get_backtest_summary(site: str, db: Session) -> BacktestSummaryDict:
    """
    Aggregate backtest accuracy stats for a site.

    Reads from backtest_results.  Returns zeros / None when no rows exist.

    Parameters
    ----------
    site : Site name.
    db   : Active SQLAlchemy Session.
    """
    rows = db.execute(
        select(BacktestResult)
        .where(BacktestResult.site == site)
        .order_by(BacktestResult.month.asc())
    ).scalars().all()

    if not rows:
        return BacktestSummaryDict(
            site=site, n_months=0,
            mean_ape=None, pct_within_20=None, pct_within_30=None,
        )

    valid = [r for r in rows if r.abs_pct_error is not None]
    n = len(valid)

    if n == 0:
        return BacktestSummaryDict(
            site=site, n_months=len(rows),
            mean_ape=None, pct_within_20=None, pct_within_30=None,
        )

    apes = [r.abs_pct_error for r in valid]
    mean_ape = round(sum(apes) / n, 2)
    pct_20 = round(sum(1 for a in apes if a <= 20) / n * 100, 1)
    pct_30 = round(sum(1 for a in apes if a <= 30) / n * 100, 1)

    return BacktestSummaryDict(
        site=site,
        n_months=len(rows),
        mean_ape=mean_ape,
        pct_within_20=pct_20,
        pct_within_30=pct_30,
    )


def get_backtest_rows(site: str, db: Session) -> list[BacktestRowDict]:
    """
    Return the raw per-month backtest rows for a site.

    Parameters
    ----------
    site : Site name.
    db   : Active SQLAlchemy Session.

    Returns
    -------
    List of BacktestRowDict ordered by month ascending.
    Empty list when no backtest data exists for the site.
    """
    rows = db.execute(
        select(BacktestResult)
        .where(BacktestResult.site == site)
        .order_by(BacktestResult.month.asc())
    ).scalars().all()

    return [
        BacktestRowDict(
            month=r.month,
            actual=r.actual,
            predicted=r.predicted,
            abs_pct_error=round(r.abs_pct_error, 2) if r.abs_pct_error is not None else None,
            model_name=r.model_name,
        )
        for r in rows
    ]
