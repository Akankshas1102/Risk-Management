# Changes made on 28 May 2026 (uncommitted)

These are the changes made **today** that are NOT yet committed. Everything from
27 May and earlier (diagnostics tab, frontend files, quarterly forecasting, sMAPE,
backtest-quarterly switch) is already committed + pushed (commits `4eebe20`,
`a41d0bc`, `194f524`, `d8a2d73`) and is safe.

**Theme of today's work:** wire the new `CATEGORY_GROUP` column (12 clean groups)
into the ML pipeline, plus fix the `/api/sites` "only 24 sites" bug.

## How to re-apply after pulling your friend's changes

```bash
# 1. Pull your friend's work first
git pull

# 2. Re-apply today's changes from the patch
git apply changes_28may2026.patch

# 3. If git apply reports conflicts (friend touched the same files),
#    apply by hand using the per-file notes below.

# 4. Re-run the pipeline so the DB reflects the changes
python scripts/load_csv_to_db.py
python scripts/run_pipeline.py
```

The exact diff is saved in **`changes_28may2026.patch`** next to this file.

---

## File-by-file changes

### 1. `backend/app/models/ol_incidents.py`
- **What:** Added `CATEGORY_GROUP = Column("category_group", String)` on the `OLIncident` model (placed after `INCIDENTCATNAME`).
- **Why:** The loader builds the table from this model and drops any column the model doesn't declare. This line is required for `category_group` to exist in the `ol_incidents` table.

### 2. `scripts/load_csv_to_db.py`
- **What:** Changed `CSV_PATH` to a preference chain: `OL_INCIDENTS_properly_cleaned.csv` → `OL_INCIDENTS_clean.csv` → raw export (first existing wins).
- **Why:** The new cleaned CSV (encoding fixed, severity Low/Medium/High only, plus the `CATEGORY_GROUP` column) lives at `data/raw/OL_INCIDENTS_properly_cleaned.csv`.

### 3. `backend/app/services/pipeline_steps.py`
- **What:** In `step_risk_scores`, the diversity-index query now selects `OLIncident.CATEGORY_GROUP` (aliased as `incident_category`) instead of `INCIDENTCATNAME`.
- **Why:** Shannon entropy over 12 balanced groups is a more meaningful diversity signal than over 41 imbalanced categories. (No other index changed; risk-score weights untouched.)

### 4. `backend/app/ml/drivers.py`
- **What:** Both `_load_quarterly_cat_raw` (the SHAP pivot source) and `_load_monthly_cat_raw` (the sparkline source) now select `OLIncident.CATEGORY_GROUP` instead of `INCIDENTCATNAME`.
- **Why:** SHAP attribution gets cleaner signal from 12 groups; sparklines must use the same grouping so they line up with the new driver names.

### 5. `backend/app/services/recommendations.py`
- **What:** Updated rule keyword matching to the new group names:
  - `rule_access_control`: `"access control"` → `"access"` (matches "Access & Intrusion")
  - `rule_ir_worker`: `"ir"+"worker"` / `"agitation"` → `"industrial"` (matches "Industrial Relations")
  - `rule_process_deviations`: simplified to `"sop"` / `"safety"` (matches "Safety & SOP Violation")
  - `rule_asset_property` (`"asset"`) and `rule_material_handling` (`"material"`) already matched their groups — left as-is.
- **Why:** Driver names are now group names; the old keyword strings no longer matched. All other rule logic unchanged.

### 6. `backend/app/api/analytics.py`  (Bug fix: `/api/sites`)
- **What:** `/api/sites` no longer filters to the latest complete quarter. It now returns ALL distinct sites in `ol_incidents` since 2020 (`incident_count` is now the site's total, and `quarter` param is accepted but ignored). Cache key changed to `sites:all:{bu}`.
- **Why:** 14 sites had predictions/drivers/risk scores computed but were unselectable in the UI because they had no incidents last quarter. Verified: 24 → 38 sites. Response shape unchanged.

---

## New data file (not in the patch)
- `data/raw/OL_INCIDENTS_properly_cleaned.csv` — your cleaned CSV (14,290 rows, 33 cols, `CATEGORY_GROUP` with 12 groups). It's a data file, so re-apply by keeping/regenerating it, not via the code patch.

## NOT done yet (planned, interrupted)
- **Bug 2 — Predictions tab backtest overlay line.** The dashed orange backtest line is missing because backtest rows now use quarter labels (`"2025-Q4"`) but `frontend/src/tabs/Predictions.tsx` matches them against monthly keys (`"2025-10"`). This was the next task when work was paused. No code change has been made for it yet.

## Verification snapshot (after today's changes, run_id=4)
- Pipeline: all 4 steps OK.
- `risk_drivers` now grouped into the 12 clean `CATEGORY_GROUP` values (a few stale orphan rows remain under old site names `NAN` / `RAM Agucha` / `RJON-Upstream` from 27-May runs — cosmetic).
- `/api/sites`: 38 sites (was 24).
