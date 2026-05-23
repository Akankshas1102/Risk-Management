"""
Service layer for risk-driver and recommendation regeneration.

Public API (for Vinay's endpoints):
    regenerate_for_site(site, db=None) -> dict
        Re-computes SHAP drivers + rules-based recommendations for one site
        and persists the results.  Opens its own SSMSSession internally;
        the `db` argument is accepted for FastAPI Depends compatibility but
        is not used.

    regenerate_all(dry_run=False) -> dict
        Convenience wrapper that runs regenerate_for_site for every site
        found in OL_INCIDENTS.  Used by the nightly pipeline and CLI scripts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from app.core.ssms import SSMSSession
from app.ml.drivers import compute_drivers_for_site
from app.models.drivers import Recommendation, RiskDriver
from app.models.ol_incidents import OLIncident
from app.services.recommendations import generate_recommendations


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_site_context(site: str, sf) -> dict:
    """Return site-level context dict used by the rules engine."""
    with sf() as session:
        row = session.execute(
            text("""
                SELECT TOP 1 YEAR, QUARTER, COUNT(*) AS total
                FROM OL_INCIDENTS
                WHERE SINAME = :s AND TRY_CAST(YEAR AS INT) > 2000
                GROUP BY YEAR, QUARTER
                ORDER BY CAST(YEAR AS INT)*10 +
                    CASE QUARTER WHEN 'Q4' THEN 0 WHEN 'Q1' THEN 1
                                 WHEN 'Q2' THEN 2 ELSE 3 END DESC
            """),
            {"s": site},
        ).first()
        if not row:
            return {}

        prev = session.execute(
            text("""
                SELECT TOP 1 COUNT(*) AS total FROM OL_INCIDENTS
                WHERE SINAME = :s AND TRY_CAST(YEAR AS INT) > 2000
                  AND NOT (YEAR = :y AND QUARTER = :q)
                GROUP BY YEAR, QUARTER
                ORDER BY CAST(YEAR AS INT)*10 +
                    CASE QUARTER WHEN 'Q4' THEN 0 WHEN 'Q1' THEN 1
                                 WHEN 'Q2' THEN 2 ELSE 3 END DESC
            """),
            {"s": site, "y": row.YEAR, "q": row.QUARTER},
        ).first()

        lag_rows = session.execute(
            text("""
                SELECT OCCUREDDATE, REPORTEDDATE FROM OL_INCIDENTS
                WHERE SINAME = :s AND YEAR = :y AND QUARTER = :q
                  AND OCCUREDDATE IS NOT NULL AND REPORTEDDATE IS NOT NULL
                  AND LEN(OCCUREDDATE) = 10 AND LEN(REPORTEDDATE) = 10
            """),
            {"s": site, "y": row.YEAR, "q": row.QUARTER},
        ).all()

        bu_row = session.execute(
            select(OLIncident.BUNAME)
            .where(OLIncident.SINAME == site)
            .limit(1)
        ).first()

    lags = []
    for r in lag_rows:
        try:
            lags.append(
                (pd.Timestamp(r.REPORTEDDATE) - pd.Timestamp(r.OCCUREDDATE)).days
            )
        except Exception:
            pass

    prev_total = prev.total if prev else None
    delta = (
        round((row.total - prev_total) / prev_total * 100, 1) if prev_total else None
    )
    return {
        "site": site,
        "quarter": f"{row.YEAR}-{row.QUARTER}",
        "total_incidents_qtr": row.total,
        "delta_qtr_pct": delta,
        "reporting_lag_p90": float(np.percentile(lags, 90)) if lags else None,
        "business_unit": bu_row[0] if bu_row else None,
    }


def _persist(
    site: str,
    drivers_df: pd.DataFrame,
    recs: list,
    quarter: str,
    sf,
) -> tuple[int, int]:
    """
    Delete-then-insert drivers and recommendations for one site.

    Returns (driver_rows_written, rec_rows_written).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with sf() as session:
        # Drivers
        session.execute(text("DELETE FROM risk_drivers WHERE site = :s"), {"s": site})
        for _, row in drivers_df.iterrows():
            session.add(RiskDriver(
                site=site,
                quarter=row["quarter"],
                driver_name=row["driver_name"],
                category=row["category"],
                impact_score=row["impact_score"],
                trend=row["trend"],
                pct_change_vs_last_qtr=row["pct_change_vs_last_qtr"],
                sparkline_data=row.get("sparkline_data"),
                computed_at=row["computed_at"],
            ))

        # Recommendations (scoped to site+quarter)
        session.execute(
            text("DELETE FROM recommendations WHERE site = :s AND quarter = :q"),
            {"s": site, "q": quarter},
        )
        for rec in recs:
            session.add(Recommendation(
                site=site,
                quarter=quarter,
                action_text=rec.action_text,
                priority=rec.priority,
                impact_estimate=rec.impact_estimate or "",
                suggested_owner=rec.suggested_owner or "",
                status="open",
                source=rec.source,
                driver_link=rec.driver_link or "",
                created_at=now,
            ))

        session.commit()

    return len(drivers_df), len(recs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def regenerate_for_site(site: str, db=None) -> dict:
    """
    Re-compute SHAP drivers and rules-based recommendations for *one* site
    and persist the results.

    Parameters
    ----------
    site : Site name matching SINAME in OL_INCIDENTS.
    db   : Accepted for FastAPI ``Depends`` compatibility; not used internally.
           The function manages its own SSMSSession transactions.

    Returns
    -------
    dict
        ``{site, quarter, drivers_written, recs_written}``

    Raises
    ------
    RuntimeError
        If the site has no incident data (nothing to compute).
    """
    sf = SSMSSession
    drivers_df = compute_drivers_for_site(site, session_factory=sf)
    if drivers_df.empty:
        raise RuntimeError(f"No incident data found for site '{site}'")

    top10 = drivers_df.head(10)
    ctx = _get_site_context(site, sf)
    quarter = ctx.get("quarter") or top10.iloc[0]["quarter"]
    recs = generate_recommendations(top10.to_dict(orient="records"), ctx)

    d_written, r_written = _persist(site, top10, recs, quarter, sf)

    return {
        "site": site,
        "quarter": quarter,
        "drivers_written": d_written,
        "recs_written": r_written,
    }


def regenerate_all(dry_run: bool = False) -> dict:
    """
    Run ``regenerate_for_site`` for every site in OL_INCIDENTS.

    Parameters
    ----------
    dry_run : If True, compute but do not persist.

    Returns
    -------
    dict
        ``{sites_processed, sites_skipped, total_drivers, total_recs, errors}``
    """
    sf = SSMSSession
    with sf() as session:
        rows = session.execute(
            select(OLIncident.SINAME, OLIncident.BUNAME)
            .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
            .distinct()
            .order_by(OLIncident.SINAME)
        ).all()

    all_sites = [r.SINAME for r in rows]
    ok = skipped = errors = total_drivers = total_recs = 0

    for site in all_sites:
        try:
            drivers_df = compute_drivers_for_site(site, session_factory=sf)
            if drivers_df.empty:
                skipped += 1
                continue

            top10 = drivers_df.head(10)
            ctx = _get_site_context(site, sf)
            quarter = ctx.get("quarter") or top10.iloc[0]["quarter"]
            recs = generate_recommendations(top10.to_dict(orient="records"), ctx)

            if not dry_run:
                _persist(site, top10, recs, quarter, sf)

            total_drivers += len(top10)
            total_recs += len(recs)
            ok += 1
        except Exception:
            errors += 1

    return {
        "sites_processed": ok,
        "sites_skipped": skipped,
        "total_drivers": total_drivers,
        "total_recs": total_recs,
        "errors": errors,
    }
