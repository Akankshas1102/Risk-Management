# %% [markdown]
# # Incident Data Exploration
# Run with: `python notebooks/01_data_exploration.py`
# Or open in VS Code / Jupyter as a notebook (requires jupytext or the Jupyter extension).

# %%
import sys
from pathlib import Path

import pandas as pd

RAW_CSV = Path(__file__).parent.parent / "data" / "raw" / "OL_INCIDENTS_20260518_142042.csv"

df = pd.read_csv(RAW_CSV)

# %% [markdown]
# ## 1. Shape and dtypes

# %%
print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns\n")
print("Dtypes:")
print(df.dtypes.to_string())

# %% [markdown]
# ## 2. Null counts

# %%
null_counts = df.isnull().sum()
print("\nNull counts (non-zero only):")
print(null_counts[null_counts > 0].to_string())

# %% [markdown]
# ## 3. Value counts for key categoricals

# %%
CATEGORICAL_COLS = [
    "SINAME", "BUNAME", "INCIDENTTYPENAME", "INCIDENTCATNAME",
    "LEVELNAME", "PRIORITY", "STATUS", "YEAR",
]

for col in CATEGORICAL_COLS:
    print(f"\n{'-' * 50}")
    print(f"{col}  (unique={df[col].nunique(dropna=False)})")
    vc = df[col].value_counts(dropna=False)
    print(vc.head(20).to_string())

# %% [markdown]
# ## 4. Reporting lag distribution

# %%
df["OCCUREDDATE"] = pd.to_datetime(df["OCCUREDDATE"], errors="coerce")
df["REPORTEDDATE"] = pd.to_datetime(df["REPORTEDDATE"], errors="coerce")
df["lag_days"] = (df["REPORTEDDATE"] - df["OCCUREDDATE"]).dt.days

print("\nReporting lag (days) - REPORTEDDATE minus OCCUREDDATE:")
print(df["lag_days"].describe().to_string())
print(f"\nlag > 30 days : {(df['lag_days'] > 30).sum():,}")
print(f"lag < 0 days  : {(df['lag_days'] < 0).sum():,}  (reported before occurrence date)")
print(f"lag = 0 days  : {(df['lag_days'] == 0).sum():,}  (same-day reporting)")

print("\nPercentile breakdown:")
for p in [50, 75, 90, 95, 99]:
    print(f"  p{p:3d}: {df['lag_days'].quantile(p / 100):.0f} days")

# %% [markdown]
# ## 5. Known data-quality flags

# %%
print("\n=== DATA QUALITY FLAGS ===\n")

# Flag 1: 1899 outlier
rows_1899 = df[df["YEAR"] == 1899]
print(f"[FLAG] YEAR=1899 rows: {len(rows_1899)}")
if not rows_1899.empty:
    print(rows_1899[["INCROWID", "OCCUREDDATE", "REPORTEDDATE", "SINAME", "INCIDENTTITLE"]].to_string(index=False))

# Flag 2: PRIORITY is constant
unique_priority = df["PRIORITY"].unique()
print(f"\n[FLAG] PRIORITY unique values: {unique_priority}")
print("       Column is constant; will be dropped in cleaning.")

# Flag 3: Partial 2026 data
rows_2026 = df[df["YEAR"] == 2026]
print(f"\n[FLAG] YEAR=2026 rows: {len(rows_2026):,}  (partial year, data cut: 2026-05-18)")
print(f"       Quarter breakdown:\n{rows_2026['QUARTER'].value_counts().to_string()}")

# Flag 4: Negative lags
neg_lag = df[df["lag_days"] < 0]
print(f"\n[FLAG] Negative reporting lag: {len(neg_lag):,} rows")
print(f"       Min lag: {df['lag_days'].min():.0f} days  (REPORTEDDATE before OCCUREDDATE)")

# Flag 5: Extreme positive lags
extreme_lag = df[df["lag_days"] > 365]
print(f"\n[FLAG] Lag > 365 days: {len(extreme_lag):,} rows  (includes the 1899 outlier)")

# Flag 6: LEVELNAME edge cases
edge_levels = df[~df["LEVELNAME"].isin(["Low", "Medium", "High"])]["LEVELNAME"].value_counts(dropna=False)
print(f"\n[FLAG] LEVELNAME outside Low/Medium/High:\n{edge_levels.to_string()}")

print("\nDone.")
