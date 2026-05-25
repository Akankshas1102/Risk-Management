"""
Read-only analytics API.  All endpoints query OL_INCIDENTS in the vedanta
SQL Server database.  Heavy aggregation results are cached for 5 minutes.
"""

import calendar
import time
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, and_, case, cast, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.ssms import get_ssms_db
from app.models.ol_incidents import OLIncident
from app.schemas.analytics import (
    HeatmapPoint,
    IncidentCategoryCount,
    IncidentSiteCount,
    IncidentTypeCount,
    KPIResponse,
    SiteItem,
    TrendPoint,
)

router = APIRouter(prefix="/api", tags=["analytics"])

# ---------------------------------------------------------------------------
# Simple TTL cache (5 min, module-level, thread-safe enough for this load)
# ---------------------------------------------------------------------------

_CACHE_TTL = 300
_cache: dict[str, tuple[Any, float]] = {}


def _cache_get(key: str) -> tuple[bool, Any]:
    if key in _cache:
        val, exp = _cache[key]
        if time.monotonic() < exp:
            return True, val
        del _cache[key]
    return False, None


def _cache_set(key: str, val: Any) -> None:
    _cache[key] = (val, time.monotonic() + _CACHE_TTL)


# ---------------------------------------------------------------------------
# Quarter utilities (fiscal year: Q4=Jan-Mar, Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec)
# ---------------------------------------------------------------------------

_FISCAL_ORDER = ["Q4", "Q1", "Q2", "Q3"]
_MONTH_ABBR = {i: calendar.month_abbr[i] for i in range(1, 13)}


def _qsort_key(qs: str) -> int:
    """Comparable integer for fiscal-quarter strings: '2024-Q4'→20240, '2024-Q1'→20241."""
    year, q = qs.split("-")
    return int(year) * 10 + _FISCAL_ORDER.index(q)


def _current_q() -> str:
    today = date.today()
    m = today.month
    q = (m - 4) // 3 + 1 if m >= 4 else 4
    return f"{today.year}-Q{q}"


def _prev_q(year: int, q: str) -> tuple[int, str]:
    idx = _FISCAL_ORDER.index(q)
    return (year - 1, "Q3") if idx == 0 else (year, _FISCAL_ORDER[idx - 1])


def _latest_complete_q(db: Session) -> str:
    """Largest quarter in OL_INCIDENTS that is not the current (incomplete) quarter."""
    hit, cached = _cache_get("latest_q")
    if hit:
        return cached

    rows = db.execute(
        select(OLIncident.YEAR, OLIncident.QUARTER)
        .where(OLIncident.YEAR >= "2020")
        .distinct()
    ).all()
    qs = sorted(
        {f"{y}-{q}" for y, q in rows if y and q},
        key=_qsort_key,
    )
    cur = _current_q()
    complete = [q for q in qs if q != cur]
    result = complete[-1] if complete else (qs[-1] if qs else cur)
    _cache_set("latest_q", result)
    return result


def _resolve_quarter(quarter: Optional[str], db: Session) -> tuple[str, str]:
    """Return (year_str, quarter_str) from a 'YYYY-Qn' string (or the latest complete)."""
    q_str = quarter or _latest_complete_q(db)
    year_s, q_s = q_str.split("-")
    return year_s, q_s


def _base_filter(year_s: str, q_s: str, business_unit: Optional[str] = None):
    """Common WHERE clause: valid year + specific quarter + optional BU filter."""
    conds = [OLIncident.YEAR >= "2020", OLIncident.YEAR == year_s, OLIncident.QUARTER == q_s]
    if business_unit:
        conds.append(OLIncident.BUNAME == business_unit)
    return conds


