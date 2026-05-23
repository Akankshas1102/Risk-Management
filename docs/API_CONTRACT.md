# API Contract — Risk Management Dashboard

**Source of truth** for the interface between the ML/backend layer and the frontend.  
Backend: FastAPI + SQL Server (`vedanta`). Base URL: `http://localhost:8000`.  
All dates are ISO-8601 strings. All monetary/numeric fields are native JSON numbers.

---

## Table of Contents

1. [GET /api/sites](#1-get-apisites)
2. [GET /api/kpis](#2-get-apikpis)
3. [GET /api/risk-scores](#3-get-apirisk-scores)
4. [GET /api/predictions](#4-get-apipredictions)
5. [GET /api/predictions/backtest](#5-get-apipredictionsbacktest)
6. [GET /api/drivers](#6-get-apidrivers)
7. [GET /api/recommendations](#7-get-apirecommendations)
8. [GET /api/incidents/by-type](#8-get-apiincidentsby-type)
9. [GET /api/incidents/by-category](#9-get-apiincidentsby-category)
10. [GET /api/incidents/by-site](#10-get-apiincidentsby-site)
11. [GET /api/incidents/trend](#11-get-apiincidentstrend)
12. [GET /api/incidents/heatmap](#12-get-apiincidentsheatmap)
13. [GET /api/admin/freshness](#13-get-apiadminfreshness)

---

## Fiscal Quarter Convention

> **Q4 = January–March · Q1 = April–June · Q2 = July–September · Q3 = October–December**
>
> The year in `"YYYY-Qn"` is always the **calendar year** of those months.  
> Example: `"2025-Q4"` = January–March **2025**; `"2026-Q1"` = April–June **2026**.
>
> Chronological sort key (used internally): `year × 10 + index` where  
> index order is Q4=0 · Q1=1 · Q2=2 · Q3=3.  
> So `2025-Q3` → `20253` > `2025-Q2` → `20252`.

---

## 1. GET /api/sites

Returns all sites with their business unit and incident count for the chosen (or latest complete) quarter, ordered by incident count descending.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `quarter` | `string` | No | Latest complete | `"YYYY-Qn"`, e.g. `"2025-Q3"` |
| `business_unit` | `string` | No | — | Filter to a single BU |

### Response

`200 OK` — `application/json` — Array of `SiteItem`

```json
[
  {
    "site": "VAB",
    "business_unit": "Iron Ore Business",
    "incident_count": 211
  },
  {
    "site": "TSPL",
    "business_unit": "TSPL",
    "incident_count": 143
  },
  {
    "site": "CLZS(CHANDERIYA)",
    "business_unit": "Hindustan Zinc Limited",
    "incident_count": 127
  },
  {
    "site": "VAL J",
    "business_unit": "ALUMINIUM SECTOR",
    "incident_count": 109
  },
  {
    "site": "VAL L",
    "business_unit": "ALUMINIUM SECTOR",
    "incident_count": 100
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `site` | `string` | Exact `SINAME` value from `OL_INCIDENTS` — use verbatim as a query param elsewhere |
| `business_unit` | `string \| null` | `null` when `BUNAME` is NULL in the source table |
| `incident_count` | `integer` | Count within the selected quarter only |

### Edge Cases

- Returns an **empty array** `[]` if no incidents are recorded for the requested quarter.
- `business_unit` is `null` for sites that have no BU recorded (e.g. `"HO"`).

---

## 2. GET /api/kpis

Single-row performance summary for a site (or all sites) in a quarter.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | No | All sites | Exact site name |
| `quarter` | `string` | No | Latest complete | `"YYYY-Qn"` |
| `business_unit` | `string` | No | — | BU filter (applied alongside `site` when both are provided) |

### Response

`200 OK` — `application/json` — Single `KPIResponse` object

```json
{
  "quarter": "2025-Q3",
  "site": "RDC",
  "total_incidents_qtr": 45,
  "delta_vs_last_qtr_pct": -38.4,
  "top_category": "Any Other",
  "top_category_share": 0.4,
  "predicted_next_qtr": 86,
  "risk_score": 36.9,
  "confidence_score": null
}
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `quarter` | `string` | Resolved quarter used for the calculation |
| `site` | `string \| null` | `null` when no `site` param provided (all-sites mode) |
| `total_incidents_qtr` | `integer` | Raw count from `OL_INCIDENTS` |
| `delta_vs_last_qtr_pct` | `float \| null` | `(current − previous) / previous × 100`; `null` if no prior quarter data |
| `top_category` | `string \| null` | `INCIDENTCATNAME` with the highest count this quarter |
| `top_category_share` | `float \| null` | Proportion `[0, 1]`; e.g. `0.4` means 40% |
| `predicted_next_qtr` | `integer \| null` | Nearest future prediction from `predictions_cache`; `null` if no model run yet |
| `risk_score` | `float \| null` | Composite score `[0, 100]` from `risk_scores` table; `null` when unavailable |
| `confidence_score` | `null` | **Always null** — reserved for a future phase |

### Edge Cases

- `delta_vs_last_qtr_pct`: returns `null` for the very first quarter in the data set (no previous to compare).
- `predicted_next_qtr`: returns `null` if site has no entry in `predictions_cache`. For sites with model `"none"` (e.g. `"VLCTPP"`, insufficient history), `predicted_next_qtr` will be `0` — the frontend should treat `0` as "Insufficient history".
- `risk_score`: is read from `risk_scores WHERE site = :s AND quarter = :q`. Returns `null` if the ML pipeline has not yet been run for this quarter.
- When `site` is not provided, `delta_vs_last_qtr_pct` and `top_category` reflect aggregate all-sites behaviour.

---

## 3. GET /api/risk-scores

Full risk-score history with optional per-site or latest-only filtering.

> **Implementation note:** This endpoint uses `DATABASE_URL`. In the current deployment `DATABASE_URL` and `SSMS_DATABASE_URL` both point to the same SQL Server `vedanta` instance, so all data is accessible. If the two are ever separated (e.g. PostgreSQL for `DATABASE_URL`) this endpoint will return empty results until migrated.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | No | — | Filter to one site |
| `business_unit` | `string` | No | — | Filter to one BU |
| `quarter` | `string` | No | — | Exact quarter, e.g. `"2025-Q3"` |
| `latest_only` | `boolean` | No | `false` | Return only the most recent scored quarter per site (uses `quarter_sort_key`) |

### Response

`200 OK` — `application/json` — Array of `RiskScoreResponse`

```json
[
  {
    "id": 1571,
    "site": "RDC",
    "business_unit": "Hindustan Zinc Limited",
    "quarter": "2025-Q3",
    "quarter_sort_key": 20253,
    "risk_score": 36.9365,
    "risk_level": "Low",
    "frequency_index": 0.21327,
    "severity_index": 0.276923,
    "velocity_index": 0.308219,
    "diversity_index": 1.0,
    "computed_at": "2026-05-19T17:15:55.073000"
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `id` | `integer` | Auto-increment PK |
| `site` | `string` | |
| `business_unit` | `string \| null` | |
| `quarter` | `string` | `"YYYY-Qn"` |
| `quarter_sort_key` | `integer \| null` | `year × 10 + [0–3]`; used for chronological ordering |
| `risk_score` | `float \| null` | Composite score `[0, 100]` — weighted sum of the four sub-indices |
| `risk_level` | `string \| null` | `"Low"` / `"Medium"` / `"High"` / `"Critical"` |
| `frequency_index` | `float \| null` | Normalised incident frequency `[0, 1]` |
| `severity_index` | `float \| null` | Normalised severity `[0, 1]` |
| `velocity_index` | `float \| null` | Normalised quarter-on-quarter growth rate `[0, 1]` |
| `diversity_index` | `float \| null` | Normalised category diversity (Shannon entropy) `[0, 1]` |
| `computed_at` | `string \| null` | ISO-8601 datetime of last computation |

### Edge Cases

- With `latest_only=true` and no `site` filter: returns one row per site (highest `quarter_sort_key`). Use this for the all-sites heatmap or ranking views.
- Quarters with zero incidents will have `risk_score = 0` and all sub-indices `= 0`.
- Results ordered by `quarter_sort_key DESC, site ASC`.

---

## 4. GET /api/predictions

Cached ML forecast for the next 3 fiscal quarters, plus champion-model metadata. Populated by `scripts/train_all_forecasters.py`.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | No | — | Filter to one site (pass for all site-specific views) |
| `business_unit` | `string` | No | — | BU filter |

### Response

`200 OK` — `application/json` — `PredictionsResponse` object

```json
{
  "model_meta": {
    "site": "BALCO",
    "champion_model": "xgboost",
    "holdout_rmse": 1.649,
    "holdout_mape": 22.29,
    "training_rows": 22,
    "last_trained_at": "2026-05-20T10:53:55.767000",
    "n_quarters_history": 21
  },
  "predictions": [
    {
      "id": 557,
      "site": "BALCO",
      "business_unit": "ALUMINIUM SECTOR",
      "target_quarter": "2026-Q1",
      "predicted_count": 23.4,
      "lower_ci": 14.5,
      "upper_ci": 32.7,
      "model_name": "ensemble",
      "trained_at": "2026-05-20T10:53:55.767000",
      "training_data_through": "2026-Q4",
      "confidence_band": "high"
    },
    {
      "id": 558,
      "site": "BALCO",
      "business_unit": "ALUMINIUM SECTOR",
      "target_quarter": "2026-Q2",
      "predicted_count": 17.1,
      "lower_ci": 9.1,
      "upper_ci": 25.4,
      "model_name": "ensemble",
      "trained_at": "2026-05-20T10:53:55.767000",
      "training_data_through": "2026-Q4",
      "confidence_band": "high"
    },
    {
      "id": 556,
      "site": "BALCO",
      "business_unit": "ALUMINIUM SECTOR",
      "target_quarter": "2026-Q4",
      "predicted_count": 13.0,
      "lower_ci": 6.4,
      "upper_ci": 19.9,
      "model_name": "ensemble",
      "trained_at": "2026-05-20T10:53:55.767000",
      "training_data_through": "2026-Q4",
      "confidence_band": "high"
    }
  ]
}
```

### `model_meta` Field Reference

| Field | Type | Notes |
|---|---|---|
| `site` | `string` | |
| `champion_model` | `string \| null` | `"prophet"` / `"xgboost"` / `"ensemble"` / `"bu_prophet"` / `"none"` |
| `holdout_rmse` | `float \| null` | Root-mean-squared error on the 3-month holdout set |
| `holdout_mape` | `float \| null` | Mean absolute percentage error on holdout, as a percentage (e.g. `22.29` = 22.3%) |
| `training_rows` | `integer \| null` | Months of data used for final model training |
| `last_trained_at` | `string \| null` | ISO-8601 datetime |
| `n_quarters_history` | `integer \| null` | Count of distinct quarters in `risk_scores` for this site — proxy for history depth |

### `predictions[]` Field Reference

| Field | Type | Notes |
|---|---|---|
| `id` | `integer` | Auto-increment PK |
| `site` | `string` | |
| `business_unit` | `string \| null` | |
| `target_quarter` | `string` | The fiscal quarter being predicted, e.g. `"2026-Q1"` |
| `predicted_count` | `float \| null` | Point-estimate incident count (quarter total) |
| `lower_ci` | `float \| null` | 80% confidence interval lower bound |
| `upper_ci` | `float \| null` | 80% confidence interval upper bound |
| `model_name` | `string \| null` | Which model produced this row: `"ensemble"` / `"prophet"` / `"xgboost"` / `"bu_prophet"` / `"none"` |
| `trained_at` | `string \| null` | ISO-8601 datetime of training run |
| `training_data_through` | `string \| null` | Last quarter included in training data, e.g. `"2026-Q4"` |
| `confidence_band` | `string \| null` | `"high"` (≥24 months data) / `"medium"` (12–23 months) / `"low"` (<12 months or BU fallback) |

### Model Selection Logic

| Condition | Model used | `confidence_band` |
|---|---|---|
| Site has ≥50 incidents AND ≥12 months data | Prophet + XGBoost ensemble | `"high"` or `"medium"` |
| Site has sufficient data; one model fails | Single model (prophet or xgboost) | `"medium"` |
| Site below threshold; BU series available | `"bu_prophet"` (scaled by site share) | `"low"` |
| No usable data at all | `"none"` — all predictions are `0.0` | `"low"` |

### Edge Cases

- **Insufficient history** (`model_name = "none"`): `predicted_count = 0.0`, `lower_ci = 0.0`, `upper_ci = 0.0`. Example: site `"VLCTPP"` (3 total incidents). Frontend should display `"Insufficient history"` rather than `0`.
- **`predictions` order**: sorted by `target_quarter` ascending (lexicographic), which is **not** strictly chronological due to the Q4 < Q1 within-year anomaly. Fiscal chronological order: Q4 2025 → Q1 2026 → Q2 2026 → Q3 2026.
- **`model_meta` when `site` not provided**: reflects the first prediction row's site. For all-site views, call with an explicit `site=` param.
- **Stale predictions**: if the ML pipeline has not been run recently, `training_data_through` may lag the latest data in `OL_INCIDENTS`. The `model_meta.last_trained_at` field reveals this.

---

## 5. GET /api/predictions/backtest

Six-month walk-forward holdout results for the champion model at a site. The model is trained on data up to six months before the site's latest data point; actual vs. predicted for each month in that window is stored in `backtest_results`. Populated by `scripts/compute_backtest.py`.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | **Yes** | — | Exact site name |

### Response

`200 OK` — `application/json` — Array of `BacktestPoint`, ordered by `month` ascending

```json
[
  {
    "month": "2025-08",
    "actual": 5.0,
    "predicted": 9.35,
    "model_name": "xgboost"
  },
  {
    "month": "2025-09",
    "actual": 6.0,
    "predicted": 7.51,
    "model_name": "xgboost"
  },
  {
    "month": "2025-10",
    "actual": 2.0,
    "predicted": 4.97,
    "model_name": "xgboost"
  },
  {
    "month": "2025-11",
    "actual": 6.0,
    "predicted": 3.68,
    "model_name": "xgboost"
  },
  {
    "month": "2025-12",
    "actual": 3.0,
    "predicted": 5.19,
    "model_name": "xgboost"
  },
  {
    "month": "2026-01",
    "actual": 5.0,
    "predicted": 8.41,
    "model_name": "xgboost"
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `month` | `string` | `"YYYY-MM"` format |
| `actual` | `float \| null` | True monthly incident count from `OL_INCIDENTS` |
| `predicted` | `float \| null` | Monthly prediction generated by the champion model |
| `model_name` | `string \| null` | `"prophet"` or `"xgboost"` — the single model used (not ensemble; ensemble not applicable to per-month backtest) |

### Edge Cases

- Returns `[]` for sites with insufficient history (e.g. `"VLCTPP"`, `model_name = "none"` — backtest computation is skipped).
- Returns `[]` if `compute_backtest.py` has not been run.
- For BU-fallback sites, `actual` reflects the site's true monthly count; `predicted` is the BU-level prediction scaled by the site's historical share.
- Always exactly 6 rows per site when populated (or 0 when skipped).

---

## 6. GET /api/drivers

Top SHAP-based risk drivers for a site, sorted by `impact_score` descending. Populated by `scripts/compute_drivers_and_recs.py`.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | **Yes** | — | Exact site name |
| `quarter` | `string` | No | Most recent batch | `"YYYY-Qn"` |
| `n` | `integer` | No | `10` | Max rows to return (1–50) |

### Response

`200 OK` — `application/json` — Array of `DriverItem`

```json
[
  {
    "id": 1265,
    "site": "RDC",
    "quarter": "2025-Q3",
    "driver_name": "Agitation by community and workers",
    "category": "Agitation by community and workers",
    "impact_score": 100.0,
    "trend": "down",
    "pct_change_vs_last_qtr": -90.0,
    "computed_at": "2026-05-19T17:17:23.430000"
  },
  {
    "id": 1266,
    "site": "RDC",
    "quarter": "2025-Q3",
    "driver_name": "ASSET/PROPERTY",
    "category": "ASSET/PROPERTY",
    "impact_score": 44.07,
    "trend": "down",
    "pct_change_vs_last_qtr": -20.0,
    "computed_at": "2026-05-19T17:17:23.430000"
  },
  {
    "id": 1267,
    "site": "RDC",
    "quarter": "2025-Q3",
    "driver_name": "IR",
    "category": "IR",
    "impact_score": 31.16,
    "trend": "up",
    "pct_change_vs_last_qtr": 0.0,
    "computed_at": "2026-05-19T17:17:23.430000"
  },
  {
    "id": 1268,
    "site": "RDC",
    "quarter": "2025-Q3",
    "driver_name": "IR - Worker/ Union/ Transporters",
    "category": "IR - Worker/ Union/ Transporters",
    "impact_score": 14.96,
    "trend": "down",
    "pct_change_vs_last_qtr": -88.9,
    "computed_at": "2026-05-19T17:17:23.430000"
  },
  {
    "id": 1269,
    "site": "RDC",
    "quarter": "2025-Q3",
    "driver_name": "Dharna",
    "category": "Dharna",
    "impact_score": 10.99,
    "trend": "flat",
    "pct_change_vs_last_qtr": 0.0,
    "computed_at": "2026-05-19T17:17:23.430000"
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `id` | `integer` | |
| `site` | `string` | |
| `quarter` | `string` | Quarter to which this driver applies |
| `driver_name` | `string \| null` | Human-readable label (mirrors `category` in current impl) |
| `category` | `string \| null` | Raw `INCIDENTCATNAME` value |
| `impact_score` | `float \| null` | Normalised SHAP importance `[0, 100]`; the top driver for a site is always `100.0` |
| `trend` | `string \| null` | `"up"` / `"down"` / `"flat"` — direction vs. previous quarter |
| `pct_change_vs_last_qtr` | `float \| null` | `%` change in this category's count vs. prior quarter; `0.0` when the category is new |
| `computed_at` | `string \| null` | ISO-8601 datetime |

### Edge Cases

- When `quarter` is omitted, returns drivers from the most recently computed batch (matched by `computed_at` max). This may differ from the latest quarter in `OL_INCIDENTS` if the pipeline has not been re-run.
- Returns `[]` for new sites not yet processed by `compute_drivers_and_recs.py`.

---

## 7. GET /api/recommendations

Rules-based action items derived from the top risk drivers, ordered high → medium → low priority.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | **Yes** | — | Exact site name |
| `quarter` | `string` | No | Most recent batch | `"YYYY-Qn"` |

### Response

`200 OK` — `application/json` — Array of `RecommendationItem`

```json
[
  {
    "id": 189,
    "site": "RDC",
    "quarter": "2025-Q3",
    "action_text": "Review and address root causes of 'Agitation by community and workers' incidents",
    "priority": "high",
    "impact_estimate": "Top driver accounts for 100/100 of predicted risk",
    "suggested_owner": "Site EHS Manager",
    "status": "open",
    "source": "rules",
    "created_at": "2026-05-19T17:17:16.347000"
  },
  {
    "id": 190,
    "site": "RDC",
    "quarter": "2025-Q3",
    "action_text": "Conduct root-cause analysis and implement corrective actions for ASSET/PROPERTY incidents",
    "priority": "medium",
    "impact_estimate": "Driver accounts for 44/100 of predicted risk",
    "suggested_owner": "Site EHS Manager",
    "status": "open",
    "source": "rules",
    "created_at": "2026-05-19T17:17:16.347000"
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `id` | `integer` | |
| `site` | `string` | |
| `quarter` | `string` | |
| `action_text` | `string \| null` | The recommendation sentence |
| `priority` | `string \| null` | `"high"` / `"medium"` / `"low"` |
| `impact_estimate` | `string \| null` | Narrative estimate of impact (free text) |
| `suggested_owner` | `string \| null` | Role or team responsible |
| `status` | `string \| null` | `"open"` (only open items are returned by this endpoint) |
| `source` | `string \| null` | `"rules"` (ML-generated LLM source reserved for future phase) |
| `created_at` | `string \| null` | ISO-8601 datetime |

### Edge Cases

- Only `status = "open"` records are returned. If all recommendations for a site have been resolved, returns `[]`.
- When `quarter` is omitted, returns recommendations from the batch matching the most recent `created_at` for that site.

---

## 8. GET /api/incidents/by-type

Incident counts grouped by `INCIDENTTYPENAME` for a site and quarter.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | No | All sites | |
| `quarter` | `string` | No | Latest complete | `"YYYY-Qn"` |
| `business_unit` | `string` | No | — | |

### Response

`200 OK` — `application/json` — Array of `IncidentTypeCount`, ordered by count descending

```json
[
  {
    "incident_type": "SECURITY INCIDENTS",
    "count": 86
  },
  {
    "incident_type": "NON-SECURITY INCIDENTS-IR/PR",
    "count": 23
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `incident_type` | `string` | `INCIDENTTYPENAME`; falls back to `"Unknown"` when NULL |
| `count` | `integer` | |

### Edge Cases

- Only two distinct `INCIDENTTYPENAME` values appear in the current data: `"SECURITY INCIDENTS"` and `"NON-SECURITY INCIDENTS-IR/PR"`. A site with all one type returns a single-element array.

---

## 9. GET /api/incidents/by-category

Incident counts grouped by `INCIDENTCATNAME`, capped at top 15 categories, with an `"Other"` bucket for the remainder.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | No | All sites | |
| `quarter` | `string` | No | Latest complete | `"YYYY-Qn"` |
| `business_unit` | `string` | No | — | |

### Response

`200 OK` — `application/json` — Array of `IncidentCategoryCount`, ordered by count descending. Maximum 16 elements (15 named + `"Other"`).

```json
[
  {
    "category": "SOP- LSR Violation",
    "count": 36
  },
  {
    "category": "Access Control",
    "count": 35
  },
  {
    "category": "PR - Villagers/ Neighborhood",
    "count": 19
  },
  {
    "category": "Material",
    "count": 10
  },
  {
    "category": "ASSET/PROPERTY",
    "count": 5
  },
  {
    "category": "IR - Worker/ Union/ Transporters",
    "count": 4
  },
  {
    "category": "Other",
    "count": 0
  }
]
```

> The `"Other"` element is only appended when there are more than 15 distinct categories. Its count is the aggregate of all categories beyond the top 15.

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `category` | `string` | Raw `INCIDENTCATNAME` or `"Unknown"` (NULL source) or `"Other"` (rollup) |
| `count` | `integer` | |

### Observed Category Values (non-exhaustive)

`Access Control` · `Agitation by community and workers` · `Any Other` · `ASSET/PROPERTY` ·  
`Dharna` · `Fire` · `IR` · `IR - Worker/ Union/ Transporters` · `Leaks` · `Material` ·  
`PR - Villagers/ Neighborhood` · `SOP- LSR Violation`

---

## 10. GET /api/incidents/by-site

Incident counts per site for a given quarter, ordered by count descending. Used for site-ranking views and the bubble/bar charts.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `quarter` | `string` | No | Latest complete | `"YYYY-Qn"` |
| `business_unit` | `string` | No | — | Filter to a BU |

### Response

`200 OK` — `application/json` — Array of `IncidentSiteCount`

```json
[
  {
    "site": "VAB",
    "business_unit": "Iron Ore Business",
    "count": 211
  },
  {
    "site": "TSPL",
    "business_unit": "TSPL",
    "count": 143
  },
  {
    "site": "CLZS(CHANDERIYA)",
    "business_unit": "Hindustan Zinc Limited",
    "count": 127
  },
  {
    "site": "VAL J",
    "business_unit": "ALUMINIUM SECTOR",
    "count": 109
  },
  {
    "site": "VAL L",
    "business_unit": "ALUMINIUM SECTOR",
    "count": 100
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `site` | `string` | |
| `business_unit` | `string \| null` | |
| `count` | `integer` | Incidents in the selected quarter |

---

## 11. GET /api/incidents/trend

Monthly incident time series for a site (or all sites), with a computed all-sites average for benchmarking.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `site` | `string` | No | All sites | |
| `months` | `integer` | No | `12` | Lookback window (1–60 months) |
| `business_unit` | `string` | No | — | |

### Response

`200 OK` — `application/json` — Array of `TrendPoint`, ordered by `(year, month)` ascending

```json
[
  {
    "year": 2025,
    "month": 7,
    "month_label": "Jul 2025",
    "count": 22,
    "all_sites_avg": 21.9
  },
  {
    "year": 2025,
    "month": 8,
    "month_label": "Aug 2025",
    "count": 10,
    "all_sites_avg": 15.8
  },
  {
    "year": 2025,
    "month": 9,
    "month_label": "Sep 2025",
    "count": 6,
    "all_sites_avg": 17.2
  },
  {
    "year": 2025,
    "month": 10,
    "month_label": "Oct 2025",
    "count": 2,
    "all_sites_avg": 12.1
  },
  {
    "year": 2025,
    "month": 11,
    "month_label": "Nov 2025",
    "count": 6,
    "all_sites_avg": 11.4
  },
  {
    "year": 2025,
    "month": 12,
    "month_label": "Dec 2025",
    "count": 3,
    "all_sites_avg": 9.8
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `year` | `integer` | Calendar year |
| `month` | `integer` | Calendar month `1–12` |
| `month_label` | `string` | `"MMM YYYY"` format, e.g. `"Jul 2025"` |
| `count` | `integer` | Incident count for this site (or 0 if no incidents recorded this month) |
| `all_sites_avg` | `float` | Mean **per-site** monthly count across all sites for this month (not the total). Always ≥ 0; rounded to 2 decimal places. |

### Edge Cases

- A month with no incidents for the selected site has `count = 0`; the month still appears in the response if any site had incidents.
- `all_sites_avg` is computed from a sub-query that groups by `(year, month, site)` first, then averages — so it reflects the average across **active sites** that month, not across all 37.
- Results cover all months within the `[today − months, today]` window that have data from any site.
- `month_label` uses `calendar.month_abbr`, giving three-letter abbreviations: `Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec`.

---

## 12. GET /api/incidents/heatmap

Per-site likelihood vs. impact scores for the risk heatmap scatter chart. Scores are min-max normalised across all sites in the selected quarter.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `quarter` | `string` | No | Latest complete | `"YYYY-Qn"` |
| `business_unit` | `string` | No | — | |

### Response

`200 OK` — `application/json` — Array of `HeatmapPoint`, ordered by frequency descending

```json
[
  {
    "site": "VAB",
    "business_unit": "Iron Ore Business",
    "likelihood_score": 1.0,
    "impact_score": 1.0,
    "risk_band": "Critical"
  },
  {
    "site": "TSPL",
    "business_unit": "TSPL",
    "likelihood_score": 0.6057,
    "impact_score": 0.4479,
    "risk_band": "Medium"
  },
  {
    "site": "CLZS(CHANDERIYA)",
    "business_unit": "Hindustan Zinc Limited",
    "likelihood_score": 0.5094,
    "impact_score": 0.3733,
    "risk_band": "Low"
  },
  {
    "site": "VAL J",
    "business_unit": "ALUMINIUM SECTOR",
    "likelihood_score": 0.4038,
    "impact_score": 0.3493,
    "risk_band": "Low"
  }
]
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `site` | `string` | |
| `business_unit` | `string \| null` | |
| `likelihood_score` | `float` | Min-max normalised incident frequency `[0.0, 1.0]`. The site with the most incidents gets `1.0`; the site with the fewest gets `0.0`. |
| `impact_score` | `float` | Min-max normalised severity-weighted count `[0.0, 1.0]`. Severity weights: High=3, Medium=2, Low/other=1. |
| `risk_band` | `string` | `"Low"` / `"Medium"` / `"High"` / `"Critical"` based on `(likelihood + impact) / 2`: `≤0.40`=Low, `0.41–0.65`=Medium, `0.66–0.85`=High, `>0.85`=Critical. |

### Edge Cases

- **Single site in quarter**: both scores will be `0.5` (constant — min == max means the normalisation returns 0.5 for all).
- **Returns `[]`** if no incidents are recorded for the requested quarter.
- When `business_unit` filter results in fewer than 2 active sites, scores lose comparative meaning.

---

## 13. GET /api/admin/freshness

Snapshot of data currency across the pipeline. Used by the `FreshnessFooter` component to show staleness warnings.

### Query Parameters

None.

### Response

`200 OK` — `application/json`

```json
{
  "last_pipeline_run_at": "2026-05-19T17:17:28.737000",
  "pipeline_run_status": "success",
  "latest_data_date": "2026-01-31",
  "latest_predicted_quarter": "2026-Q1",
  "last_ingest_at": null
}
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `last_pipeline_run_at` | `string \| null` | ISO-8601 datetime of the most recently **finished** `pipeline_runs` row; `null` if pipeline has never completed |
| `pipeline_run_status` | `string \| null` | `"success"` / `"error"` / `"running"` from that row; `null` if no run |
| `latest_data_date` | `string \| null` | Maximum `OCCUREDDATE` in `OL_INCIDENTS` where the date is a valid `"YYYY-MM-DD"` string; reflects how fresh the raw incident data is |
| `latest_predicted_quarter` | `string \| null` | The `target_quarter` of the most recently **trained** prediction row (by `trained_at`); indicates the horizon of the current model |
| `last_ingest_at` | `null` | **Always `null`** — `OL_INCIDENTS` is populated externally (not via this pipeline); field reserved for future automated ingest tracking |

### Edge Cases

- `last_pipeline_run_at` is `null` on a fresh deployment before any pipeline run.
- `latest_data_date` may be significantly earlier than today if the external data feed is delayed. The frontend should warn if the gap exceeds, e.g., 30 days.

---

## Common Error Responses

All endpoints may return the following FastAPI-standard errors:

| Status | Body | When |
|---|---|---|
| `422 Unprocessable Entity` | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` | Invalid query param type (e.g. non-boolean `latest_only`) |
| `500 Internal Server Error` | `{"detail": "Internal Server Error"}` | DB connection failure or unhandled exception |

There is no `401`/`403` — the API is unauthenticated in the current deployment.

---

## Caching Behaviour

Endpoints in the analytics router (`/api/sites`, `/api/kpis`, `/api/incidents/*`) cache results in a module-level Python dict with a **5-minute TTL**. Cache key includes site, quarter, and BU. The frontend uses TanStack Query with matching `staleTime: 5 * 60_000`.

Prediction and driver endpoints (`/api/predictions`, `/api/drivers`, `/api/recommendations`) are **not cached server-side** — their source tables update only when the ML scripts are re-run manually.

---

## Running Data Refreshes

```bash
# Re-run the full ML pipeline (also available via POST /api/admin/retrain)
python scripts/compute_risk_scores.py
python scripts/train_all_forecasters.py
python scripts/compute_drivers_and_recs.py
python scripts/compute_backtest.py
```

---

*Generated: 2026-05-20 · Last verified against live `vedanta` database.*
