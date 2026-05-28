"""List all distinct category, severity, type, BU and site values for alias-map design."""
from pathlib import Path
import pandas as pd

CSV = Path(r"c:\Users\ASUS\Desktop\Risk-Management\data\raw\OL_INCIDENTS_20260518_142042.csv")
df = pd.read_csv(CSV, low_memory=False)

print("=== INCIDENTCATNAME (all 42, with counts) ===")
print(df["INCIDENTCATNAME"].value_counts(dropna=False).to_string())

print("\n=== LEVELNAME (all values, with counts) ===")
print(df["LEVELNAME"].value_counts(dropna=False).to_string())

print("\n=== INCIDENTTYPENAME (all values, with counts) ===")
print(df["INCIDENTTYPENAME"].value_counts(dropna=False).to_string())

print("\n=== BUNAME (all values, with counts) ===")
print(df["BUNAME"].value_counts(dropna=False).to_string())

print("\n=== SINAME after upper+strip → distinct count, and casing variants ===")
norm = df["SINAME"].astype(str).str.strip().str.upper()
print("Distinct after normalisation:", norm.nunique())
variants = (df.assign(norm=norm)
              .groupby("norm")["SINAME"]
              .nunique()
              .sort_values(ascending=False))
print("Sites with >1 raw casing/spelling variant:")
print(variants[variants > 1].to_string())
