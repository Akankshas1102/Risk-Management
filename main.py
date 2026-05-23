import io
import os
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

_ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

load_dotenv()

app = FastAPI(title="OL_INCIDENTS Data Exporter", version="1.0.0")

EXPORT_DIR = Path(__file__).parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

DATE_COL = os.getenv("DATE_COLUMN", "OCCUREDDATE")


def get_connection():
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={os.getenv('DB_HOST')},{os.getenv('DB_PORT', '1433')};"
        f"DATABASE={os.getenv('DB')};"
        f"UID={os.getenv('DB_USER')};"
        f"PWD={os.getenv('DB_PASSWD')};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    try:
        return pyodbc.connect(conn_str)
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"DB connection failed: {str(e)}")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(
            lambda v: _ILLEGAL_CHARS.sub("", v) if isinstance(v, str) else v
        )
    return df


def run_query(sql: str) -> pd.DataFrame:
    with get_connection() as conn:
        df = pd.read_sql(sql, conn)
    return clean_dataframe(df)


def fy_label(start_year: int) -> str:
    return f"FY{start_year}-{str(start_year + 1)[-2:]}"


def fy_where(start_year: int, col: str = DATE_COL) -> str:
    """SQL WHERE clause for one financial year (Apr 1 – Mar 31) on a YYYY-MM-DD text column."""
    return (
        f"CONVERT(DATE, [{col}]) >= '{start_year}-04-01' "
        f"AND CONVERT(DATE, [{col}]) <= '{start_year + 1}-03-31'"
    )


def all_fy_years_in_db() -> list[int]:
    """Return sorted list of FY start-years present in the table."""
    sql = f"""
        SELECT DISTINCT
            CASE
                WHEN MONTH(CONVERT(DATE, [{DATE_COL}])) >= 4
                    THEN YEAR(CONVERT(DATE, [{DATE_COL}]))
                ELSE YEAR(CONVERT(DATE, [{DATE_COL}])) - 1
            END AS fy_start
        FROM dbo.OL_INCIDENTS
        WHERE TRY_CONVERT(DATE, [{DATE_COL}]) IS NOT NULL
        ORDER BY fy_start DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [r[0] for r in rows]


def save_df_to_file(df: pd.DataFrame, filepath: Path, fmt: str, sheet: str) -> None:
    if fmt == "xlsx":
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet[:31])
    else:
        df.to_csv(filepath, index=False)


# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "message": "OL_INCIDENTS Exporter API",
        "endpoints": {
            "preview":         "GET /preview?limit=10",
            "columns":         "GET /columns",
            "save_csv":        "GET /save/csv",
            "save_xlsx":       "GET /save/xlsx",
            "financial_years": "GET /save/financial-years?format=csv&last=3  (last=0 for all)",
        },
    }


@app.get("/preview")
def preview(limit: int = Query(default=10, ge=1, le=100)):
    df = run_query(f"SELECT TOP {limit} * FROM dbo.OL_INCIDENTS")
    return {"row_count": len(df), "columns": list(df.columns), "data": df.to_dict(orient="records")}


@app.get("/columns")
def get_columns():
    df = run_query("SELECT TOP 1 * FROM dbo.OL_INCIDENTS")
    return {"columns": {col: str(dtype) for col, dtype in df.dtypes.items()}}


@app.get("/save/csv")
def save_csv(limit: int | None = Query(default=None)):
    df = run_query(f"SELECT TOP {limit} * FROM dbo.OL_INCIDENTS" if limit else "SELECT * FROM dbo.OL_INCIDENTS")
    fp = EXPORT_DIR / f"OL_INCIDENTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(fp, index=False)
    return {"status": "saved", "rows": len(df), "columns": len(df.columns), "file": str(fp)}


@app.get("/save/xlsx")
def save_xlsx(limit: int | None = Query(default=None)):
    df = run_query(f"SELECT TOP {limit} * FROM dbo.OL_INCIDENTS" if limit else "SELECT * FROM dbo.OL_INCIDENTS")
    fp = EXPORT_DIR / f"OL_INCIDENTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(fp, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="OL_INCIDENTS")
    return {"status": "saved", "rows": len(df), "columns": len(df.columns), "file": str(fp)}


# ── Financial year exports (SQL WHERE per FY) ─────────────────────────────────

@app.get("/save/financial-years")
def save_financial_years(
    format: str = Query(default="csv", description="csv or xlsx"),
    last: int   = Query(default=3,    description="Last N financial years. Use 0 for all years in DB."),
):
    """
    Runs one SELECT per financial year using a SQL WHERE clause on OCCUREDDATE.
    Saves one file per FY into the exports/ folder.
    """
    fmt = format.lower()
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'xlsx'")

    # Determine which FY start-years to export
    if last == 0:
        fy_starts = all_fy_years_in_db()
    else:
        today = date.today()
        cur = today.year if today.month >= 4 else today.year - 1
        fy_starts = [cur - i - 1 for i in range(last)]

    saved = []
    for start_year in fy_starts:
        sql = f"""
            SELECT * FROM dbo.OL_INCIDENTS
            WHERE {fy_where(start_year)}
        """
        df = run_query(sql)
        label = fy_label(start_year)
        fp = EXPORT_DIR / f"OL_INCIDENTS_{label}.{fmt}"
        save_df_to_file(df, fp, fmt, label)
        saved.append({
            "financial_year": label,
            "period": f"{start_year}-04-01  to  {start_year + 1}-03-31",
            "rows": len(df),
            "file": str(fp),
        })

    return {"status": "saved", "files": saved}


# ── Stream (browser / Postman) ────────────────────────────────────────────────

@app.get("/download/csv")
def download_csv(limit: int | None = Query(default=None)):
    df = run_query(f"SELECT TOP {limit} * FROM dbo.OL_INCIDENTS" if limit else "SELECT * FROM dbo.OL_INCIDENTS")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    filename = f"OL_INCIDENTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/download/xlsx")
def download_xlsx(limit: int | None = Query(default=None)):
    df = run_query(f"SELECT TOP {limit} * FROM dbo.OL_INCIDENTS" if limit else "SELECT * FROM dbo.OL_INCIDENTS")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="OL_INCIDENTS")
    buf.seek(0)
    filename = f"OL_INCIDENTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"})
