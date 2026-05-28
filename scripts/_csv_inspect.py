"""Quick CSV diagnostic for OL_INCIDENTS — read-only, prints to stdout."""
import sys
from pathlib import Path

CSV = Path(r"c:\Users\ASUS\Desktop\Risk-Management\data\raw\OL_INCIDENTS_20260518_142042.csv")

try:
    import pandas as pd
except ImportError:
    print("pandas not available; falling back to csv stdlib")
    import csv
    with CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
        rdr = csv.reader(f)
        header = next(rdr)
        rows = list(rdr)
    print("ROWS:", len(rows))
    print("COLUMNS:", len(header))
    print("HEADER:", header)
    sys.exit(0)

df = pd.read_csv(CSV, low_memory=False)
print("SHAPE:", df.shape)
print("\nCOLUMNS:")
for c in df.columns:
    print("  ", c)

print("\nDTYPES:")
print(df.dtypes.to_string())

print("\nNULL COUNTS (sorted desc):")
print(df.isna().sum().sort_values(ascending=False).to_string())

print("\nUNIQUE COUNTS (key columns):")
for col in ["VNAME","BUNAME","SINAME","PRIORITY","STATUS","INCIDENTTYPENAME",
            "INCIDENTCATNAME","LEVELNAME","YEAR","QUARTER","MONTH","ZNAME",
            "INCIDENTTYPENAME_DISPLAY","INCIDENTCATNAME_DISPLAY","INCIDENTCOUNT"]:
    if col in df.columns:
        print(f"  {col}: {df[col].nunique(dropna=True)}  (sample: {df[col].dropna().unique()[:5].tolist()})")

print("\nYEAR distribution:")
if "YEAR" in df.columns:
    print(df["YEAR"].value_counts(dropna=False).sort_index().to_string())

print("\nLEVELNAME distribution:")
if "LEVELNAME" in df.columns:
    print(df["LEVELNAME"].value_counts(dropna=False).to_string())

print("\nINCIDENTTYPENAME distribution:")
if "INCIDENTTYPENAME" in df.columns:
    print(df["INCIDENTTYPENAME"].value_counts(dropna=False).to_string())

print("\nINCIDENTCATNAME distribution (top 25):")
if "INCIDENTCATNAME" in df.columns:
    print(df["INCIDENTCATNAME"].value_counts(dropna=False).head(25).to_string())

print("\nSINAME distribution (top 40):")
if "SINAME" in df.columns:
    print(df["SINAME"].value_counts(dropna=False).head(40).to_string())

print("\nBUNAME distribution:")
if "BUNAME" in df.columns:
    print(df["BUNAME"].value_counts(dropna=False).to_string())

# Date parsing checks
for c in ["OCCUREDDATE","REPORTEDDATE","LASTUPDATEDDATE","DSRDATE"]:
    if c in df.columns:
        parsed = pd.to_datetime(df[c], errors="coerce", format="%Y-%m-%d")
        bad = parsed.isna().sum() - df[c].isna().sum()
        print(f"\n{c}: parseable={parsed.notna().sum()}  null_in_csv={df[c].isna().sum()}  unparseable_non_null={max(bad,0)}")
        print(f"   min={parsed.min()}  max={parsed.max()}")

# Reporting lag
if "OCCUREDDATE" in df.columns and "REPORTEDDATE" in df.columns:
    occ = pd.to_datetime(df["OCCUREDDATE"], errors="coerce")
    rep = pd.to_datetime(df["REPORTEDDATE"], errors="coerce")
    lag = (rep - occ).dt.days
    print("\nREPORTING LAG (days) summary:")
    print(lag.describe().to_string())
    print("  negative_lag rows:", int((lag < 0).sum()))

# Duplicates and sample garbage
if "INCROWID" in df.columns:
    print("\nINCROWID dupes:", int(df["INCROWID"].duplicated().sum()))
if "INCIDENTID" in df.columns:
    print("INCIDENTID dupes:", int(df["INCIDENTID"].duplicated().sum()))

# Site name normalisation preview
if "SINAME" in df.columns:
    raw = df["SINAME"].dropna().astype(str)
    norm = raw.str.strip().str.upper()
    diff = (raw != norm).sum()
    print(f"\nSINAME would change after upper+strip on {diff} rows")
    print("Sample variant pairs (first 10):")
    for r, n in zip(raw[raw != norm].head(10), norm[raw != norm].head(10)):
        print(f"   {r!r}  ->  {n!r}")

# Per-month rows for site coverage check
if "YEAR" in df.columns and "MONTH" in df.columns and "SINAME" in df.columns:
    g = df.groupby("SINAME").size().sort_values(ascending=False)
    print("\nIncidents per site (top 10):")
    print(g.head(10).to_string())
    print("\nIncidents per site (bottom 10):")
    print(g.tail(10).to_string())
    months_per_site = (
        df.dropna(subset=["YEAR","MONTH"]).assign(ym=df["YEAR"].astype(str)+"-"+df["MONTH"].astype(str))
          .groupby("SINAME")["ym"].nunique().sort_values()
    )
    print("\nDistinct (year,month) per site (bottom 10 — these are sparse):")
    print(months_per_site.head(10).to_string())
    print("\nDistinct (year,month) per site (top 5 — these are dense):")
    print(months_per_site.tail(5).to_string())
