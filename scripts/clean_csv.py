"""
scripts/clean_csv.py
====================
One-shot CSV cleanup. Reads the raw OL_INCIDENTS export and writes a cleaned
copy that the pipeline will use going forward.

What it does
------------
1. Drops rows with YEAR < 2000  (the 1899 sentinel row)
2. Normalises SINAME            (UPPERCASE + strip + collapse internal whitespace)
3. Canonicalises INCIDENTCATNAME variants — for each group of near-identical
   spellings, the most common spelling wins and the rest are renamed to match.

What it does NOT do
-------------------
- Touch the original file (read-only on the source CSV).
- Fix LEVELNAME anomalies (you have 4 odd values: 'Level 1 (Minor)',
  'Level 2 (Major)', 'Select'). Add to FIX_LEVELNAME below to enable.

Output
------
data/raw/OL_INCIDENTS_clean.csv

After running this, scripts/load_csv_to_db.py automatically picks up the
cleaned file (no further code change needed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "data" / "raw" / "OL_INCIDENTS_20260518_142042.csv"
DST = REPO_ROOT / "data" / "raw" / "OL_INCIDENTS_clean.csv"

# Set to True to also normalise LEVELNAME anomalies:
#   'Level 1 (Minor)' -> 'Low'
#   'Level 2 (Major)' -> 'High'
#   'Select'          -> 'Low'
FIX_LEVELNAME = False

# Explicit category aliases for cases the automatic canonical grouping
# can't catch — e.g. American vs British spelling.  Add new pairs here
# as you spot them. Format: { 'bad_spelling': 'canonical_spelling' }
CATEGORY_ALIASES: dict[str, str] = {
    # Villagers/Neighbourhood — American vs British + spacing
    "PR-Villagers/Neighbourhood": "PR - Villagers/ Neighborhood",
}


def canonical_form(s: str) -> str:
    """Whitespace + case insensitive key used to group near-identical strings."""
    return re.sub(r"\s+", "", s.strip().upper())


def main() -> None:
    if not SRC.exists():
        print(f"ERROR: source CSV not found: {SRC}")
        sys.exit(1)

    print("=" * 70)
    print(f"Reading: {SRC.name}")
    df = pd.read_csv(SRC, low_memory=False)
    rows_before = len(df)
    print(f"  rows: {rows_before:,}")
    print("=" * 70)

    # ── Step 1: drop pre-2000 rows ──────────────────────────────────────
    print("\n[1] Dropping rows with YEAR < 2000")
    year_num = pd.to_numeric(df["YEAR"], errors="coerce")
    dropped = df[year_num < 2000]
    df = df[~(year_num < 2000)].copy()
    print(f"    Dropped {len(dropped)} row(s)")
    for _, r in dropped.iterrows():
        print(f"      - INCROWID={r['INCROWID']}  YEAR={r['YEAR']}  "
              f"OCCUREDDATE={r['OCCUREDDATE']}  SINAME={r['SINAME']}")

    # ── Step 2: normalise SINAME ────────────────────────────────────────
    print("\n[2] Normalising SINAME (UPPER + strip + collapse whitespace)")
    if "SINAME" in df.columns:
        # Drop rows where SINAME is null/blank — they can't belong to any site.
        null_mask = df["SINAME"].isna() | (df["SINAME"].astype(str).str.strip() == "")
        n_null = int(null_mask.sum())
        if n_null:
            print(f"    Dropping {n_null} row(s) with null/blank SINAME")
            df = df[~null_mask].copy()

        before_unique = df["SINAME"].nunique()
        before_values = sorted(df["SINAME"].dropna().unique().tolist())

        # IMPORTANT: do NOT use .astype(str) here — it converts NaN to literal 'nan'
        # which then becomes "NAN" after .upper(), creating a fake site named "NAN".
        df["SINAME"] = (
            df["SINAME"]
            .str.strip()
            .str.upper()
            .str.replace(r"\s+", " ", regex=True)
        )
        after_unique = df["SINAME"].nunique()
        merged = before_unique - after_unique
        print(f"    {before_unique} unique -> {after_unique} unique  ({merged} variant(s) merged)")

        if merged > 0:
            # Show which variants merged
            after_values = set(df["SINAME"].dropna().unique().tolist())
            removed = [v for v in before_values if v not in after_values]
            for v in removed[:20]:
                normalised = re.sub(r"\s+", " ", v.strip().upper())
                print(f"      - {v!r} -> {normalised!r}")

    # ── Step 3: canonicalise INCIDENTCATNAME ────────────────────────────
    print("\n[3] Canonicalising INCIDENTCATNAME variants")
    cat_col = "INCIDENTCATNAME"
    if cat_col in df.columns:
        before_unique = df[cat_col].nunique()
        merge_count = 0

        # 3a) Apply explicit aliases (American/British, known typos, etc.)
        if CATEGORY_ALIASES:
            print("    (a) Applying explicit aliases:")
            for bad, good in CATEGORY_ALIASES.items():
                n = (df[cat_col] == bad).sum()
                if n:
                    print(f"        - {bad!r} ({n} rows) -> {good!r}")
                    df[cat_col] = df[cat_col].replace(bad, good)
                    merge_count += 1

        # 3b) Auto-detect remaining whitespace/case variants
        print("    (b) Auto-detecting whitespace/case variants:")
        groups: dict[str, list[tuple[str, int]]] = {}
        for cat, cnt in df[cat_col].dropna().value_counts().items():
            key = canonical_form(str(cat))
            groups.setdefault(key, []).append((cat, int(cnt)))

        rename_map: dict[str, str] = {}
        for variants in groups.values():
            if len(variants) <= 1:
                continue
            variants.sort(key=lambda x: x[1], reverse=True)
            canonical = variants[0][0]
            for variant, cnt in variants[1:]:
                rename_map[variant] = canonical
                merge_count += 1
                print(f"        - {variant!r} ({cnt} rows) -> {canonical!r}")

        if rename_map:
            df[cat_col] = df[cat_col].replace(rename_map)
        after_unique = df[cat_col].nunique()
        print(f"    {before_unique} unique -> {after_unique} unique  "
              f"({merge_count} variant(s) merged total)")

    # ── Step 4 (optional): LEVELNAME anomalies ──────────────────────────
    if FIX_LEVELNAME and "LEVELNAME" in df.columns:
        print("\n[4] Normalising LEVELNAME anomalies")
        level_map = {
            "Level 1 (Minor)": "Low",
            "Level 2 (Major)": "High",
            "Select":          "Low",
        }
        fixed = 0
        for bad, good in level_map.items():
            n = (df["LEVELNAME"] == bad).sum()
            if n:
                print(f"    - {bad!r} ({n} rows) -> {good!r}")
                fixed += n
        df["LEVELNAME"] = df["LEVELNAME"].replace(level_map)
        print(f"    Fixed {fixed} row(s)")

    # ── Save ───────────────────────────────────────────────────────────
    df.to_csv(DST, index=False)
    print("\n" + "=" * 70)
    print(f"Wrote: {DST.name}")
    print(f"  rows: {len(df):,}  (was {rows_before:,})")
    print("=" * 70)

    print("\nNEXT STEPS")
    print("  1. python scripts/load_csv_to_db.py     # reload Postgres from the cleaned CSV")
    print("  2. python scripts/run_pipeline.py -v   # retrain everything")
    print()


if __name__ == "__main__":
    main()