def _minmax_norm(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _risk_band(score: float) -> str:
    if score <= 0.40:
        return "Low"
    if score <= 0.65:
        return "Medium"
    if score <= 0.85:
        return "High"
    return "Critical"


# ---------------------------------------------------------------------------
# 1. GET /api/sites
# ---------------------------------------------------------------------------

@router.get("/sites", response_model=list[SiteItem])
def list_sites(
    quarter: Optional[str] = Query(None, description="YYYY-Qn, defaults to latest complete"),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    """All sites with their BU and incident count for the given (or latest complete) quarter."""
    year_s, q_s = _resolve_quarter(quarter, db)
    cache_key = f"sites:{year_s}:{q_s}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    stmt = (
        select(OLIncident.SINAME, OLIncident.BUNAME, func.count().label("incident_count"))
        .where(*_base_filter(year_s, q_s, business_unit))
        .group_by(OLIncident.SINAME, OLIncident.BUNAME)
        .order_by(func.count().desc())
    )
    rows = db.execute(stmt).all()
    result = [
        SiteItem(site=r.SINAME or "Unknown", business_unit=r.BUNAME, incident_count=r.incident_count)
        for r in rows
    ]
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 2. GET /api/kpis
# ---------------------------------------------------------------------------

@router.get("/kpis", response_model=KPIResponse)
def get_kpis(
    site: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None, description="YYYY-Qn, defaults to latest complete"),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    """
    Key performance indicators for a site (or all sites) in a quarter.
    risk_score and predicted_next_qtr are null until those tables are populated.
    """
    year_s, q_s = _resolve_quarter(quarter, db)
    cache_key = f"kpis:{site}:{year_s}:{q_s}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    base = [OLIncident.YEAR >= "2020", OLIncident.YEAR == year_s, OLIncident.QUARTER == q_s]
    if site:
        base.append(OLIncident.SINAME == site)
    if business_unit:
        base.append(OLIncident.BUNAME == business_unit)

    # Total incidents this quarter
    total: int = db.execute(select(func.count()).select_from(OLIncident).where(*base)).scalar() or 0

    # Previous quarter count
    prev_year, prev_q = _prev_q(int(year_s), q_s)
    prev_base = [
        OLIncident.YEAR >= "2020",
        OLIncident.YEAR == str(prev_year),
        OLIncident.QUARTER == prev_q,
    ]
    if site:
        prev_base.append(OLIncident.SINAME == site)
    if business_unit:
        prev_base.append(OLIncident.BUNAME == business_unit)
    prev_total: int = (
        db.execute(select(func.count()).select_from(OLIncident).where(*prev_base)).scalar() or 0
    )
    delta = round((total - prev_total) / prev_total * 100, 1) if prev_total else None

    # Top incident category
    top_row = db.execute(
        select(OLIncident.INCIDENTCATNAME, func.count().label("n"))
        .where(*base)
        .group_by(OLIncident.INCIDENTCATNAME)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    top_cat = top_row.INCIDENTCATNAME if top_row else None
    top_share = round(top_row.n / total, 3) if (top_row and total) else None

    # Risk score from risk_scores table
    risk_score: Optional[float] = None
    try:
        rs = db.execute(
            text("SELECT risk_score FROM risk_scores WHERE site = :s AND quarter = :q"),
            {"s": site or "", "q": f"{year_s}-{q_s}"},
        ).scalar()
        risk_score = float(rs) if rs is not None else None
    except Exception:
        pass

    # Next-quarter prediction from predictions_cache (nearest future quarter)
    predicted_next_qtr: Optional[int] = None
    try:
        pred = db.execute(
            text(
                "SELECT predicted_count FROM predictions_cache "
                "WHERE site = :s "
                "ORDER BY trained_at DESC LIMIT 1"
            ),
            {"s": site or ""},
        ).scalar()
        predicted_next_qtr = int(round(pred)) if pred is not None else None
    except Exception:
        pass

    result = KPIResponse(
        quarter=f"{year_s}-{q_s}",
        site=site,
        total_incidents_qtr=total,
        delta_vs_last_qtr_pct=delta,
        top_category=top_cat,
        top_category_share=top_share,
        predicted_next_qtr=predicted_next_qtr,
        risk_score=risk_score,
        confidence_score=None,
    )
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 3. GET /api/incidents/by-type
# ---------------------------------------------------------------------------

@router.get("/incidents/by-type", response_model=list[IncidentTypeCount])
def incidents_by_type(
    site: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    year_s, q_s = _resolve_quarter(quarter, db)
    cache_key = f"by_type:{site}:{year_s}:{q_s}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    conds = _base_filter(year_s, q_s, business_unit)
    if site:
        conds.append(OLIncident.SINAME == site)

    rows = db.execute(
        select(OLIncident.INCIDENTTYPENAME, func.count().label("n"))
        .where(*conds)
        .group_by(OLIncident.INCIDENTTYPENAME)
        .order_by(func.count().desc())
    ).all()
    result = [IncidentTypeCount(incident_type=r.INCIDENTTYPENAME or "Unknown", count=r.n) for r in rows]
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 4. GET /api/incidents/by-category  (top 15 + "Other")
# ---------------------------------------------------------------------------

@router.get("/incidents/by-category", response_model=list[IncidentCategoryCount])
def incidents_by_category(
    site: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    year_s, q_s = _resolve_quarter(quarter, db)
    cache_key = f"by_cat:{site}:{year_s}:{q_s}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    conds = _base_filter(year_s, q_s, business_unit)
    if site:
        conds.append(OLIncident.SINAME == site)

    rows = db.execute(
        select(OLIncident.INCIDENTCATNAME, func.count().label("n"))
        .where(*conds)
        .group_by(OLIncident.INCIDENTCATNAME)
        .order_by(func.count().desc())
    ).all()

    top = rows[:15]
    other_n = sum(r.n for r in rows[15:])
    result = [IncidentCategoryCount(category=r.INCIDENTCATNAME or "Unknown", count=r.n) for r in top]
    if other_n:
        result.append(IncidentCategoryCount(category="Other", count=other_n))
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 5. GET /api/incidents/by-site
# ---------------------------------------------------------------------------

@router.get("/incidents/by-site", response_model=list[IncidentSiteCount])
def incidents_by_site(
    quarter: Optional[str] = Query(None),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    year_s, q_s = _resolve_quarter(quarter, db)
    cache_key = f"by_site:{year_s}:{q_s}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    rows = db.execute(
        select(OLIncident.SINAME, OLIncident.BUNAME, func.count().label("n"))
        .where(*_base_filter(year_s, q_s, business_unit))
        .group_by(OLIncident.SINAME, OLIncident.BUNAME)
        .order_by(func.count().desc())
    ).all()
    result = [
        IncidentSiteCount(site=r.SINAME or "Unknown", business_unit=r.BUNAME, count=r.n)
        for r in rows
    ]
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 6. GET /api/incidents/trend
# ---------------------------------------------------------------------------

@router.get("/incidents/trend", response_model=list[TrendPoint])
def incidents_trend(
    site: Optional[str] = Query(None),
    months: int = Query(12, ge=1, le=60),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    """Monthly time series for a site (or all sites) with the all-sites average."""
    cache_key = f"trend:{site}:{months}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    today = date.today()
    total_months_elapsed = today.year * 12 + today.month - 1 - months
    start_year = total_months_elapsed // 12
    start_month = (total_months_elapsed % 12) + 1

    year_int = cast(OLIncident.YEAR, Integer)
    date_filter = and_(
        OLIncident.YEAR >= "2020",
        or_(
            year_int > start_year,
            and_(year_int == start_year, OLIncident.MONTH >= start_month),
        ),
    )

    # Site-specific counts per (year, month)
    site_conds = [date_filter]
    if site:
        site_conds.append(OLIncident.SINAME == site)
    if business_unit:
        site_conds.append(OLIncident.BUNAME == business_unit)

    site_rows = db.execute(
        select(OLIncident.YEAR, OLIncident.MONTH, func.count().label("cnt"))
        .where(*site_conds)
        .group_by(OLIncident.YEAR, OLIncident.MONTH)
        .order_by(OLIncident.YEAR, OLIncident.MONTH)
    ).all()
    site_counts = {(r.YEAR, r.MONTH): r.cnt for r in site_rows}

    # All-sites average per (year, month) — subquery over per-site monthly counts
    bu_filter = [date_filter]
    if business_unit:
        bu_filter.append(OLIncident.BUNAME == business_unit)

    sub = (
        select(
            OLIncident.YEAR,
            OLIncident.MONTH,
            OLIncident.SINAME,
            func.count().label("cnt"),
        )
        .where(*bu_filter)
        .group_by(OLIncident.YEAR, OLIncident.MONTH, OLIncident.SINAME)
        .subquery()
    )
    avg_rows = db.execute(
        select(sub.c.YEAR, sub.c.MONTH, func.avg(cast(sub.c.cnt, Integer)).label("avg_cnt"))
        .group_by(sub.c.YEAR, sub.c.MONTH)
        .order_by(sub.c.YEAR, sub.c.MONTH)
    ).all()
    avg_counts = {(r.YEAR, r.MONTH): float(r.avg_cnt) for r in avg_rows}

    # Build result covering every month that has any data
    all_keys = sorted(set(site_counts) | set(avg_counts))
    result = []
    for year_s, month in all_keys:
        result.append(
            TrendPoint(
                year=int(year_s),
                month=month,
                month_label=f"{_MONTH_ABBR[month]} {year_s}",
                count=site_counts.get((year_s, month), 0),
                all_sites_avg=round(avg_counts.get((year_s, month), 0.0), 2),
            )
        )

    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# 7. GET /api/incidents/heatmap
# ---------------------------------------------------------------------------

@router.get("/incidents/heatmap", response_model=list[HeatmapPoint])
def incidents_heatmap(
    quarter: Optional[str] = Query(None),
    business_unit: Optional[str] = Query(None),
    db: Session = Depends(get_ssms_db),
):
    """
    Per-site likelihood (normalised frequency) and impact (normalised severity)
    for use in the Risk Heatmap chart.
    """
    year_s, q_s = _resolve_quarter(quarter, db)
    cache_key = f"heatmap:{year_s}:{q_s}:{business_unit}"
    hit, val = _cache_get(cache_key)
    if hit:
        return val

    severity_score = func.sum(
        case(
            (OLIncident.LEVELNAME == "High", 3),
            (OLIncident.LEVELNAME == "Medium", 2),
            else_=1,
        )
    ).label("severity_score")

    rows = db.execute(
        select(
            OLIncident.SINAME,
            OLIncident.BUNAME,
            func.count().label("frequency"),
            severity_score,
        )
        .where(*_base_filter(year_s, q_s, business_unit))
        .group_by(OLIncident.SINAME, OLIncident.BUNAME)
        .order_by(func.count().desc())
    ).all()

    if not rows:
        return []

    freqs = [r.frequency for r in rows]
    sevs = [float(r.severity_score) for r in rows]
    norm_freq = _minmax_norm(freqs)
    norm_sev = _minmax_norm(sevs)

    result = [
        HeatmapPoint(
            site=r.SINAME or "Unknown",
            business_unit=r.BUNAME,
            likelihood_score=round(norm_freq[i], 4),
            impact_score=round(norm_sev[i], 4),
            risk_band=_risk_band((norm_freq[i] + norm_sev[i]) / 2),
        )
        for i, r in enumerate(rows)
    ]
    _cache_set(cache_key, result)
    return result
