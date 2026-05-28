# ML Pipeline State

*Last updated: 2026-05-20*

## Table Population Summary

All five ML tables are now populated and serving live data to the dashboard API.

| Table | Row Count | Coverage | Notes |
|---|---|---|---|
| `risk_scores` | 777 | 2021-Q1 → 2026-Q4 | Composite score (frequency + severity + velocity + diversity) per site per quarter |
| `predictions_cache` | 111 | Next 3 quarters per site | 37 sites; ensemble of Prophet + XGBoost per site |
| `model_runs` | 355+ | All sites | Champion selected by holdout RMSE; duplicate rows from multiple runs are expected |
| `risk_drivers` | 278 | 37 sites | SHAP-based top-10 incident-category drivers per site |
| `recommendations` | 41 | 37 sites | Rules-based action items derived from top drivers |
| `backtest_results` | 216 | 36 sites × 6 months | Walk-forward holdout: model trained on data before cutoff, predicts 6-month window |

## Model Details

- **Forecasting architecture**: For each site, Prophet and XGBoost are both trained on a time-based train/holdout split (last 3 months = holdout). The champion is whichever achieves lower holdout RMSE. When both succeed, predictions are averaged (ensemble). Sites with fewer than 50 incidents or 12 months of data fall back to BU-level Prophet scaled by the site's historical share.
- **Champion model distribution**: Predominantly XGBoost for sites with sparse data (low volatility), Prophet or ensemble for high-volume sites. All 37 sites use "ensemble" as the reported model name when both models contributed.
- **Prediction quarters**: Latest 3 fiscal quarters after the site's training data cutoff. For most sites this is 2026-Q4 (Jan-Mar), 2026-Q1 (Apr-Jun), 2026-Q2 (Jul-Sep). Sites backed by a BU series that ends in December 2025 have their predictions anchored to December 2025.
- **Backtest accuracy**: 6-month walk-forward holdout shows site-level MAPE varies from ~22% (high-volume sites like BALCO) to higher for sparse sites. Results stored in `backtest_results` and served by `GET /api/predictions/backtest?site=X`.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/compute_risk_scores.py` | Compute quarterly composite risk scores |
| `scripts/train_all_forecasters.py` | Train Prophet+XGBoost, populate predictions_cache and model_runs |
| `scripts/compute_drivers_and_recs.py` | SHAP drivers + rules-based recommendations |
| `scripts/compute_backtest.py` | 6-month walk-forward backtest for all sites |

## Bug Fixed (2026-05-20)

`backend/app/ml/forecaster.py` — BU-fallback path was anchoring prediction quarters to the sparse site's last data point instead of the BU training series' end. Fixed to use `train_series["ds"].max()`, which prevents sparse sites from generating predictions for quarters already in the past.

---

## Update — 2026-05-23

### Schema Changes (migration 0007)

Two columns added to existing tables:

| Table | New Column | Type | Purpose |
|---|---|---|---|
| `backtest_results` | `abs_pct_error` | FLOAT NULL | \|actual − predicted\| / actual × 100; NULL when actual = 0 |
| `model_runs` | `n_quarters_history` | INT NULL | Distinct quarters in `risk_scores` for this site (history depth proxy) |

Both columns were backfilled for all existing rows on migration. New script runs populate them at insert time.

### New Files

| File | Purpose |
|---|---|
| `backend/app/ml/backtest.py` | Reusable backtest module: `compute_site_backtest()`, `run_all_backtests()`, `compute_abs_pct_error()` |
| `scripts/run_backtest.py` | CLI wrapper around `run_all_backtests()` — replaces the old `compute_backtest.py` for new runs |
| `backend/app/services/model_meta.py` | Service layer for the predictions API — call `get_model_meta(site, db)`, `get_backtest_summary(site, db)`, `get_backtest_rows(site, db)` |
| `backend/alembic/versions/0007_add_backtest_ape_and_model_history.py` | Alembic migration DDL for the two new columns |

### Bug Fixed (2026-05-23) — BU Series Anchor for Inactive BUs

`backend/app/ml/features.py` — BU-level and sparse site series were built by filling only between the BU's own first and last incident dates. For BUs like FACOR (last incident Sep 2025) and VZI (last incident Jul 2025), this caused the training anchor to be months in the past, producing stale predictions (e.g. 2025-Q2, 2025-Q3 as "future" quarters).

**Fix:** Added `get_global_max_date()` which queries the latest `(YEAR, MONTH)` from OL_INCIDENTS once per process and caches it. `build_site_monthly_series()` and `build_bu_monthly_series()` now zero-pad their series to this global max date so every site's training anchor is current.

**Result:** After re-running `scripts/train_all_forecasters.py`, all 37 sites now show consistent future predictions: **2026-Q4 (Jan–Mar), 2026-Q1 (Apr–Jun), 2026-Q2 (Jul–Sep)** — the three quarters immediately after the global data end of January 2026.

### Verified Row Counts (2026-05-23)

| Table | Rows | Coverage |
|---|---|---|
| `risk_scores` | 777 | 2021-Q1 → 2026-Q4 |
| `predictions_cache` | 111 | 37 sites × 3 quarters (2026-Q4, 2026-Q1, 2026-Q2) |
| `model_runs` | 648 | All sites; champions have holdout_rmse, holdout_mape, n_quarters_history |
| `risk_drivers` | 278 | 37 sites |
| `recommendations` | 41 | 37 sites |
| `backtest_results` | 216 | 36 sites × 6 months (VLCTPP skipped: insufficient data); all rows have abs_pct_error |

### Predictions API integration note

**Do not call** `backend/app/api/predictions.py` directly from ML scripts.
Instead use the service layer:

```python
from app.services.model_meta import get_model_meta, get_backtest_summary, get_backtest_rows

