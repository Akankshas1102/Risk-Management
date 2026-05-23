from typing import Optional
from pydantic import BaseModel


class SiteItem(BaseModel):
    site: str
    business_unit: Optional[str] = None
    incident_count: int


class KPIResponse(BaseModel):
    quarter: str
    site: Optional[str] = None
    total_incidents_qtr: int
    delta_vs_last_qtr_pct: Optional[float] = None  # None if no previous quarter data
    top_category: Optional[str] = None
    top_category_share: Optional[float] = None     # 0–1
    predicted_next_qtr: Optional[int] = None       # placeholder — null until ML phase
    risk_score: Optional[float] = None             # from risk_scores table when available
    confidence_score: Optional[float] = None       # placeholder — null until ML phase


class IncidentTypeCount(BaseModel):
    incident_type: str
    count: int


class IncidentCategoryCount(BaseModel):
    category: str
    count: int


class IncidentSiteCount(BaseModel):
    site: str
    business_unit: Optional[str] = None
    count: int


class TrendPoint(BaseModel):
    year: int
    month: int
    month_label: str        # e.g. "Oct 2024"
    count: int
    all_sites_avg: float


class HeatmapPoint(BaseModel):
    site: str
    business_unit: Optional[str] = None
    likelihood_score: float  # min-max normalised frequency [0, 1]
    impact_score: float      # min-max normalised severity-weighted sum [0, 1]
    risk_band: str           # Low / Medium / High / Critical
