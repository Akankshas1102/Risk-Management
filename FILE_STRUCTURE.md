# File Structure

**Source of truth: SQL Server vedanta database (OL_INCIDENTS + all ML tables).**
**Postgres retired: 2026-05-25 (Phase 2C cleanup).**

*Last updated: 2026-05-25*

---

## Top-level

| File / Dir | Purpose |
|---|---|
| `README.md` | Project overview and setup instructions |
| `FILE_STRUCTURE.md` | This file — canonical repo map |
| `main.py` | Root entry point — starts uvicorn on `backend/app/main.py` |
| `run.bat` | Windows convenience launcher |
| `requirements.txt` | Root-level Python dependencies (mirrors `backend/requirements.txt`) |
| `.env` | Environment variables (DATABASE_URL, SSMS_DATABASE_URL, etc.) — not committed |
| `.env.example` | Template for `.env` |

---

## backend/

### `backend/app/main.py`
FastAPI application factory. Registers all routers, adds CORS middleware, starts
APScheduler nightly-retrain on boot via `lifespan` context manager.
`GET /health` returns next scheduled retrain time.

### `backend/app/core/`

| File | Purpose |
|---|---|
| `config.py` | Pydantic-settings `Settings` class. Reads `.env`. Exposes `SSMS_DATABASE_URL`, `RETRAIN_CRON`, etc. |
| `ssms.py` | SQL Server engine (`ssms_engine`), `SSMSSession` factory, `get_ssms_db()` FastAPI dependency |
| `database.py` | **Compatibility shim only.** Re-exports `get_db = get_ssms_db` and `SessionLocal = SSMSSession` so Vinay's `api/risk_scores.py` (imports `from app.core.database import get_db`) continues to work without modification. Do not add Postgres code here. |
| `scheduler.py` | APScheduler `BackgroundScheduler` wrapper. `start_scheduler(cron)`, `shutdown_scheduler()`, `next_run_time()`. Fires `run_full_pipeline(trigger="scheduled")` on the configured cron. |

### `backend/app/models/`

All models use `SSMSBase` (SQL Server). No Postgres models remain.

| File | Table | Purpose |
|---|---|---|
| `ol_incidents.py` | `OL_INCIDENTS` | Read-only source of truth for raw incident data. Defines `SSMSBase`. |
| `pipeline.py` | `pipeline_runs`, `risk_scores` | Pipeline execution log + composite risk scores per site per quarter |
| `predictions.py` | `predictions_cache`, `model_runs` | Forecast cache (next 3 quarters per site) + model training log |
| `drivers.py` | `risk_drivers`, `recommendations` | SHAP-based top-10 drivers + rules-based action items per site |
| `backtest.py` | `backtest_results` | Walk-forward 6-month holdout evaluation results |
| `ingestion.py` | `ingestion_runs` | CSV upload run log (status, row counts, timestamps) |
| `risk_score.py` | — | **Compatibility shim.** Re-exports `RiskScoreSSMS as RiskScore` so `api/risk_scores.py` continues to work. |

### `backend/app/schemas/`

Pydantic response schemas. **Vinay's territory — do not modify.**

| File | Schemas |
|---|---|
| `analytics.py` | `SiteItem`, `KPIResponse`, `IncidentTypeCount`, etc. |
| `drivers.py` | `DriverItem`, `RecommendationItem` |
| `incident.py` | `IncidentIngest`, ingestion response |
| `predictions.py` | `PredictionsResponse`, `BacktestPoint`, `ModelMeta` |
| `risk_score.py` | `RiskScoreResponse` |

### `backend/app/api/`

FastAPI routers. **Vinay's territory — do not modify.**

| File | Prefix | Purpose |
|---|---|---|
| `analytics.py` | `/api` | Sites, KPIs, incident breakdown by type/category/site/trend/heatmap |
| `risk_scores.py` | `/api` | `GET /risk-scores` — now reads from SQL Server via `RiskScoreSSMS` shim |
| `drivers.py` | `/api` | `GET /drivers`, `GET /recommendations` |
| `predictions.py` | `/api` | `GET /predictions`, `GET /predictions/backtest` |
| `ingest.py` | `/api` | `POST /ingest` — CSV upload; triggers ML pipeline on success |
| `admin.py` | `/api/admin` | `POST /retrain`, `GET /runs`, `GET /freshness` |

### `backend/app/services/`

| File | Purpose |
|---|---|
| `cleaner.py` | Pure-pandas CSV cleaning: date validation, bad-year filtering, quarantine |
| `ingestion.py` | `ingest_csv()` — reads CSV → runs cleaner → writes `ingestion_runs` to SQL Server |
| `risk_score.py` | Pure-math utilities: `compute_frequency_index`, `compute_severity_index`, `compute_velocity_index`, `compute_diversity_index`, `_quarter_sort_key`, `_score_to_level`, etc. **No DB calls.** Imported by `pipeline_steps.py`. |
| `recommendations.py` | 8-rule rules engine producing `RecommendationSpec` objects. Rules: high_velocity, access_control, material_handling, ir_worker, asset_property, reporting_lag, process_deviations, generic_fallback |
| `drivers_service.py` | `regenerate_for_site(site)`, `regenerate_all(dry_run)` — convenience wrappers for driver+recommendation re-generation |
| `model_meta.py` | `get_model_meta(site, db)`, `get_backtest_summary(site, db)`, `get_backtest_rows(site, db)` — service layer for Vinay's predictions API |
| `pipeline_steps.py` | `step_risk_scores()`, `step_forecasters()`, `step_drivers()`, `step_backtest()` — the 4 ML pipeline step functions. Each is idempotent and self-contained. |
| `orchestrator.py` | `run_full_pipeline(trigger)` — runs all 4 steps in order, records to `pipeline_runs`. Also: `trigger_manual_retrain()`, `get_recent_runs(limit)`, `get_freshness()` |