with SessionLocal() as db:
    meta    = get_model_meta("BALCO", db)        # ModelMetaDict
    summary = get_backtest_summary("BALCO", db)  # BacktestSummaryDict
    rows    = get_backtest_rows("BALCO", db)     # list[BacktestRowDict]
```

`ModelMetaDict` keys match the `ModelMeta` Pydantic schema field-for-field:
`site`, `champion_model`, `holdout_rmse`, `holdout_mape`, `training_rows`, `last_trained_at`, `n_quarters_history`.

---

## Update — 2026-05-24 (Part 2 — Orchestration & Scheduling)

### Pipeline execution order (4 steps)

```
risk_scores → forecasters → backtest → drivers
```

| Step | Function | Duration | Notes |
|---|---|---|---|
| `risk_scores` | `step_risk_scores()` | ~3s | Composite score per site per quarter |
| `forecasters` | `step_forecasters()` | ~66s | Prophet + XGBoost; 37 sites × 3 quarters |
| `backtest` | `step_backtest()` | ~71s | 6-month walk-forward holdout; 36/37 sites (VLCTPP skipped) |
| `drivers` | `step_drivers()` | ~58s | SHAP drivers + recommendations with sparklines |

### New / changed files

| File | Purpose |
|---|---|
| `backend/app/core/config.py` | Added `RETRAIN_CRON: str = "0 2 * * *"` setting |
| `backend/app/core/scheduler.py` | APScheduler `BackgroundScheduler`; `start_scheduler()`, `shutdown_scheduler()`, `next_run_time()` |
| `backend/app/main.py` | Added `lifespan` context manager — starts scheduler on boot, logs next retrain time, exposes it on `GET /health` |
| `backend/app/services/pipeline_steps.py` | Added `step_backtest()` wrapper around `run_all_backtests()` |
| `backend/app/services/orchestrator.py` | Rewritten: 4-step pipeline, + `trigger_manual_retrain()`, `get_recent_runs()`, `get_freshness()` |
| `scripts/run_pipeline.py` | Full CLI (replaced stub): `--trigger`, `--verbose`, proper exit codes |

### Ingestion → pipeline hook

`api/ingest.py` already passes `on_success=lambda: background_tasks.add_task(run_full_pipeline, trigger="post_ingest")` into `ingest_csv()`.  No further changes needed.

### Scheduler

- **Default cron**: `"0 2 * * *"` (daily at 02:00 UTC)
- **Override**: set `RETRAIN_CRON=<5-field cron>` in `.env`
- **Next run visible**: `GET /health` returns `{"status": "ok", "next_scheduled_retrain": "..."}`
- **Misfire grace**: 1 hour; `coalesce=True` (one run even if multiple missed)

### Service functions (admin API uses these)

```python
from app.services.orchestrator import (
    trigger_manual_retrain,
    get_recent_runs,
    get_freshness,
)

# Trigger a manual run (returns immediately)
result = trigger_manual_retrain(background_tasks=bg)
# Returns: {"run_id": 7, "status": "queued"}

