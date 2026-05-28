# ML Explained — for future reference

Plain-language walkthrough of how the Risk Management ML pipeline works on
your `OL_INCIDENTS` data. Keep this open while you read the dashboard.

> Every chart and table you see in the **Data & Model Health** tab is built
> from the same numbers explained here. Nothing is hardcoded; if you replace
> the CSV with a different one, every number in the UI changes accordingly.


## 1. What the data actually is

Each row in `ol_incidents` is **one reported security/non-security incident**
at a specific Vedanta site. Important columns for ML:

| Column | Meaning |
|---|---|
| `SINAME` | Site (e.g. ENABLING, IRON ORE KARNATAKA) |
| `BUNAME` | Business Unit (e.g. ALUMINIUM SECTOR) |
| `OCCUREDDATE` | Date the incident occurred (`YYYY-MM-DD`) |
| `MONTH`, `QUARTER`, `YEAR` | Calendar month, fiscal quarter, calendar year |
| `LEVELNAME` | Severity: Low / Medium / High |
| `INCIDENTCATNAME` | Category: ASSET/PROPERTY, IR, Material, etc. |

**Fiscal-year convention used everywhere in this project:**

| Fiscal | Months |
|---|---|
| Q1 | Apr – Jun |
| Q2 | Jul – Sep |
| Q3 | Oct – Dec |
| Q4 | Jan – Mar |

So `2025-Q1` means **Apr–Jun 2025**, not Jan–Mar 2025.

## 2. The big rule — one model per site

The pipeline does **NOT** train one big model on all sites mixed together.
For every site that has enough data, it builds **its own** time series and
trains **its own** Prophet and XGBoost models. Sites with too little data
borrow from their business unit (explained in §6).


## 3. Building a site's time series

For one site (say `ENABLING`):

1. Pull every row where `SINAME = 'ENABLING'`.
2. Group by fiscal quarter, count rows.
3. Drop the **currently-open** quarter (it's still receiving incidents and
   would look artificially low).

The result is just a list of numbers like:

```
2023-Q1  →  382
2023-Q2  →  390
2023-Q3  →  283
2023-Q4  →    1     ← real data gap from your CSV
2024-Q1  →  669
…
2025-Q4  →   36
2026-Q4  →   44     ← latest complete quarter
```

That whole column of ~14 numbers is **the entire training input** for the
forecaster. No other site, no extra features, just this site's history.

## 4. Train / Holdout split

The pipeline pretends it doesn't know the future and tests itself.
It hides the **last 2 fiscal quarters** ("the holdout") and trains on
everything before them.

```
[…historical quarters…] [training] [training] [HIDDEN] [HIDDEN]
                                                  ↑           ↑
                                              holdout_1   holdout_2
```

After training, the model is asked to predict the two HIDDEN quarters.
We compare its guesses to what really happened.


## 5. The two models we train

For each site we train **two independent models** on the same series:

### Prophet
Facebook's time-series model. It learns a smooth trend plus yearly
seasonality from a column of dated values. Good for series with
seasonality or steady growth.

### XGBoost (with lag features)
A regression tree boosting model. We feed it features built from the
recent past:

| Feature | What it means |
|---|---|
| `lag_1` | Previous quarter's count |
| `lag_2` | Two quarters ago |
| `lag_4` | Four quarters ago (year-over-year) |
| `rolling_2q` | Average of the last 2 quarters |
| `fiscal_q` | Which fiscal quarter (1=Q4, 2=Q1, 3=Q2, 4=Q3) |

For multi-step prediction it uses each predicted quarter as input to the
next one (recursive forecasting).

### Champion selection
Whichever model has the **lower RMSE on the holdout** is marked
`is_champion = True` in the `model_runs` table. When both are roughly
tied, the dashboard reports the average ("ensemble").


## 6. Sparse sites — BU fallback

A site that has **fewer than 50 incidents** OR **fewer than 4 quarters**
of history can't train its own model. Instead the pipeline:

1. Finds the site's Business Unit (e.g. KAYAD → Hindustan Zinc Limited).
2. Builds the **same kind of time series at the BU level** (sum across
   every site in that BU).
