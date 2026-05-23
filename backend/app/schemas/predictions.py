from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PredictionItem(BaseModel):
    id: int
    site: str
    business_unit: Optional[str] = None
    target_quarter: str
    predicted_count: Optional[float] = None
    lower_ci: Optional[float] = None
    upper_ci: Optional[float] = None
    model_name: Optional[str] = None
    trained_at: Optional[datetime] = None
    training_data_through: Optional[str] = None
    confidence_band: Optional[str] = None

    model_config = {"from_attributes": True}


class ModelMeta(BaseModel):
    site: str
    champion_model: Optional[str] = None
    holdout_rmse: Optional[float] = None
    holdout_mape: Optional[float] = None
    training_rows: Optional[int] = None
    last_trained_at: Optional[datetime] = None
    n_quarters_history: Optional[int] = None


class PredictionsResponse(BaseModel):
    model_meta: ModelMeta
    predictions: list[PredictionItem]


class BacktestPoint(BaseModel):
    month: str           # "YYYY-MM"
    actual: Optional[float] = None
    predicted: Optional[float] = None
    model_name: Optional[str] = None

    model_config = {"from_attributes": True}
