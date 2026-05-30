"""
AI Insights service — deterministic, rule-based narrative builder.

Public API
----------
generate_site_insight(site, quarter, db) -> dict
    Returns
    {
        signals: {...},                  # structured signal block (also returned)
        executive_brief: str,            # ~1 paragraph
        operational_observation: str,    # ~1 paragraph
        risk_advisory: str,              # ~1 paragraph
        generated_at: ISO8601,
        source: "rule-based",
    }

How it works
------------
1. Pulls structured signals from existing tables (no raw rows):
   risk_scores, risk_drivers, predictions_cache, backtest_results,
   recommendations, plus a lightweight coverage count from ol_incidents.

2. Assembles the three narrative sections via Python string templates +
   threshold bands.  No external LLM is called.  All wording is grounded
   in the signal block.

3. A 5-minute in-process TTL cache keyed by (site, quarter) avoids
   recomputing on dashboard re-renders.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.lib import quarters as Q
from app.models.backtest import BacktestResult
from app.models.drivers import RiskDriver
from app.models.pipeline import RiskScore
from app.models.predictions import ModelRun, PredictionsCache
from app.services.recommendations import generate_recommendations


# ---------------------------------------------------------------------------
# In-process TTL cache (per process; reset on restart)
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 300
_cache: dict[tuple[str, str], tuple[dict, float]] = {}


# ---------------------------------------------------------------------------
# Wording helpers — consistent threshold bands so output is reproducible
# ---------------------------------------------------------------------------

def _qoq_word(delta_pct: Optional[float]) -> str:
    """Human-readable band for a QoQ percentage change."""
    if delta_pct is None:
        return "no prior-quarter comparison"
    if delta_pct > 50:
        return f"sharp rise (+{delta_pct:.0f}% QoQ)"
    if delta_pct > 20:
        return f"rising (+{delta_pct:.0f}% QoQ)"
    if delta_pct > 5:
        return f"modestly rising (+{delta_pct:.0f}% QoQ)"
    if delta_pct < -50:
        return f"sharp decline ({delta_pct:.0f}% QoQ)"
    if delta_pct < -20:
        return f"declining ({delta_pct:.0f}% QoQ)"
    if delta_pct < -5:
        return f"modestly declining ({delta_pct:.0f}% QoQ)"
    return "broadly flat QoQ"


def _score_delta_word(curr: float, prev: Optional[float]) -> str:
    """Human-readable band for a composite-score change in points."""
    if prev is None:
        return "no prior-quarter score for comparison"
    delta = round(curr - prev, 1)
    if delta > 10:
        return f"sharply up ({delta:+.1f} points from {prev:.1f})"
    if delta > 2:
        return f"modestly up ({delta:+.1f} points from {prev:.1f})"
    if delta < -10:
        return f"sharply down ({delta:+.1f} points from {prev:.1f})"
    if delta < -2:
        return f"down ({delta:+.1f} points from {prev:.1f})"
    return f"broadly flat ({delta:+.1f} points vs {prev:.1f})"


def _confidence_word(band: Optional[str]) -> str:
    if not band:
        return "unspecified confidence"
    return {
        "high":   "high confidence",
        "medium": "moderate confidence",
        "low":    "low confidence",
    }.get(band.lower(), f"{band} confidence")


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def _extract_signals(site: str, quarter: str, db: Session) -> dict[str, Any]:
    """
    Pull every signal we need into one dict.

    Case-insensitive site comparison everywhere (risk_scores stores upper-case
    site names; other tables store raw SINAME — most are already upper-case
    after the CSV cleanup, but we don't rely on it).
    """
    site_upper = site.upper().strip()
    try:
        prev_q = Q.previous_label(quarter)
    except Exception:
        prev_q = None

    # ── risk_scores ────────────────────────────────────────────────────
    rs_row = db.execute(
        select(RiskScore)
        .where(func.upper(RiskScore.site) == site_upper, RiskScore.quarter == quarter)
        .limit(1)
    ).scalar_one_or_none()
    composite = float(rs_row.risk_score) if rs_row and rs_row.risk_score is not None else None
    band = rs_row.risk_level if rs_row else None

    prev_score = None
    if prev_q:
        prev_score = db.execute(
            select(RiskScore.risk_score)
            .where(func.upper(RiskScore.site) == site_upper, RiskScore.quarter == prev_q)
            .limit(1)
        ).scalar_one_or_none()
        prev_score = float(prev_score) if prev_score is not None else None

    qoq_delta_points = (
        round(composite - prev_score, 2)
        if (composite is not None and prev_score is not None) else None
    )

    # Portfolio rank within the requested quarter
    rank_rows = db.execute(
        select(RiskScore.site, RiskScore.risk_score)
        .where(RiskScore.quarter == quarter, RiskScore.risk_score.isnot(None))
        .order_by(RiskScore.risk_score.desc())
    ).all()
    total_sites = len(rank_rows)
    rank = None
    for idx, r in enumerate(rank_rows, start=1):
        if (r.site or "").upper().strip() == site_upper:
            rank = idx
            break

    # ── risk_drivers (latest computed batch for this site) ─────────────
    latest_drv_at = db.execute(
        select(func.max(RiskDriver.computed_at))
        .where(func.upper(RiskDriver.site) == site_upper)
    ).scalar()

    drv_rows = []
    if latest_drv_at is not None:
        drv_rows = db.execute(
            select(RiskDriver)
            .where(
                func.upper(RiskDriver.site) == site_upper,
                RiskDriver.computed_at == latest_drv_at,
            )
            .order_by(RiskDriver.impact_score.desc())
        ).scalars().all()

    drivers_payload = [{
        "driver_name": d.driver_name,
        "impact_score": round(float(d.impact_score), 1) if d.impact_score is not None else 0.0,
        "trend": d.trend,
        "pct_change_vs_last_qtr": (
            round(float(d.pct_change_vs_last_qtr), 1)
            if d.pct_change_vs_last_qtr is not None else None
        ),
    } for d in drv_rows]

    top_driver    = drivers_payload[0] if drivers_payload else None
    second_driver = drivers_payload[1] if len(drivers_payload) > 1 else None
    rising_count  = sum(1 for d in drivers_payload if d["trend"] == "up")
    # "Spike off small base": large positive QoQ but low impact rank
    small_base_spikes = [
        d for d in drivers_payload
        if (d.get("pct_change_vs_last_qtr") or 0) > 50 and d["impact_score"] < 30
    ]

    # ── predictions_cache (nearest future forecast) ────────────────────
    # forecaster.py emits a placeholder row with model_name='none' when no
    # model could be trained (insufficient history).  Treat that as ABSENT
    # rather than as a real "predict 0" forecast — otherwise the narrative
    # reads as if zero incidents were forecast, and the advisory sets a
    # nonsensical "≤0" target.
    pred_row = db.execute(
        select(PredictionsCache)
        .where(func.upper(PredictionsCache.site) == site_upper)
        .order_by(PredictionsCache.target_quarter.asc())
        .limit(1)
    ).scalar_one_or_none()
    forecast_payload = None
    if pred_row and (pred_row.model_name or "").strip().lower() not in ("", "none"):
        forecast_payload = {
            "target_quarter": pred_row.target_quarter,
            "predicted_count": (
                round(float(pred_row.predicted_count), 1)
                if pred_row.predicted_count is not None else None
            ),
            "lower_ci": round(float(pred_row.lower_ci), 1) if pred_row.lower_ci is not None else None,
            "upper_ci": round(float(pred_row.upper_ci), 1) if pred_row.upper_ci is not None else None,
            "confidence_band": pred_row.confidence_band,
            "model_name": pred_row.model_name,
        }

    # ── backtest_results (aggregate accuracy) ──────────────────────────
    bt_rows = db.execute(
        select(BacktestResult.abs_pct_error)
        .where(func.upper(BacktestResult.site) == site_upper)
    ).all()
    valid_apes = [r[0] for r in bt_rows if r[0] is not None]
    accuracy_pct = None
    mape = None
    if valid_apes:
        accuracy_pct = round(sum(1 for a in valid_apes if a <= 20) / len(valid_apes) * 100, 1)
        mape = round(sum(valid_apes) / len(valid_apes), 1)

    # ── champion model + training rows ─────────────────────────────────
    champ_row = db.execute(
        select(ModelRun.model_name, ModelRun.training_rows, ModelRun.trained_at)
        .where(func.upper(ModelRun.site) == site_upper, ModelRun.is_champion == True)  # noqa: E712
        .order_by(ModelRun.trained_at.desc())
        .limit(1)
    ).first()
    champion_model = champ_row.model_name if champ_row else None
    training_rows = int(champ_row.training_rows) if champ_row and champ_row.training_rows else None

    # ── coverage (incidents + distinct months) ─────────────────────────
    cov = db.execute(text("""
        SELECT COUNT(*) AS inc, COUNT(DISTINCT (year, month)) AS months
        FROM ol_incidents
        WHERE UPPER(siname) = :s AND CAST(NULLIF(year,'') AS INTEGER) >= 2020
    """), {"s": site_upper}).first()
    incidents = int(cov.inc) if cov else 0
    months    = int(cov.months) if cov else 0

    # ── recommendations (high-priority open count, latest batch) ───────
    rec_rows = db.execute(text("""
        SELECT priority FROM recommendations
        WHERE UPPER(site) = :s AND status = 'open'
          AND created_at = (
              SELECT MAX(created_at) FROM recommendations
              WHERE UPPER(site) = :s
          )
    """), {"s": site_upper}).all()
    high_open = sum(1 for r in rec_rows if (r.priority or "").lower() == "high")
    total_open = len(rec_rows)

    return {
        "site": site,
        "quarter": quarter,
        "previous_quarter": prev_q,
        "risk_scores": {
            "composite": composite,
            "band": band,
            "previous_composite": prev_score,
            "qoq_delta_points": qoq_delta_points,
            "rank": rank,
            "total_sites": total_sites,
        },
        "drivers": {
            "top": top_driver,
            "second": second_driver,
            "rising_count": rising_count,
            "small_base_spikes": small_base_spikes,
            "n_drivers": len(drivers_payload),
        },
        "forecast": forecast_payload,
        "backtest": {
            "accuracy_within_20_pct": accuracy_pct,
            "mape": mape,
            "n_evaluated": len(valid_apes),
            "champion_model": champion_model,
            "training_rows": training_rows,
        },
        "coverage": {
            "incidents_since_2020": incidents,
            "distinct_months": months,
        },
        "recommendations": {
            "high_priority_open": high_open,
            "total_open": total_open,
        },
    }


# ---------------------------------------------------------------------------
# Narrative section builders (deterministic — strings + threshold bands)
# ---------------------------------------------------------------------------

def _executive_brief(sig: dict) -> str:
    rs   = sig["risk_scores"]
    drv  = sig["drivers"]
    fc   = sig.get("forecast")
    site = sig["site"]
    q    = sig["quarter"]

    if rs["composite"] is None:
        return (
            f"No composite risk score available for {site} in {q}. "
            f"This is usually a newly-onboarded site or one that did not have a complete "
            f"quarter of data when the pipeline last ran."
        )

    delta_word = _score_delta_word(rs["composite"], rs["previous_composite"])

    rank_str = (
        f" It ranks {rs['rank']} of {rs['total_sites']} sites by risk this quarter."
        if rs["rank"] is not None else ""
    )

    top_str = ""
    if drv["top"]:
        td = drv["top"]
        top_str = (
            f" The top driver is {td['driver_name']} "
            f"(impact {td['impact_score']:.0f}/100, "
            f"{_qoq_word(td.get('pct_change_vs_last_qtr'))})."
        )

    second_str = ""
    if drv["second"]:
        sd = drv["second"]
        second_str = (
            f" Secondary driver: {sd['driver_name']} "
            f"(impact {sd['impact_score']:.0f}/100)."
        )

    if fc and fc.get("predicted_count") is not None:
        forecast_str = (
            f" Next-quarter forecast: ~{int(round(fc['predicted_count']))} incidents "
            f"in {fc['target_quarter']} ({_confidence_word(fc.get('confidence_band'))})."
        )
    else:
        # No champion model / no usable forecast row.
        forecast_str = (
            " Next-quarter forecast: not available — insufficient history for a "
            "champion model."
        )

    return (
        f"{site} ended {q} at a {rs['band'] or 'unbanded'} composite risk score of "
        f"{rs['composite']:.1f}/100, {delta_word}.{rank_str}{top_str}{second_str}{forecast_str}"
    ).strip()


def _operational_observation(sig: dict) -> str:
    drv = sig["drivers"]
    bt  = sig["backtest"]
    cov = sig["coverage"]

    # Concentration check
    if not drv["top"]:
        # No drivers attributed for this site yet (e.g. very new or very sparse).
        # Return early with a clean absence message so we don't fabricate
        # "leading driver" wording when none exists.
        reliability_only = ""
        if bt["champion_model"] is None:
            reliability_only = (
                f" No champion forecasting model has been trained for this site yet "
                f"({cov['incidents_since_2020']} incidents / "
                f"{cov['distinct_months']} months of data)."
            )
        return (
            f"Driver attribution is not yet available for this site.{reliability_only}"
        ).strip()
    else:
        top_imp = drv["top"]["impact_score"]
        sec_imp = drv["second"]["impact_score"] if drv["second"] else 0.0
        ratio = (sec_imp / top_imp) if top_imp > 0 else 0
        if top_imp >= 70 and ratio < 0.5:
            concentration = (
                f"risk is highly concentrated in '{drv['top']['driver_name']}' "
                f"(impact {top_imp:.0f}/100); the next-strongest driver is well behind"
            )
        elif drv["n_drivers"] >= 3 and ratio >= 0.5:
            concentration = (
                f"risk is spread across multiple drivers — '{drv['top']['driver_name']}' "
                f"leads but '{drv['second']['driver_name']}' is close behind at "
                f"{sec_imp:.0f}/100"
            )
        else:
            concentration = (
                f"'{drv['top']['driver_name']}' is the leading driver "
                f"({top_imp:.0f}/100), with {drv['rising_count']} rising driver(s) overall"
            )

    # Reliability sentence
    if bt["champion_model"]:
        acc_str = (
            f"{bt['accuracy_within_20_pct']:.0f}%"
            if bt["accuracy_within_20_pct"] is not None else "n/a"
        )
        mape_str = f", MAPE {bt['mape']:.0f}%" if bt["mape"] is not None else ""
        reliability = (
            f" The {bt['champion_model']} model — trained on "
            f"{cov['incidents_since_2020']} incidents across {cov['distinct_months']} months — "
            f"hit {acc_str} of holdout quarters within ±20% on backtest{mape_str}."
        )
    else:
        reliability = (
            f" No champion forecasting model has been trained for this site yet "
            f"({cov['incidents_since_2020']} incidents / {cov['distinct_months']} months of data)."
        )

    # Spike off small base
    spike_str = ""
    if drv["small_base_spikes"]:
        s = drv["small_base_spikes"][0]
        spike_str = (
            f" Watch: '{s['driver_name']}' is up "
            f"{s['pct_change_vs_last_qtr']:.0f}% QoQ from a small base — "
            f"monitor for sustained increase before escalating."
        )

    return f"Operationally, {concentration}.{reliability}{spike_str}".strip()


def _risk_advisory(sig: dict) -> str:
    drv = sig["drivers"]
    fc  = sig.get("forecast")
    rs  = sig["risk_scores"]

    if not drv["top"]:
        return (
            "No risk drivers identified — insufficient data to recommend a specific action. "
            "Once a full quarter of incidents is available, the engine will produce a "
            "targeted advisory."
        )

    # Reuse the same category->action mapping the recommendations engine uses.
    # Pass top drivers + a synthesised site_data dict in the shape rules expect.
    drivers_for_rules = []
    if drv["top"]:    drivers_for_rules.append(drv["top"])
    if drv["second"]: drivers_for_rules.append(drv["second"])

    site_data = {
        "site": sig["site"],
        "quarter": sig["quarter"],
        "total_incidents_qtr": None,
        # Use the top driver's QoQ as the site's QoQ delta (best proxy here)
        "delta_qtr_pct": drv["top"].get("pct_change_vs_last_qtr"),
        "reporting_lag_p90": None,
        "business_unit": None,
    }
    recs = generate_recommendations(drivers_for_rules, site_data)

    # Prefer a specific rule over the generic root-cause fallback
    chosen = None
    for r in recs:
        if not r.action_text.lower().startswith("investigate recurring"):
            chosen = r
            break
    if chosen is None and recs:
        chosen = recs[0]

    if chosen is None:
        action_part = (
            f"Schedule a structured review of '{drv['top']['driver_name']}' with the site "
            f"EHS team and document agreed corrective actions."
        )
    else:
        action_part = (
            f"Recommended action ({chosen.priority} priority"
            f"{', owner: ' + chosen.suggested_owner if chosen.suggested_owner else ''}): "
            f"{chosen.action_text}"
        )

    # Measurable QoQ target tied to the forecast (or to the composite if no forecast)
    target_part = ""
    if fc and fc.get("predicted_count") is not None:
        pred = int(round(fc["predicted_count"]))
        target_part = (
            f" Measurable target for {fc['target_quarter']}: hold incidents at or below "
            f"the forecast of {pred}, with an intermediate review at month 2."
        )
    elif (
        rs["composite"] is not None
        and rs["qoq_delta_points"] is not None
        and rs["qoq_delta_points"] > 5
    ):
        target_part = (
            f" Measurable target: bring the composite risk score below "
            f"{rs['composite']:.0f} next quarter."
        )

    # Always close the action sentence with a period (so it reads cleanly whether
    # or not a measurable target follows it).
    if not action_part.rstrip().endswith((".", "!", "?")):
        action_part = action_part.rstrip() + "."
    return f"{action_part}{target_part}".strip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_site_insight(site: str, quarter: str, db: Session) -> dict[str, Any]:
    """
    Build a deterministic, rule-based insight for one (site, quarter).
    Cached for ``_CACHE_TTL_SECONDS`` per (site, quarter) within the same process.
    """
    key = (site, quarter)
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[1] > now:
        return cached[0]

    signals = _extract_signals(site, quarter, db)
    payload = {
        "signals": signals,
        "executive_brief":         _executive_brief(signals),
        "operational_observation": _operational_observation(signals),
        "risk_advisory":           _risk_advisory(signals),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "rule-based",
    }
    _cache[key] = (payload, now + _CACHE_TTL_SECONDS)
    return payload
