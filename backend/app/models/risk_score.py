from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Integer,
    Numeric, String, Text, UniqueConstraint,
)

from app.core.database import Base


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (
        UniqueConstraint("site", "quarter", name="uq_risk_scores_site_quarter"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(Text, nullable=False)
    business_unit = Column(Text)
    quarter = Column(String(10), nullable=False)   # "YYYY-Qn", e.g. "2024-Q1"
    quarter_sort_key = Column(Integer)             # numeric sort: 2024*10+1 = 20241
    risk_score = Column(Numeric(7, 4))
    risk_level = Column(String(20))
    frequency_index = Column(Numeric(8, 6))
    severity_index = Column(Numeric(8, 6))
    velocity_index = Column(Numeric(8, 6))
    diversity_index = Column(Numeric(8, 6))
    computed_at = Column(DateTime(timezone=True))


class RiskScoreWeights(Base):
    __tablename__ = "risk_score_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_unit = Column(Text)                   # NULL = global default
    w_frequency = Column(Numeric(5, 4), nullable=False)
    w_severity = Column(Numeric(5, 4), nullable=False)
    w_velocity = Column(Numeric(5, 4), nullable=False)
    w_diversity = Column(Numeric(5, 4), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)                    # NULL = currently active
