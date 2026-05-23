import sys
sys.path.insert(0, "backend")
from app.core.ssms import SSMSSession
from sqlalchemy import text

with SSMSSession() as session:
    # ENABLING actual quarterly counts
    rows = session.execute(text("""
        SELECT YEAR, QUARTER, COUNT(*) as cnt
        FROM OL_INCIDENTS
        WHERE SINAME = 'ENABLING' AND TRY_CAST(YEAR AS INT) > 2020
        GROUP BY YEAR, QUARTER
        ORDER BY YEAR, QUARTER
    """)).fetchall()

    print("=== ENABLING actuals ===")
    for r in rows:
        print(f"  {r.YEAR}-{r.QUARTER}  actual={r.cnt}")

    # What the monthly series looks like
    monthly = session.execute(text("""
        SELECT YEAR, MONTH, COUNT(*) as cnt
        FROM OL_INCIDENTS
        WHERE SINAME = 'ENABLING' AND TRY_CAST(YEAR AS INT) > 2020
        GROUP BY YEAR, MONTH
        ORDER BY CAST(YEAR AS INT), MONTH
    """)).fetchall()

    print("\n=== ENABLING monthly ===")
    total_months = len(monthly)
    total_incidents = sum(r.cnt for r in monthly)
    avg_per_month = total_incidents / total_months if total_months else 0
    print(f"  Total months: {total_months}, total incidents: {total_incidents}, avg/month: {avg_per_month:.1f}")
    for r in monthly[-12:]:   # last 12 months
        print(f"  {r.YEAR}-{r.MONTH:02d}  {r.cnt}")
