"""
Admin API: pipeline management and data freshness.

POST /api/admin/retrain        — kick off a manual full pipeline run
GET  /api/admin/runs           — last 20 pipeline_runs rows
GET  /api/admin/freshness      — snapshot of data currency
GET  /api/admin/diagnostics    — per-site data quality + model health + alerts
"""

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.ssms import get_ssms_db
from app.core.scheduler import next_run_time
from app.models.pipeline import PipelineRun
from app.models.predictions import PredictionsCache
from app.services.orchestrator import create_queued_run, run_full_pipeline

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# POST /api/admin/retrain
# ---------------------------------------------------------------------------

@router.post("/retrain")
async def retrain(background_tasks: BackgroundTasks, db: Session = Depends(get_ssms_db)):
    """
    Trigger a full pipeline run (risk scores → forecasters → drivers).
    Returns immediately with the pipeline_run_id; check /api/admin/runs for status.
    """
    run_id = create_queued_run("manual")
    background_tasks.add_task(run_full_pipeline, trigger="manual", run_id=run_id)
    return {"pipeline_run_id": run_id, "status": "queued"}


# ---------------------------------------------------------------------------
# GET /api/admin/runs
# ---------------------------------------------------------------------------

@router.get("/runs")
def list_runs(db: Session = Depends(get_ssms_db)):
    """Return the last 20 pipeline runs with per-step outcomes."""
    rows = db.execute(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(20)
    ).scalars().all()

    results = []
    for run in rows:
        results.append({
            "id": run.id,
            "trigger": run.trigger,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "steps": run.steps,
            "error_summary": run.error_summary,
        })
    return results


# ---------------------------------------------------------------------------
# GET /api/admin/freshness
# ---------------------------------------------------------------------------

@router.get("/freshness")
def data_freshness(db: Session = Depends(get_ssms_db)):
    """
    Snapshot of data currency across the pipeline.

    Fields
    ------
    last_pipeline_run_at    : most recent finished pipeline_runs row
    pipeline_run_status     : its status
    latest_data_date        : max OCCUREDDATE in OL_INCIDENTS
    latest_predicted_quarter: most recently created prediction target
    """
    # Last pipeline run
    run_row = db.execute(
        select(PipelineRun.finished_at, PipelineRun.status)
        .where(PipelineRun.finished_at.isnot(None))
        .order_by(PipelineRun.finished_at.desc())
        .limit(1)
    ).first()

    # Latest incident date (OCCUREDDATE is varchar YYYY-MM-DD; MAX works on ISO strings)
    data_date_row = db.execute(
        text("""
            SELECT MAX(occureddate) AS latest_date
            FROM ol_incidents
            WHERE CAST(NULLIF(year, '') AS INTEGER) > 2000
              AND LENGTH(occureddate) = 10
        """)
    ).first()

    # Latest predicted quarter (sort by trained_at as proxy for recency)
    pred_row = db.execute(
        select(PredictionsCache.target_quarter, PredictionsCache.trained_at)
        .order_by(PredictionsCache.trained_at.desc())
        .limit(1)
    ).first()

    return {
        "last_pipeline_run_at": (
            run_row.finished_at.isoformat() if run_row and run_row.finished_at else None
        ),
        "pipeline_run_status": run_row.status if run_row else None,
        "latest_data_date": data_date_row.latest_date if data_date_row else None,
        "latest_predicted_quarter": pred_row.target_quarter if pred_row else None,
        "last_ingest_at": None,  # N/A — OL_INCIDENTS is populated externally
    }


# ---------------------------------------------------------------------------
# GET /api/admin/diagnostics
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = ("Low", "Medium", "High")
_MIN_INCIDENTS = 50
_MIN_MONTHS = 12


def _derive_status(
    incidents: int,
    n_months: int,
    champion_model: Optional[str],
    pct_within_20: Optional[float],
) -> str:
    """One-line human label for a site's data/model health."""
    if not champion_model or champion_model == "none":
        return "Insufficient data"
    if incidents < _MIN_INCIDENTS or n_months < _MIN_MONTHS:
        return "Sparse - BU fallback"
    if pct_within_20 is None:
        return "No backtest"
    if pct_within_20 >= 75:
        return "Healthy"
    if pct_within_20 >= 50:
        return "OK"
    return "Low accuracy"


