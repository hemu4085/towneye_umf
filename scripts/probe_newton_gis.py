# [FILE PATH]: scripts/probe_newton_gis.py
# Discovery for Newton MA Tier 2 — L3 TOWN_ID, AGOL zoning/historic URLs.
"""Print MassGIS L3 counts for Newton and ArcGIS Online Feature Service hits."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

L3_QUERY = (
    "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
    "Massachusetts_Property_Tax_Parcels/FeatureServer/0/query"
)


def get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 45) -> Any:
    r = requests.get(url, params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def main() -> int:
    print("=== MassGIS L3 Newton (TOWN_ID=207) ===")
    j = get_json(L3_QUERY, {"where": "TOWN_ID=207", "returnCountOnly": "true", "f": "json"})
    print(f"  TOWN_ID=207 -> count={j.get('count')!r}")

    print("\n=== AGOL search: Newton MA Feature Services (first 25) ===")
    q = (
        'owner:newtonma OR title:(Newton Massachusetts) OR title:(Newton MA) '
        'type:"Feature Service"'
    )
    search_url = "https://www.arcgis.com/sharing/rest/search"
    try:
        j_ag = get_json(search_url, {"q": q, "f": "json", "num": 25}, timeout=30)
        for r in j_ag.get("results", [])[:25]:
            print(f"  - {r.get('title')}\n      {r.get('url')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (AGOL search failed: {exc})")

    print("\n=== Broader AGOL search: Newton zoning ===")
    try:
        j2 = get_json(
            search_url,
            {
                "q": 'Newton Massachusetts zoning type:"Feature Service"',
                "f": "json",
                "num": 15,
            },
            timeout=30,
        )
        for r in j2.get("results", [])[:15]:
            print(f"  - {r.get('title')}\n      {r.get('url')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (AGOL zoning search failed: {exc})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
