# File Structure

**Source of truth:** PostgreSQL database `vedanta_risk` (managed via pgAdmin),
populated from `data/raw/OL_INCIDENTS_clean.csv`.

In the live workflow no SQL Server tooling is involved. The CSV in
`data/raw/` is provided externally (manually copied into the repo). The
optional `main.py` exporter at the project root *can* pull from SQL Server
via pyodbc, but it is not used during normal development.

*Last updated: after the SSMS cleanup refactor.*

---

## End-to-end data flow

```
                CSV is dropped here manually
                            │
                            ▼
data/raw/OL_INCIDENTS_<timestamp>.csv          ← raw snapshot
         │  (scripts/clean_csv.py)
         ▼
data/raw/OL_INCIDENTS_clean.csv                ← canonicalised CSV
         │  (scripts/load_csv_to_db.py)
         ▼
Postgres `ol_incidents` table                  ← live data store
         │  (backend/app/services/orchestrator.py)
         ▼
ML pipeline → risk_scores / predictions_cache
              / risk_drivers / recommendations
              / backtest_results / pipeline_runs
         │
         ▼
backend/app FastAPI  →  frontend (React + Vite)
```

> The `main.py` exporter at the repo root can fetch a fresh CSV from the
> corporate SQL Server `OL_INCIDENTS` table, but it is **optional** and not
> part of the normal development loop.

---

## Top-level

| File / Dir | Purpose |
|---|---|
| `README.md` | Project overview, prerequisites, quickstart |
| `FILE_STRUCTURE.md` | This file — canonical repo map |
| `main.py` | **Standalone** SQL Server → CSV/XLSX exporter (pyodbc). Independent of the live app — used only to refresh `data/raw/`. |
| `run.bat` | Windows convenience launcher for `main.py` |
| `requirements.txt` | Root-level Python dependencies (mirrors `backend/requirements.txt`) |
| `.env` | Environment variables (DATABASE_URL, RETRAIN_CRON, optional DB_* for `main.py`) — not committed |
| `.env.example` | Template for `.env` |

---

## backend/

### `backend/app/main.py`
FastAPI application factory. Registers all routers, adds CORS middleware,
starts the APScheduler nightly retrain on boot via the `lifespan` context
manager. `GET /health` returns the next scheduled retrain time.

### `backend/app/core/`

| File | Purpose |
|---|---|
| `config.py` | Pydantic-settings `Settings` class. Reads `.env`. Exposes `DATABASE_URL`, `RETRAIN_CRON`. |
| `database.py` | PostgreSQL SQLAlchemy `engine`, `SessionLocal` sessionmaker, `get_db()` FastAPI dependency. **Single canonical DB module.** |
| `scheduler.py` | APScheduler `BackgroundScheduler` wrapper. `start_scheduler(cron)`, `shutdown_scheduler()`, `next_run_time()`. Fires `run_full_pipeline(trigger="scheduled")` on the configured cron. |

### `backend/app/models/`

All ORM models inherit from a single `Base` defined in `ol_incidents.py`.

| File | Table | Purpose |
|---|---|---|
| `ol_incidents.py` | `ol_incidents` | Read-only source of truth for raw incident data. Defines `Base`. |
| `pipeline.py` | `pipeline_runs`, `risk_scores` | Pipeline execution log + composite risk scores per site per quarter |
| `predictions.py` | `predictions_cache`, `model_runs` | Forecast cache (next 3 quarters per site) + model training log |
| `drivers.py` | `risk_drivers`, `recommendations` | SHAP-based top-10 drivers + rules-based action items per site |
| `backtest.py` | `backtest_results` | Walk-forward holdout evaluation results |
| `ingestion.py` | `ingestion_runs` | CSV upload run log (status, row counts, timestamps) |

### `backend/app/schemas/`

Pydantic response schemas — the HTTP contract between backend and frontend.

