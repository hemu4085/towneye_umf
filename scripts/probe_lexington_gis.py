# [FILE PATH]: scripts/probe_lexington_gis.py
# Phase 5.0 — discover Lexington-MA's GIS endpoints
# Date: 2026-05-07
"""
Discovery probe for Lexington-MA Tier 2 onboarding.

For each Arlington Tier 2 domain we ask the same question for Lexington:

  parcel              -> Where is Lexington's "Parcels with CAMA" FeatureServer?
  zoning_overlay      -> Where is Lexington's zoning + overlay districts service?
  noncompliance       -> Does Lexington publish a LandUse_NonCompliance layer?
  local_historic      -> Does Lexington publish local-historic district polygons?
  environmental_overlay -> Does Lexington publish wetlands + flood-zone services?
  macris              -> Does the statewide MACRIS layer carry Lexington records?

Strategy
--------
1. Try the most-likely ArcGIS Server paths first
   (https://gis.lexingtonma.gov/server/rest/services).
2. Search the Massachusetts MassGIS / MAPC ArcGIS Online org for
   "Lexington" services.
3. Probe the statewide MACRIS layer for TOWN_NAME='Lexington'.
4. Probe the FEMA NFHL with Lexington's bbox.

Print a concise findings table and optionally save the probe result to
``data/lexington-ma_probe.json`` so we can use it as the source of
truth when extending ``configs/lexington-ma/config.yaml``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

OUT_PATH = REPO_ROOT / "data" / "lexington-ma_probe.json"


# Patterns we'll try — ordered by likelihood for a typical Mass town.
CANDIDATE_ARCGIS_ROOTS: List[str] = [
    "https://gis.lexingtonma.gov/server/rest/services",
    "https://gis.lexingtonma.gov/arcgis/rest/services",
    # Lexington's town site sometimes proxies through a non-default port:
    "https://gis.lexingtonma.gov/portal/sharing/rest/portals/self",
]

# MassGIS hosts statewide layers any town can use.  These are last-resort
# fallbacks if a town doesn't publish its own services.
MASS_FALLBACKS: Dict[str, str] = {
    "macris_statewide": (
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
        "MHC_Inventory_GDB/FeatureServer"
    ),
    "fema_nfhl": (
        "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
    ),
}

# Lexington bounding box — pulled from existing config.yaml line 177.
LEXINGTON_BBOX = "-71.27,42.41,-71.18,42.48"

# ArcGIS Online search for Lexington-related FeatureServers.  This is a
# generic search — many MA towns publish through ArcGIS Online without
# self-hosting a server.
AGOL_SEARCH = (
    "https://www.arcgis.com/sharing/rest/search"
    "?q=lexington%20massachusetts%20(parcel%20OR%20zoning%20OR%20historic%20OR%20wetland%20OR%20flood)"
    "%20type%3A%22Feature%20Service%22"
    "&f=json&num=50"
)


def _try_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """GET and parse JSON, returning None on any failure."""
    try:
        r = requests.get(url, params=params or {"f": "json"}, timeout=timeout)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return {"_raw": r.text[:400]}
        return {"_status": r.status_code, "_text": r.text[:200]}
    except Exception as exc:
        return {"_error": type(exc).__name__, "_msg": str(exc)[:200]}


def probe_arcgis_root(root: str) -> Dict[str, Any]:
    print(f"  -> {root}")
    res = _try_get(root, params={"f": "json"})
    if not res or "_error" in res or "_status" in res:
        return {"reachable": False, "detail": res}
    folders = res.get("folders") or []
    services = res.get("services") or []
    print(f"     reachable: {len(folders)} folders, {len(services)} services at root")
    return {
        "reachable": True,
        "folders": folders,
        "services": [{"name": s.get("name"), "type": s.get("type")} for s in services],
    }


def search_agol_for_lexington() -> List[Dict[str, Any]]:
    print(f"  -> ArcGIS Online search")
    res = _try_get(AGOL_SEARCH, params=None)
    if not res or "results" not in res:
        return []
    hits = []
    for r in res.get("results", []):
        title = (r.get("title") or "").lower()
        owner = (r.get("owner") or "").lower()
        if "lexington" not in title and "lexington" not in owner:
            continue
        hits.append({
            "title": r.get("title"),
            "owner": r.get("owner"),
            "url": r.get("url"),
            "id": r.get("id"),
            "tags": r.get("tags") or [],
        })
    print(f"     {len(hits)} Lexington-related Feature Services found")
    return hits


def probe_macris_for_lexington() -> Dict[str, Any]:
    """Hit the MACRIS layer 0 with TOWN_NAME='Lexington' filter."""
    print(f"  -> MACRIS statewide (TOWN_NAME='Lexington')")
    base = MASS_FALLBACKS["macris_statewide"]
    out: Dict[str, Any] = {"feature_server": base, "layers_checked": []}
    for layer_id in (0, 1, 3, 4, 5):
        url = f"{base}/{layer_id}/query"
        params = {
            "where": "TOWN_NAME='LEXINGTON'",
            "returnCountOnly": "true",
            "f": "json",
        }
        res = _try_get(url, params=params)
        cnt = (res or {}).get("count") if isinstance(res, dict) else None
        out["layers_checked"].append({"layer": layer_id, "count": cnt, "raw": res if cnt is None else None})
        print(f"       layer {layer_id}: {cnt if cnt is not None else 'no-count'}")
    return out


def probe_fema_for_lexington() -> Dict[str, Any]:
    """Spatial query against FEMA NFHL layer 28 (S_FLD_HAZ_AR) using Lexington's bbox."""
    print(f"  -> FEMA NFHL (Lexington bbox)")
    params = {
        "where": "1=1",
        "geometry": LEXINGTON_BBOX,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,SFHA_TF,ZONE_SUBTY",
        "returnCountOnly": "true",
        "f": "json",
    }
    res = _try_get(MASS_FALLBACKS["fema_nfhl"], params=params)
    cnt = (res or {}).get("count") if isinstance(res, dict) else None
    print(f"       intersecting flood polygons: {cnt}")
    return {"layer_url": MASS_FALLBACKS["fema_nfhl"], "intersecting_count": cnt, "raw": res if cnt is None else None}


