# [FILE PATH]: scripts/verify_l3_arlington_compat.py
# Tier 5 prep — verify MassGIS L3 carries Arlington data with the same
#                MAP_PAR_ID format the existing parcel.parquet uses.
# Date: 2026-05-07
"""
Sanity check before switching Arlington's parcel source from its own AGOL
("Parcels with CAMA" FeatureServer) to MassGIS L3 statewide.

Two questions, one script:

  Q1. Does MassGIS L3 layer 0 carry Arlington (TOWN_ID=10) records?
      Expected: ~13,000.

  Q2. Is MAP_PAR_ID format identical to Arlington's existing
      parcel.parquet?  We check the specific value
      "128.0-0003-0012.0" (29 Walnut St) and the value-pattern
      compared to a current sample from parcel.parquet.

If both pass, the parcel source switch is safe.  If MAP_PAR_ID format
diverges, we need to either rebuild identity links or maintain the
existing source as a fallback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    print("=" * 78)
    print("  Verify MassGIS L3 Arlington compatibility")
    print("=" * 78)

    l3_url = (
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
        "Massachusetts_Property_Tax_Parcels/FeatureServer/0/query"
    )

    # Arlington's MassGIS TOWN_ID is 10.
    print("\n[Q1] Arlington record count in L3...")
    r = requests.get(
        l3_url,
        params={"where": "TOWN_ID=10", "returnCountOnly": "true", "f": "json"},
        timeout=15,
    ).json()
    arl_count = r.get("count", 0)
    print(f"    L3 (TOWN_ID=10) Arlington parcels: {arl_count:,}")

    print("\n[Q2a] Look up 29 Walnut St in L3 by exact MAP_PAR_ID match...")
    target_id = "128.0-0003-0012.0"
    r = requests.get(
        l3_url,
        params={
            "where": f"TOWN_ID=10 AND MAP_PAR_ID='{target_id}'",
            "outFields": "MAP_PAR_ID,SITE_ADDR,OWNER1,YEAR_BUILT,TOTAL_VAL,LS_DATE,LS_PRICE,LOT_SIZE,LS_BOOK,LS_PAGE",
            "f": "json",
        },
        timeout=15,
    ).json()
    feats = r.get("features", [])
    if feats:
        attrs = feats[0]["attributes"]
        print(f"    EXACT MATCH found:")
        print(json.dumps(attrs, indent=6))
    else:
        print(f"    NO MATCH for MAP_PAR_ID='{target_id}' — looking for similar...")
        r2 = requests.get(
            l3_url,
            params={
                "where": "TOWN_ID=10 AND MAP_PAR_ID LIKE '128%'",
                "outFields": "MAP_PAR_ID,SITE_ADDR",
                "resultRecordCount": 5,
                "f": "json",
            },
            timeout=15,
        ).json()
        sims = r2.get("features", [])
        for s in sims:
            print(f"      sim: {s['attributes'].get('MAP_PAR_ID'):<25} {s['attributes'].get('SITE_ADDR')}")

    print("\n[Q2b] Compare MAP_PAR_ID format vs. existing parcel.parquet...")
    arl_path = REPO_ROOT / "data" / "gold" / "arlington-ma" / "parcel.parquet"
    if arl_path.exists():
        df = pd.read_parquet(arl_path)
        print(f"    existing parcel.parquet rows: {len(df):,}")
        print(f"    sample existing MAP_PAR_IDs (first 5):")
        for v in df["parcel_id"].head(5):
            print(f"      '{v}'")

        # Pull 5 from L3 for comparison.
        r = requests.get(
            l3_url,
            params={
                "where": "TOWN_ID=10",
                "outFields": "MAP_PAR_ID",
                "resultRecordCount": 5,
                "f": "json",
            },
            timeout=15,
        ).json()
        l3_sample = [f["attributes"]["MAP_PAR_ID"] for f in r.get("features", [])]
        print(f"    sample L3 MAP_PAR_IDs (first 5):")
        for v in l3_sample:
            print(f"      '{v}'")

        # Set intersection — how many of the existing IDs map cleanly into L3?
        existing_ids = set(df["parcel_id"].astype(str))
        # Pull a larger L3 sample to test overlap.
        r = requests.get(
            l3_url,
            params={
                "where": "TOWN_ID=10",
                "outFields": "MAP_PAR_ID",
                "resultRecordCount": 1000,
                "f": "json",
            },
            timeout=20,
        ).json()
        l3_ids = {f["attributes"]["MAP_PAR_ID"] for f in r.get("features", [])}
        overlap = existing_ids & l3_ids
        print(f"\n    Overlap test (1,000 L3 sample vs existing {len(existing_ids):,}):")
        print(f"      L3 IDs sampled    : {len(l3_ids):,}")
        print(f"      Overlapping       : {len(overlap):,}")
        print(f"      L3-only (no match): {len(l3_ids - existing_ids):,}")
        if overlap:
            print(f"      sample overlapping ID: '{next(iter(overlap))}'")
    else:
        print(f"    (no existing arlington parcel.parquet — first-time scrape)")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
