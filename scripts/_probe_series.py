"""Probe monthly series depth per site — informs fallback threshold."""
import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=vedanta;UID=sa;PWD=m00se_1234;TrustServerCertificate=yes"
)
cursor = conn.cursor()

cursor.execute("""
    SELECT
        SINAME,
        BUNAME,
        COUNT(*) AS total_incidents,
        COUNT(DISTINCT YEAR + '-' + CAST(MONTH AS VARCHAR)) AS distinct_months,
        MIN(YEAR) AS min_year,
        MAX(YEAR) AS max_year
    FROM OL_INCIDENTS
    WHERE TRY_CAST(YEAR AS INT) > 2000
      AND SINAME IS NOT NULL
    GROUP BY SINAME, BUNAME
    ORDER BY total_incidents DESC
""")
rows = cursor.fetchall()
print(f"{'SITE':<30} {'BU':<28} {'INCIDENTS':>10} {'MONTHS':>7} {'FROM':>6} {'TO':>6}")
print("-" * 90)
sufficient = 0
for r in rows:
    flag = "" if r.total_incidents >= 50 and r.distinct_months >= 12 else " *** LOW"
    if not flag:
        sufficient += 1
    print(f"{(r.SINAME or '')[:30]:<30} {(r.BUNAME or '')[:28]:<28} {r.total_incidents:>10} {r.distinct_months:>7} {r.min_year:>6} {r.max_year:>6}{flag}")

print(f"\nSites with sufficient data (>=50 incidents AND >=12 months): {sufficient}/{len(rows)}")
conn.close()
