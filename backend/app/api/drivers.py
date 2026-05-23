from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
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
    """Top N risk drivers for a site, sorted by impact_score descending."""
    stmt = (
        select(RiskDriver)
        .where(RiskDriver.site == site)
        .order_by(RiskDriver.impact_score.desc())
        .limit(n)
    )
    if quarter:
        stmt = stmt.where(RiskDriver.quarter == quarter)
    else:
        # latest quarter: subquery max by impact_score proxy — use computed_at
        from sqlalchemy import func
        sub = (
            select(func.max(RiskDriver.computed_at))
            .where(RiskDriver.site == site)
            .scalar_subquery()
        )
        stmt = stmt.where(RiskDriver.computed_at == sub)

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
    """
    from sqlalchemy import case

    priority_order = case(
        (Recommendation.priority == "high", 1),
        (Recommendation.priority == "medium", 2),
        else_=3,
    )

    stmt = (
        select(Recommendation)
        .where(Recommendation.site == site, Recommendation.status == "open")
        .order_by(priority_order, Recommendation.created_at.desc())
    )
    if quarter:
        stmt = stmt.where(Recommendation.quarter == quarter)
    else:
        from sqlalchemy import func
        sub = (
            select(func.max(Recommendation.created_at))
            .where(Recommendation.site == site)
            .scalar_subquery()
        )
        stmt = stmt.where(Recommendation.created_at == sub)

    return db.execute(stmt).scalars().all()
