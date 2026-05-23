import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=vedanta;UID=sa;PWD=m00se_1234;TrustServerCertificate=yes"
)
cursor = conn.cursor()

cursor.execute(
    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
    "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
)
print("Tables:", [r[0] for r in cursor.fetchall()])

cursor.execute(
    "SELECT TOP 8 SINAME, COUNT(*) as n FROM OL_INCIDENTS "
    "WHERE TRY_CAST(YEAR AS INT) > 2000 GROUP BY SINAME ORDER BY n DESC"
)
print("Top sites:", cursor.fetchall())

cursor.execute(
    "SELECT TOP 3 INCROWID, SINAME, BUNAME, OCCUREDDATE, QUARTER, YEAR, LEVELNAME, INCIDENTTYPENAME "
    "FROM OL_INCIDENTS WHERE TRY_CAST(YEAR AS INT) > 2000"
)
print("Sample rows:")
for r in cursor.fetchall():
    print(" ", r)

conn.close()
