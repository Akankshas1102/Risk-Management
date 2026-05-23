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
