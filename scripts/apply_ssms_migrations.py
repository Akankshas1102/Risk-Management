"""
Create all ML output tables in the PostgreSQL vedanta_risk database.

This script uses SQLAlchemy's create_all() to create every table registered
with SSMSBase.  It is idempotent — already-existing tables are not touched.

Tables created
--------------
  risk_scores          — composite risk score per site per quarter
  predictions_cache    — Prophet / XGBoost forecasts
  model_runs           — model training metadata + champion flag
  risk_drivers         — SHAP driver attribution rows
  recommendations      — rules-based action recommendations
  pipeline_runs        — pipeline execution history
  backtest_results     — walk-forward holdout evaluation
  ingestion_runs       — CSV upload audit trail

Usage
-----
    cd backend
    python ../scripts/apply_ssms_migrations.py

Note: ol_incidents is created by load_csv_to_db.py, not here, because that
script drops and recreates the table on each CSV reload.
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
import app.models.ingestion    # noqa: F401 — registers IngestionRunSSMS

print("Creating ML output tables in PostgreSQL vedanta_risk...")
# ol_incidents is excluded here — it is managed by load_csv_to_db.py
# All other SSMSBase tables are created below.
SSMSBase.metadata.create_all(ssms_engine, checkfirst=True)
print("Done. Tables created (if not already present):")
for table in sorted(SSMSBase.metadata.tables):
    print(f"  {table}")
