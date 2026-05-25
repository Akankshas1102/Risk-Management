"""
Compatibility shim — api/risk_scores.py imports RiskScore from here.
The canonical model is RiskScore in app.models.pipeline.
"""

from app.models.pipeline import RiskScore  # noqa: F401

__all__ = ["RiskScore"]
