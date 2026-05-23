"""SQL Server ORM models for orchestration state and risk scores."""

import json

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from app.models.ol_incidents import SSMSBase


class PipelineRun(SSMSBase):
    __tablename__ = "pipeline_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trigger = Column(String(50))            # manual / scheduled / post_ingest
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    status = Column(String(20))             # queued / running / success / partial / failed
    steps_run = Column(Text)               # JSON string: {step: {status, duration_s, ...}}
    error_summary = Column(String(2000))

    @property
    def steps(self) -> dict:
        return json.loads(self.steps_run) if self.steps_run else {}

    @steps.setter
    def steps(self, value: dict) -> None:
        self.steps_run = json.dumps(value, default=str)


class RiskScoreSSMS(SSMSBase):
    """SQL Server version of the risk_scores table (populated by the orchestrator)."""

    __tablename__ = "risk_scores"
    __table_args__ = (
        UniqueConstraint("site", "quarter", name="uq_risk_scores_site_quarter"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(String(500), nullable=False)
    business_unit = Column(String(500))
    quarter = Column(String(10), nullable=False)
    quarter_sort_key = Column(Integer)
    risk_score = Column(Float)
    risk_level = Column(String(20))
    frequency_index = Column(Float)
    severity_index = Column(Float)
    velocity_index = Column(Float)
    diversity_index = Column(Float)
    computed_at = Column(DateTime)
