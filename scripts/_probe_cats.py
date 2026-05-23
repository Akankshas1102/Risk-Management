"""Probe category distribution and quarterly pivot shape for a reference site."""
import pyodbc, json

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=vedanta;UID=sa;PWD=m00se_1234;TrustServerCertificate=yes"
)
c = conn.cursor()

# Top categories across all data
c.execute("""
    SELECT TOP 20 INCIDENTCATNAME, COUNT(*) n
    FROM OL_INCIDENTS WHERE TRY_CAST(YEAR AS INT)>2000
    GROUP BY INCIDENTCATNAME ORDER BY n DESC
""")
print("TOP 20 CATEGORIES:")
for r in c.fetchall():
    print(f"  {r.n:>6}  {r.INCIDENTCATNAME}")

# Quarterly pivot shape for IRON ORE KARNATAKA
c.execute("""
    SELECT YEAR, QUARTER, INCIDENTCATNAME, COUNT(*) n
    FROM OL_INCIDENTS
    WHERE SINAME='IRON ORE KARNATAKA' AND TRY_CAST(YEAR AS INT)>2000
    GROUP BY YEAR, QUARTER, INCIDENTCATNAME
    ORDER BY YEAR, QUARTER
""")
rows = c.fetchall()
quarters = sorted(set((r.YEAR, r.QUARTER) for r in rows))
cats = sorted(set(r.INCIDENTCATNAME for r in rows if r.INCIDENTCATNAME))
print(f"\nIRON ORE KARNATAKA: {len(quarters)} quarters, {len(cats)} distinct categories")
print("Quarters:", quarters)

conn.close()