@router.get("/diagnostics")
def diagnostics(db: Session = Depends(get_ssms_db)):
    """
    One-shot health snapshot powering the Data Health tab:
      - pipeline.last_run     : trigger, status, duration, per-step results
      - pipeline.next_run_at  : next scheduled retrain (UTC ISO)
      - freshness             : latest data date, latest predicted quarter
      - sites[]               : per-site data quality + champion model + backtest accuracy
      - alerts.site_variants  : SINAME values that collapse to the same canonical form
      - alerts.category_variants : INCIDENTCATNAME values that collapse to the same canonical form
      - alerts.data_issues    : null/invalid counts in critical columns
    """
    # ── 1. Pipeline status ───────────────────────────────────────────────
    last_run_row = db.execute(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    last_run: dict[str, Any] = {}
    if last_run_row is not None:
        steps = last_run_row.steps or {}
        total_s = round(sum(s.get("duration_s", 0) for s in steps.values()), 1) if steps else None
        last_run = {
            "id": last_run_row.id,
            "trigger": last_run_row.trigger,
            "status": last_run_row.status,
            "started_at": last_run_row.started_at.isoformat() if last_run_row.started_at else None,
            "finished_at": last_run_row.finished_at.isoformat() if last_run_row.finished_at else None,
            "total_duration_s": total_s,
            "steps": {
                name: {"status": info.get("status"), "duration_s": info.get("duration_s")}
                for name, info in steps.items()
            },
            "error_summary": last_run_row.error_summary,
        }

    nrt = next_run_time()
    next_run_iso = nrt.isoformat() if nrt else None

    # ── 2. Freshness mini-summary ────────────────────────────────────────
    data_date = db.execute(
        text("""
            SELECT MAX(occureddate) AS d
            FROM ol_incidents
            WHERE CAST(NULLIF(year,'') AS INTEGER) > 2000
              AND LENGTH(occureddate) = 10
        """)
    ).scalar()

    latest_pred_q = db.execute(
        select(PredictionsCache.target_quarter)
        .order_by(PredictionsCache.trained_at.desc())
        .limit(1)
    ).scalar()

    # ── 3. Per-site stats (one query) ────────────────────────────────────
    site_rows = db.execute(text("""
        WITH site_stats AS (
          SELECT
            siname AS site,
            MAX(buname) AS business_unit,
            COUNT(*) AS incidents,
            COUNT(DISTINCT (year, month)) AS n_months,
            MIN(occureddate) AS first_incident,
            MAX(occureddate) AS last_incident
          FROM ol_incidents
          WHERE CAST(NULLIF(year,'') AS INTEGER) >= 2020
            AND siname IS NOT NULL
          GROUP BY siname
        ),
        champ AS (
          SELECT DISTINCT ON (site)
            site, model_name AS champion_model,
            holdout_rmse, holdout_mape, training_rows, trained_at
          FROM model_runs
          WHERE is_champion = true
          ORDER BY site, trained_at DESC
        ),
        bt AS (
          SELECT
            site,
            COUNT(*) AS backtest_n,
            AVG(abs_pct_error) AS mean_ape,
            SUM(CASE WHEN abs_pct_error <= 20 THEN 1.0 ELSE 0.0 END)
              / NULLIF(COUNT(*), 0) * 100 AS pct_within_20
          FROM backtest_results
          WHERE abs_pct_error IS NOT NULL
          GROUP BY site
        ),
        preds AS (
          SELECT DISTINCT ON (site)
            site, training_data_through, confidence_band
          FROM predictions_cache
          ORDER BY site, trained_at DESC
        )
        SELECT
          s.site,
          s.business_unit,
          s.incidents,
          s.n_months,
          s.first_incident,
          s.last_incident,
          c.champion_model,
          c.holdout_rmse,
          c.holdout_mape,
          c.training_rows,
          c.trained_at,
          bt.backtest_n,
          bt.mean_ape,
          bt.pct_within_20,
          preds.training_data_through,
          preds.confidence_band
        FROM site_stats s
        LEFT JOIN champ c   ON c.site = s.site
        LEFT JOIN bt        ON bt.site = s.site
        LEFT JOIN preds     ON preds.site = s.site
        ORDER BY s.incidents DESC;
    """)).all()

    sites = []
    healthy = sparse = insufficient = low_acc = 0
    for r in site_rows:
        pct = float(r.pct_within_20) if r.pct_within_20 is not None else None
        status = _derive_status(r.incidents, r.n_months, r.champion_model, pct)
        if status == "Healthy":
            healthy += 1
        elif status == "Sparse - BU fallback":
            sparse += 1
        elif status == "Insufficient data":
            insufficient += 1
        elif status == "Low accuracy":
            low_acc += 1

        sites.append({
            "site": r.site,
            "business_unit": r.business_unit,
            "incidents": int(r.incidents),
            "n_months": int(r.n_months),
            "first_incident": r.first_incident,
            "last_incident": r.last_incident,
            "champion_model": r.champion_model,
            "holdout_rmse": round(float(r.holdout_rmse), 2) if r.holdout_rmse is not None else None,
            "holdout_mape": round(float(r.holdout_mape), 1) if r.holdout_mape is not None else None,
            "training_rows": int(r.training_rows) if r.training_rows is not None else None,
            "last_trained_at": r.trained_at.isoformat() if r.trained_at else None,
            "backtest_n_months": int(r.backtest_n) if r.backtest_n is not None else 0,
            "backtest_mean_ape": round(float(r.mean_ape), 1) if r.mean_ape is not None else None,
            "backtest_pct_within_20": round(pct, 1) if pct is not None else None,
            "training_data_through": r.training_data_through,
            "confidence_band": r.confidence_band,
            "status": status,
        })

    # ── 4. Alerts: site name variants ────────────────────────────────────
    site_variant_rows = db.execute(text("""
        SELECT
          UPPER(TRIM(siname)) AS canonical,
          COUNT(DISTINCT siname) AS variant_count,
          STRING_AGG(DISTINCT siname, ' | ' ORDER BY siname) AS variants
        FROM ol_incidents
        WHERE siname IS NOT NULL
        GROUP BY UPPER(TRIM(siname))
        HAVING COUNT(DISTINCT siname) > 1
        ORDER BY variant_count DESC;
    """)).all()
    site_variants = [
        {"canonical": r.canonical, "variant_count": int(r.variant_count), "variants": r.variants}
        for r in site_variant_rows
    ]

    # ── 5. Alerts: category variants (whitespace+case normalised) ────────
    cat_variant_rows = db.execute(text("""
        SELECT
          REGEXP_REPLACE(UPPER(TRIM(incidentcatname)), '\\s+', '', 'g') AS canonical,
          COUNT(DISTINCT incidentcatname) AS variant_count,
          STRING_AGG(DISTINCT incidentcatname, ' | ' ORDER BY incidentcatname) AS variants
        FROM ol_incidents
        WHERE incidentcatname IS NOT NULL
        GROUP BY REGEXP_REPLACE(UPPER(TRIM(incidentcatname)), '\\s+', '', 'g')
        HAVING COUNT(DISTINCT incidentcatname) > 1
        ORDER BY variant_count DESC;
    """)).all()
    category_variants = [
        {"canonical": r.canonical, "variant_count": int(r.variant_count), "variants": r.variants}
        for r in cat_variant_rows
    ]

    # ── 6. Alerts: null/invalid data counts ──────────────────────────────
    issues_row = db.execute(text(f"""
        SELECT
          COUNT(*) FILTER (WHERE year IS NULL OR year = '')        AS null_year,
          COUNT(*) FILTER (WHERE month IS NULL)                     AS null_month,
          COUNT(*) FILTER (WHERE quarter IS NULL OR quarter = '')   AS null_quarter,
          COUNT(*) FILTER (WHERE levelname IS NULL OR levelname = '') AS null_severity,
          COUNT(*) FILTER (WHERE levelname NOT IN ('Low','Medium','High')) AS invalid_severity,
          COUNT(*) FILTER (WHERE CAST(NULLIF(year,'') AS INTEGER) < 2000)  AS pre_2000_year,
          COUNT(*) AS total_rows
        FROM ol_incidents;
    """)).first()

    data_issues = {
        "total_rows": int(issues_row.total_rows),
        "null_year": int(issues_row.null_year),
        "null_month": int(issues_row.null_month),
        "null_quarter": int(issues_row.null_quarter),
        "null_severity": int(issues_row.null_severity),
        "invalid_severity": int(issues_row.invalid_severity),
        "pre_2000_year": int(issues_row.pre_2000_year),
    }

    return {
        "pipeline": {
            "last_run": last_run,
            "next_run_at": next_run_iso,
        },
        "freshness": {
            "latest_data_date": data_date,
            "latest_predicted_quarter": latest_pred_q,
        },
        "summary": {
            "total_sites": len(sites),
            "healthy": healthy,
            "sparse_bu_fallback": sparse,
            "insufficient_data": insufficient,
            "low_accuracy": low_acc,
        },
        "sites": sites,
        "alerts": {
            "site_variants": site_variants,
            "category_variants": category_variants,
            "data_issues": data_issues,
        },
    }
