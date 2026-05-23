from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RiskScoreResponse(BaseModel):
    id: int
    site: str
    business_unit: Optional[str] = None
    quarter: str
    quarter_sort_key: Optional[int] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    frequency_index: Optional[float] = None
    severity_index: Optional[float] = None
    velocity_index: Optional[float] = None
    diversity_index: Optional[float] = None
    computed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
