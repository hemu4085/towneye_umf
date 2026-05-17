# [FILE PATH]: scripts/verify_tier5_outcome.py
# Tier 5 verification — confirm L3 backfill closes the assessor gap and
# Lexington's first-scrape is healthy.
# Date: 2026-05-07
"""
Three checks, one script:

  [A] Arlington 29 Walnut St (parcel_id="128.0-0003-0012.0") now carries
      the full CAMA assessor record in parcel.metadata.raw_attributes.
      Compare key fields to the sidecar JSON we promoted in Tier 4.5.

  [B] Lexington's parcel.parquet has 12,780 rows, the L3 attributes
      flowed through, and at least one known address ("16 BENJAMIN RD")
      is reachable.

  [C] Lexington's local-historic.parquet has 28,061 rows but the two
      views (survey + inventory) overlap on (mhcn, address) — count the
      true unique property records vs. duplication factor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    print("=" * 78)
    print("  Tier 5 outcome verification")
    print("=" * 78)

    # ------------------------------------------------------------------
    # [A] Arlington 29 Walnut full-CAMA check.
    # ------------------------------------------------------------------
    print("\n[A] Arlington 29 Walnut — L3 raw_attributes check")
    arl = pd.read_parquet("data/gold/arlington-ma/parcel.parquet")
    print(f"    parcel.parquet rows : {len(arl):,}")
    row = arl[arl["parcel_id"] == "128.0-0003-0012.0"]
    if row.empty:
        print("    !! 29 Walnut not found by parcel_id — investigate")
    else:
        r0 = row.iloc[0]
        meta = r0["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        ra = meta.get("raw_attributes", {})
        print(f"    address      : {r0.get('address')}")
        print(f"    centroid     : ({r0.get('centroid_lat')}, {r0.get('centroid_lon')})")
        print(f"    L3 raw_attributes carries:")
        for k in [
            "OWNER1", "YEAR_BUILT", "TOTAL_VAL", "BLDG_VAL", "LAND_VAL",
            "LS_DATE", "LS_PRICE", "LS_BOOK", "LS_PAGE",
            "LOT_SIZE", "BLD_AREA", "RES_AREA", "USE_CODE", "ZONING",
            "STYLE", "STORIES", "NUM_ROOMS",
        ]:
            v = ra.get(k)
            mark = "y" if v is not None else "-"
            print(f"      [{mark}] {k:<14} = {v!r}")

    # ------------------------------------------------------------------
    # [B] Lexington parcel sanity.
    # ------------------------------------------------------------------
    print("\n[B] Lexington parcel.parquet sanity")
    lex = pd.read_parquet("data/gold/lexington-ma/parcel.parquet")
    print(f"    parcel.parquet rows : {len(lex):,}")
    print(f"    cols                : {list(lex.columns)}")
    print(f"    sample addresses   :")
    for a in lex["address"].dropna().head(5):
        print(f"      '{a}'")

    by_addr = lex[lex["address"].fillna("").str.upper() == "16 BENJAMIN RD"]
    if not by_addr.empty:
        r = by_addr.iloc[0]
        meta = r["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        ra = meta.get("raw_attributes", {})
        print(f"\n    16 BENJAMIN RD spot check:")
        print(f"      parcel_id    : {r['parcel_id']}")
        print(f"      area_sqft    : {r.get('area_sqft')}")
        print(f"      OWNER1       : {ra.get('OWNER1')}")
        print(f"      YEAR_BUILT   : {ra.get('YEAR_BUILT')}")
        print(f"      LS_PRICE     : {ra.get('LS_PRICE')}")
        print(f"      ZONING       : {ra.get('ZONING')}")

    # ------------------------------------------------------------------
    # [C] Lexington local-historic dedup analysis.
    # ------------------------------------------------------------------
    print("\n[C] Lexington local-historic dedup analysis")
    lh = pd.read_parquet("data/gold/lexington-ma/local-historic.parquet")
    print(f"    rows total            : {len(lh):,}")

    if "mhcn" in lh.columns:
        with_mhcn = lh[lh["mhcn"].fillna("") != ""]
        print(f"    rows with MHCN       : {len(with_mhcn):,}")
        print(f"    unique MHCN values   : {with_mhcn['mhcn'].nunique():,}")

    # Source breakdown — how many came from each FeatureServer?
    if "source_dataset" in lh.columns:
        print("    rows per source       :")
        for src, n in lh["source_dataset"].value_counts().head(10).items():
            print(f"      {src:<40} {n:>7,}")
    else:
        # try metadata.source key
        sample_meta = lh["metadata"].iloc[0] if "metadata" in lh.columns else None
        print(f"    sample metadata cols : {sample_meta if isinstance(sample_meta, dict) else (sample_meta[:200] if isinstance(sample_meta, str) else 'n/a')}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
