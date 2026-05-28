# scripts/

Operational scripts for the Risk Management project.
Source of truth: **PostgreSQL** database `vedanta_risk` (managed via pgAdmin),
populated from `data/raw/OL_INCIDENTS_clean.csv`.

| Script | Purpose | When to run |
|---|---|---|
| `clean_csv.py` | One-shot cleanup of the raw OL_INCIDENTS CSV → produces `OL_INCIDENTS_clean.csv` | After dropping a fresh raw export into `data/raw/` |
| `load_csv_to_db.py` | Truncates `ol_incidents` in Postgres and bulk-loads the cleaned CSV | After cleaning, or when refreshing the database |
| `apply_migrations.py` | Creates / updates all ML output tables (`risk_scores`, `predictions_cache`, `model_runs`, `risk_drivers`, `recommendations`, `pipeline_runs`, `backtest_results`, `ingestion_runs`) using `Base.metadata.create_all()` | After adding a new ORM model or column |
| `run_pipeline.py` | Full ML pipeline CLI: risk_scores → forecasters → backtest → drivers | Manual trigger or cron fallback |
| `run_backtest.py` | Standalone walk-forward backtest for all sites | Standalone re-evaluation |
| `_csv_inspect.py` | Print quick CSV diagnostics (column nullability, value distributions, date parsing) | Ad-hoc data exploration |
| `_csv_aliases.py` | List distinct site / category / severity values to design alias maps | Ad-hoc data exploration |

## Typical usage

```bash
# 1. Clean the raw CSV
python scripts/clean_csv.py

# 2. Apply / update the schema (idempotent)
python scripts/apply_migrations.py

# 3. Bulk-load the cleaned CSV into Postgres
python scripts/load_csv_to_db.py

# 4. Run the ML pipeline (manual)
python scripts/run_pipeline.py --trigger manual --verbose

# Scheduled run (from cron / Windows Task Scheduler)
python scripts/run_pipeline.py --trigger scheduled

# Standalone backtest only
python scripts/run_backtest.py
```

## Exit codes (run_pipeline.py)

| Code | Meaning |
|---|---|
| 0 | All 4 steps succeeded |
| 1 | One or more steps failed / partial run |
| 2 | Unhandled exception before any step ran |
