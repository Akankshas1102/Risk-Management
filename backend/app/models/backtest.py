from sqlalchemy import BigInteger, Column, DateTime, Float, String

from app.models.ol_incidents import SSMSBase


class BacktestResult(SSMSBase):
    __tablename__ = "backtest_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(String(500), nullable=False)
    month = Column(String(10), nullable=False)   # "YYYY-MM"
    actual = Column(Float)
    predicted = Column(Float)
    abs_pct_error = Column(Float)                # |actual - predicted| / actual * 100
    model_name = Column(String(50))
    computed_at = Column(DateTime)
