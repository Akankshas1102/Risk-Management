"""
Compatibility shim — RiskScore is now the SQL Server model.

The original Postgres RiskScore and RiskScoreWeights were retired in Phase 2C
(2026-05-25).  api/risk_scores.py imports RiskScore from this module and must
continue to work without modification (it is Vinay's territory).

The canonical model is RiskScoreSSMS in app.models.pipeline.
RiskScoreWeights (Postgres) is retired; no active code used it.
"""

from app.models.pipeline import RiskScoreSSMS as RiskScore  # noqa: F401

__all__ = ["RiskScore"]
