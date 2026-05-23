from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DriverItem(BaseModel):
    id: int
    site: str
    quarter: str
    driver_name: Optional[str] = None
    category: Optional[str] = None
    impact_score: Optional[float] = None
    trend: Optional[str] = None
    pct_change_vs_last_qtr: Optional[float] = None
    computed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RecommendationItem(BaseModel):
    id: int
    site: str
    quarter: str
    action_text: Optional[str] = None
    priority: Optional[str] = None
    impact_estimate: Optional[str] = None
    suggested_owner: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