# Last N pipeline runs
runs = get_recent_runs(limit=10)
# Returns: list of {id, trigger, status, started_at, finished_at, total_duration_s, steps, error_summary}

# Data currency snapshot
info = get_freshness()
# Returns: {last_ingest_at, last_pipeline_run_at, pipeline_run_status,
#           latest_incident_date, latest_predicted_quarter,
#           n_sites_with_predictions, sites_missing_predictions}
```

### Verified run (run_id=6, 2026-05-24)

| Step | Status | Duration | Output |
|---|---|---|---|
| risk_scores | ok | 2.7s | 37 sites, 777 rows |
| forecasters | ok | 65.6s | 37 sites, 111 rows |
| backtest | ok | 70.6s | 36 ok, 1 skipped (VLCTPP), 216 rows |
| drivers | ok | 57.5s | 37 sites, 278 drivers, 47 recs |

`get_freshness()` output:
```
last_pipeline_run_at    : 2026-05-23T19:17:32.950000
pipeline_run_status     : success
latest_incident_date    : 2026-01-31
latest_predicted_quarter: 2026-Q1
n_sites_with_predictions: 37
sites_missing_predictions: []    ← all sites covered
last_ingest_at          : None   ← OL_INCIDENTS populated externally; no CSV uploads
```

**VLCTPP root-cause**: Insufficient monthly history for a 6-month holdout window (site has too few distinct months of data). It is excluded from `backtest_results` but still has predictions and risk scores.

---

## Update — 2026-05-24

### Schema Changes (migration 0008)

| Table | New Column | Type | Purpose |
|---|---|---|---|
| `risk_drivers` | `sparkline_data` | NVARCHAR(MAX) | JSON array of last-6-month counts per driver category, e.g. `"[2,0,5,3,7,4]"` |
| `recommendations` | `driver_link` | NVARCHAR(500) | Category / driver name that triggered the rule |

### Enriched risk_drivers and recommendations

`backend/app/ml/drivers.py` — `compute_drivers_for_site()` now:
- Computes **sparkline_data** (6-month monthly counts per category) via `build_category_sparklines()` in a single batch DB call
- Exposes **trend** (`up` / `down` / `flat`) and **pct_change_vs_last_qtr** already computed; now persisted

`backend/app/services/recommendations.py` — rules engine now:
- All rules set **driver_link** (which category triggered the rule)
- Two new rules added: `rule_high_velocity` (QoQ spike >50%) and `rule_material_handling` (material impact >60)
- Total rule count: 8 (order: high_velocity → access_control → material_handling → ir_worker → asset_property → reporting_lag → process_deviations → generic_fallback)
- All rules set `source="rules"`, `suggested_owner`, `impact_estimate`, `priority`

### New Service — `backend/app/services/drivers_service.py`

**Admin API uses these functions:**

```python
from app.services.drivers_service import regenerate_for_site, regenerate_all

# Single site — call from a POST /api/sites/{site}/regen endpoint
result = regenerate_for_site(site)
# Returns: {site, quarter, drivers_written, recs_written}

# All sites — for nightly job or manual refresh
summary = regenerate_all(dry_run=False)
# Returns: {sites_processed, sites_skipped, total_drivers, total_recs, errors}
```

### Verified Row Counts (2026-05-24)

| Table | Rows | Notes |
|---|---|---|
| `risk_drivers` | 278 | All 37 sites; **278/278 rows have non-null sparkline_data** |
| `recommendations` | 47 | 37 sites; 2 sites (IRON ORE ORISSA, MINES) have 3 recommendations each |

Sample output — BALCO top drivers (SHAP-scored, sparklines populated):

| driver_name | impact_score | trend | pct_change | sparkline_preview |
|---|---|---|---|---|
| Material | 100.00 | flat | +0.0 | `[0,0,0,0,0,0]` |
| Access Control | 89.35 | up | +0.0 | `[0,0,0,0,0,1]` |
| ASSET/PROPERTY | 49.80 | down | -55.6 | `[2,6,1,6,2,4]` |

Sample recommendations — IRON ORE ORISSA (3 recs, multiple rules fired):

| priority | action_text | driver_link | source |
|---|---|---|---|
| high | Review and address root causes of 'IR - Worker/...' | IR - Worker/ Union/ Transporters | rules |
| medium | Initiate community/labour engagement programme | IR - Worker/ Union/ Transporters | rules |
| medium | Schedule SOP/LSR refresher training and update procedure notices | SOP- LSR Violation | rules |