def probe_mapgeo_pattern() -> Dict[str, Any]:
    """Many MA towns expose data through MapGeo at <town>.mapgeo.io with
    an embedded ArcGIS service.  Cheap to check."""
    print(f"  -> MapGeo pattern")
    candidates = [
        "https://lexingtonma.mapgeo.io/",
        "https://lexington.mapgeo.io/",
    ]
    found = []
    for c in candidates:
        try:
            r = requests.head(c, timeout=8, allow_redirects=True)
            print(f"       {c} -> HTTP {r.status_code}")
            if r.status_code < 400:
                found.append({"url": c, "status": r.status_code})
        except Exception as exc:
            print(f"       {c} -> {type(exc).__name__}")
    return {"hits": found}


def main() -> int:
    print("=" * 78)
    print("  Phase 5.0 — Lexington-MA GIS Discovery Probe")
    print("=" * 78)

    findings: Dict[str, Any] = {
        "town_slug": "lexington-ma",
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "arcgis_roots": [],
        "agol_hits": [],
        "macris": None,
        "fema": None,
        "mapgeo": None,
    }

    print("\n[1] Self-hosted ArcGIS Server roots")
    for root in CANDIDATE_ARCGIS_ROOTS:
        findings["arcgis_roots"].append({"root": root, **probe_arcgis_root(root)})

    print("\n[2] ArcGIS Online search for Lexington services")
    findings["agol_hits"] = search_agol_for_lexington()

    print("\n[3] MACRIS statewide — Lexington records")
    findings["macris"] = probe_macris_for_lexington()

    print("\n[4] FEMA NFHL — Lexington bbox")
    findings["fema"] = probe_fema_for_lexington()

    print("\n[5] MapGeo pattern (lots of MA towns use this)")
    findings["mapgeo"] = probe_mapgeo_pattern()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(findings, indent=2))
    print(f"\n  Saved full probe -> {OUT_PATH.relative_to(REPO_ROOT)}")
    print("=" * 78)

    # Summary
    print("\n  --- Findings summary ---")
    reachable_roots = [r for r in findings["arcgis_roots"] if r.get("reachable")]
    print(f"    self-hosted ArcGIS roots reachable: {len(reachable_roots)}")
    print(f"    AGOL Lexington services found      : {len(findings['agol_hits'])}")
    macris_layers = findings["macris"]["layers_checked"] if findings["macris"] else []
    macris_total = sum((l.get("count") or 0) for l in macris_layers)
    print(f"    MACRIS Lexington records (all layers): {macris_total}")
    fema_count = (findings["fema"] or {}).get("intersecting_count")
    print(f"    FEMA flood polygons intersecting bbox: {fema_count}")
    mapgeo_hits = (findings["mapgeo"] or {}).get("hits", [])
    print(f"    MapGeo: {len(mapgeo_hits)} reachable")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
