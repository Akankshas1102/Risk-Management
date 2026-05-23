from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String

from app.models.ol_incidents import SSMSBase


class PredictionsCache(SSMSBase):
    __tablename__ = "predictions_cache"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(String(500), nullable=False)
    business_unit = Column(String(500))
    target_quarter = Column(String(10), nullable=False)   # "YYYY-Qn"
    predicted_count = Column(Float)
    lower_ci = Column(Float)
    upper_ci = Column(Float)
    model_name = Column(String(50))                       # prophet/xgboost/ensemble/bu_prophet
    trained_at = Column(DateTime)
    training_data_through = Column(String(10))            # last quarter in training data
    confidence_band = Column(String(10))                  # high/medium/low


class ModelRun(SSMSBase):
    __tablename__ = "model_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_name = Column(String(50), nullable=False)
    site = Column(String(500))                            # null for BU-level models
    trained_at = Column(DateTime)
    training_rows = Column(Integer)
    holdout_rmse = Column(Float)
    holdout_mape = Column(Float)
    is_champion = Column(Boolean, default=False)
    n_quarters_history = Column(Integer)                  # distinct quarters in risk_scores for this site
    notes = Column(String(2000))