### `backend/app/ml/`

| File | Purpose |
|---|---|
| `features.py` | `build_site_monthly_series()`, `build_bu_monthly_series()`, `get_global_max_date()` — time-series construction from OL_INCIDENTS for forecasting |
| `forecaster.py` | Prophet + XGBoost per-site ensemble. `predict_next_n_quarters(site, n)`. Champion = lower holdout RMSE. BU-level fallback for sparse sites. |
| `drivers.py` | SHAP feature attribution: `compute_drivers_for_site(site)`, `build_category_sparklines()`, trend + pct-change computation |
| `backtest.py` | `compute_site_backtest(site)`, `run_all_backtests()`, `compute_abs_pct_error()` — 6-month walk-forward holdout |

### `backend/tests/`

| File | Type | Purpose |
|---|---|---|
| `test_analytics.py` | Integration | Hits live SQL Server vedanta DB. Tests all analytics endpoints. |
| `test_forecaster.py` | Unit | Pure-math forecaster tests (synthetic DataFrames, no DB). |
| `test_drivers.py` | Unit | Pure-math driver attribution + rules engine tests (no DB). |

### `backend/alembic/versions/`

SQL Server schema migration documentation. Applied via `scripts/apply_ssms_migrations.py`
(`SSMSBase.metadata.create_all`), NOT via alembic CLI.

| File | What changed |
|---|---|
| `0003_predictions_cache.py` | Created `predictions_cache`, `model_runs` |
| `0004_drivers_recommendations.py` | Created `risk_drivers`, `recommendations` |
| `0005_pipeline_runs.py` | Created `pipeline_runs`, `risk_scores` |
| `0006_backtest_results.py` | Created `backtest_results` |
| `0007_add_backtest_ape_and_model_history.py` | Added `abs_pct_error`, `n_quarters_history` |
| `0008_drivers_sparkline_rec_driver_link.py` | Added `sparkline_data`, `driver_link` |
| `0009_ingestion_runs_ssms.py` | Created `ingestion_runs` (SQL Server mirror of retired Postgres table) |

---

## scripts/

| File | Purpose |
|---|---|
| `run_pipeline.py` | **Main CLI.** Runs all 4 ML steps. `--trigger`, `--verbose`. Exit codes: 0=success, 1=partial/failed, 2=exception. |
| `run_backtest.py` | Standalone 6-month walk-forward backtest CLI. |
| `apply_ssms_migrations.py` | Creates / updates all SQL Server tables from `SSMSBase.metadata`. Run after adding new models or columns. |
| `README.md` | Script usage guide |

---

## frontend/src/

| Path | Purpose |
|---|---|
| `main.tsx` | React entry point |
| `App.tsx` | Tab routing (`Overview`, `Trends`, `Risk Drivers`, `Predictions`, `Recommendations`, `AI Insights`, `Reports`) |
| `api/client.ts` | Axios instance (base URL from `VITE_API_BASE_URL`) |
| `api/hooks.ts` | React Query hooks for all endpoints |
| `types/api.ts` | TypeScript interfaces matching backend Pydantic schemas |
| `context/FilterContext.tsx` | Global site / BU / quarter filter state |
| `tabs/Overview.tsx` | KPI cards + incident breakdown charts |
| `tabs/Trends.tsx` | Incident trend over time |
| `tabs/RiskDrivers.tsx` | SHAP driver attribution with sparklines |
| `tabs/Predictions.tsx` | Forecast chart with confidence bands |
| `tabs/Recommendations.tsx` | Rules-based action items |
| `tabs/AIInsights.tsx` | Placeholder stub — not yet implemented |
| `tabs/Reports.tsx` | Placeholder stub — not yet implemented |
| `components/layout/` | Header, Sidebar, Layout, FreshnessFooter |
| `components/common/` | KpiCard, ChartCard, SeverityBadge, ErrorState, SkeletonGrid |
| `components/ui/` | shadcn/ui primitives (badge, button, card, skeleton) |

---

## data/

| Path | Purpose |
|---|---|
| `data/raw/` | Source CSV exports from OL_INCIDENTS. **Never delete.** |
| `data/processed/incidents_clean.parquet` | Cleaned snapshot (parquet). Generated by legacy cleaning pipeline; OL_INCIDENTS is now the live source. |

## exports/

Raw CSV/XLSX exports used during initial SQL Server load. Kept for audit / reload purposes.

---

## docs/

| File | Purpose |
|---|---|
| `ML_PIPELINE_STATE.md` | Comprehensive ML pipeline state, verified row counts, bug fix log, and service-layer API reference |
| `API_CONTRACT.md` | Full REST API contract for all endpoints |
