from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.predictions import ModelRun, PredictionsCache
from app.models.backtest import BacktestResult
import app.models.backtest  # noqa — ensures table is registered
from app.schemas.predictions import (
    BacktestPoint,
    ModelMeta,
    PredictionItem,
    PredictionsResponse,
)

router = APIRouter(prefix="/api", tags=["predictions"])

# Fiscal quarter order: Q4=Jan-Mar (0), Q1=Apr-Jun (1), Q2=Jul-Sep (2), Q3=Oct-Dec (3)
_FISCAL_ORDER = ["Q4", "Q1", "Q2", "Q3"]


def _quarter_sort_key(quarter_str: str) -> int:
    """Return a comparable int for fiscal-quarter strings, e.g. '2026-Q4' → 20260."""
    try:
        year, q = quarter_str.split("-")
        return int(year) * 10 + _FISCAL_ORDER.index(q)
    except (ValueError, IndexError):
        return 0


def _build_model_meta(site: str, db: Session) -> ModelMeta:
    """Build ModelMeta by reading the champion ModelRun for a site."""
    champ = db.execute(
        select(ModelRun)
        .where(ModelRun.site == site, ModelRun.is_champion == True)  # noqa: E712
        .order_by(ModelRun.trained_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if champ is None:
        return ModelMeta(site=site)

    # Count distinct quarters in risk_scores to estimate history depth
    from sqlalchemy import text
    n_q = db.execute(
        text("SELECT COUNT(DISTINCT quarter) FROM risk_scores WHERE site = :s"),
        {"s": site},
    ).scalar() or 0

    return ModelMeta(
        site=site,
        champion_model=champ.model_name,
        holdout_rmse=round(champ.holdout_rmse, 3) if champ.holdout_rmse else None,
        holdout_mape=round(champ.holdout_mape, 2) if champ.holdout_mape else None,
        training_rows=champ.training_rows,
        last_trained_at=champ.trained_at,
        n_quarters_history=int(n_q),
    )


@router.get("/predictions", response_model=PredictionsResponse)
def get_predictions(
    site: Optional[str] = Query(None, description="Filter by site name"),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Return cached predictions + champion model metadata.
    Call scripts/train_all_forecasters.py to populate predictions first.
    """
    stmt = select(PredictionsCache)

    if site:
        stmt = stmt.where(PredictionsCache.site == site)
    if business_unit:
        stmt = stmt.where(PredictionsCache.business_unit == business_unit)

    items = db.execute(stmt).scalars().all()
    # Sort using fiscal calendar: Q4 (Jan-Mar) < Q1 (Apr-Jun) < Q2 (Jul-Sep) < Q3 (Oct-Dec)
    items = sorted(items, key=lambda p: _quarter_sort_key(p.target_quarter))

    meta_site = site or (items[0].site if items else "")
    model_meta = _build_model_meta(meta_site, db) if meta_site else ModelMeta(site="")

    return PredictionsResponse(
        model_meta=model_meta,
        predictions=[PredictionItem.model_validate(i) for i in items],
    )


@router.get("/predictions/backtest", response_model=list[BacktestPoint])
def get_backtest(
    site: str = Query(..., description="Site name"),
    db: Session = Depends(get_db),
):
    """
    Return the last 6 months of (actual, predicted) pairs for the champion model.
    Populated by scripts/compute_backtest.py.
    """
    rows = db.execute(
        select(BacktestResult)
        .where(BacktestResult.site == site)
        .order_by(BacktestResult.month.asc())
    ).scalars().all()

    return [BacktestPoint.model_validate(r) for r in rows]