3. Trains Prophet/XGBoost on the BU series.
4. Predicts the BU's next quarter.
5. Multiplies that BU prediction by the site's historical share. If KAYAD
   historically had 0.8% of HZL's incidents → site forecast = BU forecast × 0.008.

This is labelled `bu_prophet` in the dashboard. It's a useful estimate but
**it's a guess based on the BU pattern**, not a real per-site forecast.
The Site Detail drawer says so explicitly.

## 7. Computing the accuracy numbers — worked example

After training, suppose the holdout for site **EXAMPLE_SITE** is:

| Quarter | Actual | Predicted |
|---|---|---|
| 2025-Q3 | 88 | 78 |
| 2025-Q4 | 91 | 96 |

The pipeline computes three numbers:

### a) `abs_pct_error` (per holdout quarter)
```
2025-Q3 :  |88 - 78| / 88  × 100  =  11.4 %
2025-Q4 :  |91 - 96| / 91  × 100  =   5.5 %
```
Stored per-row in the `backtest_results` table.

### b) `mean_ape` (a.k.a. MAPE)
```
mean_ape = (11.4 + 5.5) / 2 = 8.45 %
```
"On average, the prediction was about 8.45% off."

### c) `pct_within_20` — the headline accuracy
Both holdout errors are ≤ 20% → **100% within ±20%**.
Read this as "the model nailed every test quarter to within 20%."

If a site had 4 holdout quarters and 3 of them were within 20%, you'd see
`75%`. If 1 of 2 was within 20%, you'd see `50%`.


## 8. Why ±20% and not ±0% (perfect)?

Incident counts are noisy by nature — even a "perfect" model would miss
by a few each quarter. ±20% is the industry rule of thumb for "useful for
planning". The system also tracks `pct_within_30` for a looser tolerance.

## 9. What the status pills mean

| Pill | Meaning | Colour |
|---|---|---|
| **Healthy** | `pct_within_20 ≥ 75%` | Green |
| **OK** | `pct_within_20 ≥ 50%` | Blue |
| **Sparse - BU fallback** | <50 incidents or <4 quarters → using BU model | Amber |
| **Low accuracy** | `pct_within_20 < 50%` | Orange |
| **No backtest** | Model exists but holdout actuals were all zero (error undefined) | Grey |
| **Insufficient data** | No model trained — predictions are zeros | Red |

## 10. System-wide accuracy

The KPI tile labelled "**System Accuracy**" at the top of the Data Health
tab is the **incident-weighted average** of every site's `pct_within_20`.
Big sites get more influence than tiny ones, which prevents a single
sparse site with 100% (because both 2 holdout actuals happened to be 0)
from dominating the headline.

The same response also includes the unweighted average and counts of
sites missing models or stuck on BU fallback.

## 11. What can change the numbers?

- **Re-running `scripts/run_pipeline.py`** with the same data: numbers can
  shift slightly because Prophet's internal sampling is not deterministic.
  Differences should be small.
- **Replacing the CSV** with a newer one: the entire pipeline re-derives
  everything. Sites that didn't exist before appear; sites that gained
  enough rows can move from "Sparse" to "Healthy"; the system accuracy
  rolls up to whatever the new evidence supports.
- **Adding more history**: backtest holdout stays at 2 quarters but the
  estimate gets more reliable as the training window grows.


## 12. Where each number lives in the database

| Value shown in UI | Backend table.column |
|---|---|
| Total incidents | `ol_incidents` (count of rows) |
| Distinct months / quarters | `ol_incidents` aggregation |
| First / last incident date | `MIN/MAX(ol_incidents.occureddate)` |
| Champion model | `model_runs.model_name` where `is_champion = true` |
| Holdout RMSE / MAPE | `model_runs.holdout_rmse`, `holdout_mape` |
| Train rows used | `model_runs.training_rows` |
| Per-quarter actual vs predicted | `backtest_results.actual / predicted / abs_pct_error` |
| Forecast (next 3 quarters) | `predictions_cache.predicted_count / lower_ci / upper_ci` |
| Confidence band | `predictions_cache.confidence_band` |
| System accuracy KPI | computed live from `backtest_results` aggregated by site |

If you want to inspect or audit anything by hand, those are the tables
to query in pgAdmin.
