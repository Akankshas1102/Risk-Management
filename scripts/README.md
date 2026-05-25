# scripts/

Operational scripts for the Risk Management ML pipeline.
Source of truth: **SQL Server vedanta database** (OL_INCIDENTS + all ML tables).
Postgres was retired on 2026-05-25.

| Script | Purpose | When to run |
|---|---|---|
| `run_pipeline.py` | Full ML pipeline CLI: risk_scores → forecasters → backtest → drivers | Manual trigger or cron fallback |
| `run_backtest.py` | Standalone walk-forward backtest for all sites | Standalone re-evaluation |
| `apply_ssms_migrations.py` | Create / update SQL Server tables from ORM metadata | After adding new model columns or tables |

## Typical usage

```
# Full pipeline (manual trigger)
python scripts/run_pipeline.py --trigger manual --verbose

# Scheduled (from cron or task scheduler)
python scripts/run_pipeline.py --trigger scheduled

# Standalone backtest only
python scripts/run_backtest.py

# Apply schema changes after model updates
python scripts/apply_ssms_migrations.py
```

## Exit codes (run_pipeline.py)

| Code | Meaning |
|---|---|
| 0 | All 4 steps succeeded |
| 1 | One or more steps failed / partial run |
| 2 | Unhandled exception before any step ran |
