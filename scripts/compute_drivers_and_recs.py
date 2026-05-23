"""
CLI: compute SHAP-based risk drivers and rules-based recommendations for all sites.

Usage:
    python scripts/compute_drivers_and_recs.py
    python scripts/compute_drivers_and_recs.py --sites "ENABLING" "VAL J"
    python scripts/compute_drivers_and_recs.py --dry-run

Run apply_ssms_migrations.py first to create risk_drivers / recommendations tables.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from app.core.ssms import SSMSSession
from app.ml.drivers import compute_drivers_for_site
from app.models.drivers import Recommendation, RiskDriver
from app.models.ol_incidents import OLIncident
import app.models.drivers  # noqa — register tables with SSMSBase
from app.services.recommendations import generate_recommendations


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute risk drivers and recommendations.")
    p.add_argument("--sites", nargs="*", help="Specific sites (default: all)")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def get_all_sites(sf) -> list[tuple[str, str]]:
    with sf() as session:
        rows = session.execute(
            select(OLIncident.SINAME, OLIncident.BUNAME)
            .where(OLIncident.YEAR >= "2020", OLIncident.SINAME.isnot(None))
            .distinct()
            .order_by(OLIncident.SINAME)
        ).all()
    return [(r.SINAME, r.BUNAME) for r in rows]


def get_site_data(site: str, sf) -> dict:
    """Build site-level context dict for the recommendations engine."""
    with sf() as session:
        # Most recent complete quarter
        row = session.execute(
            text("""
                SELECT TOP 1 YEAR, QUARTER, COUNT(*) as total
                FROM OL_INCIDENTS
                WHERE SINAME = :s AND TRY_CAST(YEAR AS INT) > 2000
                GROUP BY YEAR, QUARTER
                ORDER BY CAST(YEAR AS INT) * 10 +
                    CASE QUARTER
                        WHEN 'Q4' THEN 0 WHEN 'Q1' THEN 1
                        WHEN 'Q2' THEN 2 ELSE 3 END DESC
            """),
            {"s": site},
        ).first()
        if not row:
            return {}

        cur_year, cur_q, cur_total = row.YEAR, row.QUARTER, row.total

        # Previous quarter total (for delta)
        prev_row = session.execute(
            text("""
                SELECT TOP 1 COUNT(*) as total
                FROM OL_INCIDENTS
                WHERE SINAME = :s AND TRY_CAST(YEAR AS INT) > 2000
                  AND NOT (YEAR = :y AND QUARTER = :q)
                GROUP BY YEAR, QUARTER
                ORDER BY CAST(YEAR AS INT) * 10 +
                    CASE QUARTER
                        WHEN 'Q4' THEN 0 WHEN 'Q1' THEN 1
                        WHEN 'Q2' THEN 2 ELSE 3 END DESC
            """),
            {"s": site, "y": cur_year, "q": cur_q},
        ).first()
        prev_total = prev_row.total if prev_row else None
        delta = (
            round((cur_total - prev_total) / prev_total * 100, 1)
            if prev_total
            else None
        )

        # Reporting lag p90 (OCCUREDDATE and REPORTEDDATE are VARCHAR "YYYY-MM-DD")
        lag_rows = session.execute(
            text("""
                SELECT OCCUREDDATE, REPORTEDDATE
                FROM OL_INCIDENTS
                WHERE SINAME = :s AND YEAR = :y AND QUARTER = :q
                  AND OCCUREDDATE IS NOT NULL AND REPORTEDDATE IS NOT NULL
                  AND LEN(OCCUREDDATE) = 10 AND LEN(REPORTEDDATE) = 10
            """),
            {"s": site, "y": cur_year, "q": cur_q},
        ).all()

        lags = []
        for r in lag_rows:
            try:
                lag = (pd.Timestamp(r.REPORTEDDATE) - pd.Timestamp(r.OCCUREDDATE)).days
                lags.append(lag)
            except Exception:
                pass
        lag_p90 = float(np.percentile(lags, 90)) if lags else None

        # BU
        bu_row = session.execute(
            select(OLIncident.BUNAME)
            .where(OLIncident.SINAME == site)
            .limit(1)
        ).first()
        bu = bu_row[0] if bu_row else None

    return {
        "site": site,
        "quarter": f"{cur_year}-{cur_q}",
        "total_incidents_qtr": cur_total,
        "delta_qtr_pct": delta,
        "reporting_lag_p90": lag_p90,
        "business_unit": bu,
    }


def persist_drivers(drivers_df: pd.DataFrame, site: str, sf, dry_run: bool) -> None:
    if dry_run or drivers_df.empty:
        return
    with sf() as session:
        session.execute(text("DELETE FROM risk_drivers WHERE site = :s"), {"s": site})
        for _, row in drivers_df.iterrows():
            session.add(RiskDriver(**{
                "site": site,
                "quarter": row["quarter"],
                "driver_name": row["driver_name"],
                "category": row["category"],
                "impact_score": row["impact_score"],
                "trend": row["trend"],
                "pct_change_vs_last_qtr": row["pct_change_vs_last_qtr"],
                "computed_at": row["computed_at"],
            }))
        session.commit()


def persist_recommendations(recs, site: str, quarter: str, sf, dry_run: bool) -> None:
    if dry_run or not recs:
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with sf() as session:
        for rec in recs:
            # Upsert via delete+insert (SQL Server lacks ON CONFLICT ... DO UPDATE)
            session.execute(
                text("""
                    DELETE FROM recommendations
                    WHERE site = :s AND quarter = :q AND action_text = :a
                """),
                {"s": site, "q": quarter, "a": rec.action_text},
            )
            session.add(Recommendation(
                site=site,
                quarter=quarter,
                action_text=rec.action_text,
                priority=rec.priority,
                impact_estimate=rec.impact_estimate or "",
                suggested_owner=rec.suggested_owner or "",
                status="open",
                source=rec.source,
                created_at=now,
            ))
        session.commit()


def main() -> None:
    args = parse_args()
    sf = SSMSSession

    all_pairs = get_all_sites(sf)
    if args.sites:
        all_pairs = [(s, bu) for s, bu in all_pairs if s in args.sites]

    print(f"Processing {len(all_pairs)} site(s).{'  DRY RUN' if args.dry_run else ''}")
    ok = skipped = errors = 0

    for site, bu in all_pairs:
        try:
            drivers_df = compute_drivers_for_site(site, session_factory=sf)
            if drivers_df.empty:
                skipped += 1
                continue

            top10 = drivers_df.head(10).to_dict(orient="records")
            site_data = get_site_data(site, sf)
            quarter = site_data.get("quarter", drivers_df.iloc[0]["quarter"])

            recs = generate_recommendations(top10, site_data)

            persist_drivers(drivers_df.head(10), site, sf, args.dry_run)
            persist_recommendations(recs, site, quarter, sf, args.dry_run)

            top_driver = drivers_df.iloc[0]["driver_name"] if not drivers_df.empty else "n/a"
            print(
                f"  {site:<32}  top={top_driver[:25]:<25}  "
                f"drivers={len(drivers_df)}  recs={len(recs)}"
            )
            ok += 1

        except Exception as exc:
            print(f"  ERROR {site}: {exc}", file=sys.stderr)
            errors += 1

    print(f"\nDone. ok={ok}  skipped={skipped}  errors={errors}")


if __name__ == "__main__":
    main()