| File | Schemas |
|---|---|
| `analytics.py` | `SiteItem`, `KPIResponse`, `IncidentTypeCount`, `IncidentCategoryCount`, `IncidentSiteCount`, `TrendPoint`, `HeatmapPoint` |
| `drivers.py` | `DriverItem`, `RecommendationItem` |
| `incident.py` | `IncidentRaw`, `IncidentClean` (used by the cleaner) |
| `predictions.py` | `PredictionItem`, `ModelMeta`, `PredictionsResponse`, `BacktestPoint` |
| `risk_score.py` | `RiskScoreResponse` |

### `backend/app/api/`

FastAPI routers.

| File | Prefix | Purpose |
|---|---|---|
| `analytics.py` | `/api` | Sites, KPIs, incident breakdown by type/category/site/trend/heatmap |
| `risk_scores.py` | `/api` | `GET /risk-scores` |
| `drivers.py` | `/api` | `GET /drivers`, `GET /recommendations` |
| `predictions.py` | `/api` | `GET /predictions`, `GET /predictions/backtest` |
| `ingest.py` | `/api` | `POST /ingest` — CSV upload; triggers ML pipeline on success |
| `admin.py` | `/api/admin` | `POST /retrain`, `GET /runs`, `GET /freshness`, `GET /diagnostics` |

### `backend/app/services/`

| File | Purpose |
|---|---|
| `cleaner.py` | Pure-pandas CSV cleaning: date validation, bad-year filtering, quarantine |
| `ingestion.py` | `ingest_csv()` — reads CSV → runs cleaner → writes `ingestion_runs` to Postgres |
| `risk_score.py` | Pure-math utilities for the composite score: `compute_frequency_index`, `compute_severity_index`, `compute_velocity_index`, `compute_diversity_index`, `_quarter_sort_key`, `_score_to_level`. **No DB calls.** Imported by `pipeline_steps.py`. |
| `recommendations.py` | 8-rule rules engine producing `RecommendationSpec` objects |
| `drivers_service.py` | `regenerate_for_site(site)`, `regenerate_all(dry_run)` |
| `model_meta.py` | `get_model_meta(site, db)`, `get_backtest_summary(site, db)`, `get_backtest_rows(site, db)` — service layer for the predictions API |
| `pipeline_steps.py` | `step_risk_scores()`, `step_forecasters()`, `step_drivers()`, `step_backtest()` — the 4 ML pipeline step functions |
| `orchestrator.py` | `run_full_pipeline(trigger)` plus `trigger_manual_retrain()`, `get_recent_runs(limit)`, `get_freshness()` |

### `backend/app/ml/`

| File | Purpose |
|---|---|
| `features.py` | Time-series construction from `ol_incidents`: `build_site_monthly_series()`, `build_site_quarterly_series()`, `build_bu_quarterly_series()`, `get_global_max_date()` |
| `forecaster.py` | Prophet + XGBoost per-site ensemble. `predict_next_n_quarters(site, n)`. Champion = lower holdout RMSE. BU-level fallback for sparse sites. |
| `drivers.py` | SHAP feature attribution: `compute_drivers_for_site(site)`, `build_category_sparklines()`, trend + pct-change |
| `backtest.py` | `compute_site_backtest(site)`, `run_all_backtests()`, `compute_abs_pct_error()` — walk-forward holdout |

### `backend/tests/`

| File | Type | Purpose |
|---|---|---|
| `test_analytics.py` | Integration | Hits live Postgres `vedanta_risk`. Tests all analytics endpoints. |
| `test_forecaster.py` | Unit | Pure-math forecaster tests (synthetic DataFrames, no DB). |
| `test_drivers.py` | Unit | Pure-math driver attribution + rules engine tests (no DB). |

### `backend/alembic/versions/`

Schema migration documentation. Tables are actually applied via
`scripts/apply_migrations.py` (`Base.metadata.create_all`), not via
alembic CLI.

| File | What changed |
|---|---|
| `0003_predictions_cache.py` | Created `predictions_cache`, `model_runs` |
| `0004_drivers_recommendations.py` | Created `risk_drivers`, `recommendations` |
| `0005_pipeline_runs.py` | Created `pipeline_runs`, `risk_scores` |
| `0006_backtest_results.py` | Created `backtest_results` |
| `0007_add_backtest_ape_and_model_history.py` | Added `abs_pct_error`, `n_quarters_history` |
| `0008_drivers_sparkline_rec_driver_link.py` | Added `sparkline_data`, `driver_link` |
| `0009_ingestion_runs.py` | Created `ingestion_runs` |

