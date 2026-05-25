from sqlalchemy import BigInteger, Column, DateTime, Float, String, Text

from app.models.ol_incidents import Base


class RiskDriver(Base):
    __tablename__ = "risk_drivers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(String(500), nullable=False)
    quarter = Column(String(10), nullable=False)    # "YYYY-Qn"
    driver_name = Column(String(500))               # human-readable label
    category = Column(String(500))                  # raw INCIDENTCATNAME
    impact_score = Column(Float)                    # 0–100 normalised
    trend = Column(String(10))                      # up / down / flat
    pct_change_vs_last_qtr = Column(Float)
    sparkline_data = Column(Text)                   # JSON array: last 6 monthly counts
    computed_at = Column(DateTime)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(String(500), nullable=False)
    quarter = Column(String(10), nullable=False)
    action_text = Column(String(2000))
    priority = Column(String(10))                   # high / medium / low
    impact_estimate = Column(String(500))
    suggested_owner = Column(String(500))
    status = Column(String(50), default="open")
    source = Column(String(10), default="rules")    # rules / llm
    driver_link = Column(String(500))               # category/driver that triggered this rule
    created_at = Column(DateTime)
