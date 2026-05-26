from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ssms import get_ssms_db
from app.models.drivers import Recommendation, RiskDriver
from app.schemas.drivers import DriverItem, RecommendationItem

router = APIRouter(prefix="/api", tags=["drivers"])


@router.get("/drivers", response_model=list[DriverItem])
def get_drivers(
    site: str = Query(..., description="Site name"),
    quarter: Optional[str] = Query(None, description="YYYY-Qn; defaults to most recent"),
    n: int = Query(10, ge=1, le=50, description="Max drivers to return"),
    db: Session = Depends(get_ssms_db),
):
    """
    Top N risk drivers for a site, sorted by impact_score descending.

    Always returns the most recently computed batch (max computed_at).
    The `quarter` param is accepted for API compatibility but the pipeline
    stores drivers for whatever quarter has the most recent data, which may
    differ from the calendar quarter the frontend has selected.
    """
    # Pin to the most recently computed batch for this site so the data is
    # always visible regardless of which calendar quarter the frontend shows.
    latest_computed = (
        select(func.max(RiskDriver.computed_at))
        .where(RiskDriver.site == site)
        .scalar_subquery()
    )
    stmt = (
        select(RiskDriver)
        .where(RiskDriver.site == site, RiskDriver.computed_at == latest_computed)
        .order_by(RiskDriver.impact_score.desc())
        .limit(n)
    )
    return db.execute(stmt).scalars().all()


@router.get("/recommendations", response_model=list[RecommendationItem])
def get_recommendations(
    site: str = Query(..., description="Site name"),
    quarter: Optional[str] = Query(None, description="YYYY-Qn; defaults to most recent"),
    db: Session = Depends(get_ssms_db),
):
    """
    Recommendations for a site grouped by priority (high → medium → low).
    Returns open recommendations only.

    Always returns the most recently created batch (max created_at).
    """
    from sqlalchemy import case

    priority_order = case(
        (Recommendation.priority == "high", 1),
        (Recommendation.priority == "medium", 2),
        else_=3,
    )

    latest_created = (
        select(func.max(Recommendation.created_at))
        .where(Recommendation.site == site)
        .scalar_subquery()
    )
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.site == site,
            Recommendation.status == "open",
            Recommendation.created_at == latest_created,
        )
        .order_by(priority_order, Recommendation.created_at.desc())
    )
    return db.execute(stmt).scalars().all()
