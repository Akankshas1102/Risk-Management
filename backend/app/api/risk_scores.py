from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.risk_score import RiskScore
from app.schemas.risk_score import RiskScoreResponse

router = APIRouter(prefix="/api", tags=["risk-scores"])


@router.get("/risk-scores", response_model=list[RiskScoreResponse])
def get_risk_scores(
    site: Optional[str] = None,
    business_unit: Optional[str] = None,
    quarter: Optional[str] = None,
    latest_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    Return risk scores with optional filters.

    - **site**: exact site name
    - **business_unit**: filter by BU
    - **quarter**: exact quarter string, e.g. '2024-Q1'
    - **latest_only**: return only the most recent scored quarter per site
    """
    query = select(RiskScore)

    if site:
        query = query.where(RiskScore.site == site)
    if business_unit:
        query = query.where(RiskScore.business_unit == business_unit)
    if quarter:
        query = query.where(RiskScore.quarter == quarter)

    if latest_only:
        # Use quarter_sort_key to find the chronologically latest quarter per site
        subq = (
            select(
                RiskScore.site,
                func.max(RiskScore.quarter_sort_key).label("max_key"),
            )
            .group_by(RiskScore.site)
            .subquery()
        )
        query = query.join(
            subq,
            (RiskScore.site == subq.c.site)
            & (RiskScore.quarter_sort_key == subq.c.max_key),
        )

    query = query.order_by(RiskScore.quarter_sort_key.desc(), RiskScore.site)
    return db.execute(query).scalars().all()
