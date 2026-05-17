# [FILE PATH]: scripts/probe_massgis_l3_schema.py
# Phase 5.1 prep — inspect MassGIS L3 Parcels schema for Lexington
# Date: 2026-05-07
"""
Quick one-shot: print the MassGIS Massachusetts_Property_Tax_Parcels
layer 0 field list and one Lexington feature so we can populate the
id_field_candidates and address_field_candidates in
configs/lexington-ma/config.yaml's parcels: block.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    url = (
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
        "Massachusetts_Property_Tax_Parcels/FeatureServer/0"
    )
    print(f"Inspecting {url}")

    meta = requests.get(url, params={"f": "json"}, timeout=15).json()
    print(f"\nLayer 0 fields ({len(meta.get('fields', []))}):")
    for f in meta.get("fields", []):
        print(f"  {f['name']:<22} {f.get('type', ''):<22}  {f.get('alias', '')}")

    print("\nOne Lexington (TOWN_ID=155) feature:")
    r2 = requests.get(
        url + "/query",
        params={
            "where": "TOWN_ID=155",
            "outFields": "*",
            "resultRecordCount": 1,
            "f": "json",
        },
        timeout=15,
    ).json()
    feats = r2.get("features", [])
    if feats:
        print(json.dumps(feats[0].get("attributes", {}), indent=2)[:3000])
    else:
        print("  (no features returned)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
