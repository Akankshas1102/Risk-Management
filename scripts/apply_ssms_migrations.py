"""
Apply SQL Server-specific migrations (predictions_cache, model_runs) to vedanta.
This script also creates the tables for all models registered with SSMSBase.

Usage:
    python scripts/apply_ssms_migrations.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.ssms import ssms_engine
from app.models.ol_incidents import SSMSBase
import app.models.predictions  # noqa: F401 — registers PredictionsCache, ModelRun
import app.models.drivers      # noqa: F401 — registers RiskDriver, Recommendation
import app.models.pipeline     # noqa: F401 — registers PipelineRun, RiskScoreSSMS
import app.models.backtest     # noqa: F401 — registers BacktestResult

print("Applying SSMS migrations...")
SSMSBase.metadata.create_all(ssms_engine, checkfirst=True)
print("Done. Tables created (if not already present):")
for table in SSMSBase.metadata.tables:
    print(f"  {table}")