---

## scripts/

| File | Purpose |
|---|---|
| `clean_csv.py` | One-shot cleanup: drops 1899 rows, normalises `SINAME`, canonicalises `INCIDENTCATNAME` variants. Writes `OL_INCIDENTS_clean.csv`. |
| `load_csv_to_db.py` | Drops + recreates `ol_incidents` and bulk-loads `OL_INCIDENTS_clean.csv` (or the raw file as fallback). |
| `apply_migrations.py` | Runs `Base.metadata.create_all()` to create / update all ML output tables. Run after adding new ORM columns. |
| `run_pipeline.py` | **Main CLI.** Runs all 4 ML steps. `--trigger`, `--verbose`. Exit codes: 0=success, 1=partial/failed, 2=exception. |
| `run_backtest.py` | Standalone walk-forward backtest CLI. |
| `_csv_inspect.py` | Print row-level diagnostics for the raw CSV. |
| `_csv_aliases.py` | Print distinct values to design alias maps. |
| `README.md` | Script usage guide. |

---

## frontend/src/

| Path | Purpose |
|---|---|
| `main.tsx` | React entry point |
| `App.tsx` | Tab routing (Overview, Trends, Risk Drivers, Predictions, Recommendations, AI Insights, Reports, Data Health) |
| `api/client.ts` | Axios instance (base URL from `VITE_API_URL`) |
| `api/hooks.ts` | React Query hooks for all endpoints |
| `types/api.ts` | TypeScript interfaces matching backend Pydantic schemas |
| `context/FilterContext.tsx` | Global site / quarter filter state |
| `tabs/Overview.tsx` | KPI cards + incident breakdown charts |
| `tabs/Trends.tsx` | Incident trend over time |
| `tabs/RiskDrivers.tsx` | SHAP driver attribution with sparklines |
| `tabs/Predictions.tsx` | Forecast chart with confidence bands |
| `tabs/Recommendations.tsx` | Rules-based action items |
| `tabs/IncidentBreakdown.tsx` | Per-quarter type / category / site breakdown |
| `tabs/AIInsights.tsx` | Placeholder stub |
| `tabs/Reports.tsx` | Placeholder stub |
| `tabs/DataHealth.tsx` | Pipeline + per-site model health monitor |
| `components/layout/` | Header, Sidebar, Layout, FreshnessFooter |
| `components/common/` | KpiCard, ChartCard, SeverityBadge, ErrorState, SkeletonGrid |
| `components/ui/` | shadcn/ui primitives (badge, button, card, skeleton) |

---

## data/

| Path | Purpose |
|---|---|
| `data/raw/OL_INCIDENTS_<timestamp>.csv` | Raw export from SQL Server. **Never delete.** |
| `data/raw/OL_INCIDENTS_clean.csv` | Cleaned canonical CSV. Generated by `clean_csv.py`. **This is what the pipeline loads into Postgres.** |
| `data/processed/` | Reserved — currently empty. |

## exports/

Year-wise (fiscal year) and full-snapshot CSV/XLSX dumps generated by the
root `main.py` exporter. Used as ad-hoc audit / Excel files for stakeholders.
**Not consumed by the ML pipeline.** Safe to delete files older than your
retention window. The single sentinel `OL_INCIDENTS_FY1899-00.csv` contains
the 1899 garbage row only and can be removed.

---

## docs/

| File | Purpose |
|---|---|
| `ML_PIPELINE_STATE.md` | Comprehensive ML pipeline state, verified row counts, bug-fix log, service-layer reference |
| `API_CONTRACT.md` | Full REST API contract |
| `Risk_Management_Data_Flow.pdf` | Generated diagram of the data flow |
| `generate_dataflow_pdf.py` | Reportlab script that builds the PDF |
