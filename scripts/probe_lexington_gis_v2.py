# [FILE PATH]: scripts/probe_lexington_gis_v2.py
# Phase 5.0 follow-up — find Lexington's actual data sources
# Date: 2026-05-07
"""
Round 2 of Lexington GIS discovery.

Round 1 surfaced that Lexington:
  - Has no self-hosted GIS server (DNS for gis.lexingtonma.gov fails).
  - Hosts town boundary on AGOL org ``bP0owepHkr9WxF4V`` but the public
    AGOL search did not surface parcels / zoning / historic / wetland.
  - Uses MapGeo at lexingtonma.mapgeo.io as its public-facing portal.

Round 2 looks at three concrete fallback paths:

  [A] **Lexington's AGOL org directory** — list every Feature Service the
      ``bP0owepHkr9WxF4V`` org publishes.  Some are unindexed / not
      public-search-visible but reachable directly.

  [B] **MassGIS L3 Parcels statewide layer** — guaranteed source of
      record for every MA town's parcel polygons + assessor key
      attributes.  Filter by TOWN_ID or TOWN_NAME.

  [C] **MapGeo dataset metadata** — MapGeo configs typically expose a
      list of underlying datasets via ``/api/sites/<slug>``.  If we can
      enumerate Lexington's MapGeo layers we can map them back to
      ArcGIS service URLs.

Output is appended to ``data/lexington-ma_probe_v2.json``.
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

OUT_PATH = REPO_ROOT / "data" / "lexington-ma_probe_v2.json"

LEXINGTON_AGOL_ORG = "bP0owepHkr9WxF4V"

MASSGIS_L3_PARCELS = (
    "https://gis.massgis.digital.mass.gov/arcgis/rest/services/AGOL/L3_Parcels/FeatureServer"
)
MASSGIS_L3_PARCELS_ALT = (
    "https://gis.massgis.digital.mass.gov/server/rest/services/AGOL/L3_Parcels/FeatureServer"
)

# Other MassGIS statewide layers that often substitute for town-specific ones.
MASSGIS_STATEWIDE = {
    "wetlands_dep": (
        "https://gis.massgis.digital.mass.gov/arcgis/rest/services/AGOL/DEPWetlands/FeatureServer"
    ),
    "zoning_atlas": (
        "https://services1.arcgis.com/aqgFXNVm2EdAtsSt/arcgis/rest/services/MA_Zoning_Atlas/FeatureServer"
    ),
    "historic_districts_state": (
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Historic_Districts/FeatureServer"
    ),
}

# MapGeo public site config endpoint shape.
MAPGEO_BASE = "https://lexingtonma.mapgeo.io"


def _try_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 12) -> Optional[Dict[str, Any]]:
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


def list_agol_org_content() -> List[Dict[str, Any]]:
    """List every Feature Service published by the Lexington AGOL org."""
    print(f"\n[A] AGOL org directory ({LEXINGTON_AGOL_ORG}) — Feature Services")
    # Two strategies:  AGOL content search by orgid, then per-page browse.
    out: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for orgid_arg in ("orgid", "orgId"):
        url = "https://www.arcgis.com/sharing/rest/search"
        params = {
            "q": f'{orgid_arg}:{LEXINGTON_AGOL_ORG} type:"Feature Service"',
            "f": "json",
            "num": 100,
        }
        res = _try_get(url, params=params)
        if not res or "results" not in res:
            continue
        for r in res.get("results", []):
            if r.get("id") in seen_ids:
                continue
            seen_ids.add(r["id"])
            out.append({
                "title": r.get("title"),
                "owner": r.get("owner"),
                "url": r.get("url"),
                "id": r.get("id"),
                "tags": r.get("tags") or [],
                "type": r.get("type"),
            })

    # Also try the org's hosted FeatureServer namespace directly — every AGOL
    # org publishes services under ``services.arcgis.com/<orgid>/...``.
    print(f"    {len(out)} feature services found in org content")
    for r in out:
        print(f"      - {r['title']:<55s}  ({r['id'][:8]}…)")
    return out


def probe_massgis_l3() -> Dict[str, Any]:
    """Filter MassGIS L3 Parcels by TOWN_ID for Lexington."""
    print(f"\n[B] MassGIS L3 Parcels statewide — TOWN_ID='Lexington'")
    out: Dict[str, Any] = {}
    for label, root in [("primary", MASSGIS_L3_PARCELS), ("alt", MASSGIS_L3_PARCELS_ALT)]:
        meta = _try_get(root)
        out[label] = {"root": root, "reachable": bool(meta and "layers" in meta)}
        if meta and "layers" in meta:
            layers = [{"id": l.get("id"), "name": l.get("name"), "type": l.get("type")} for l in meta.get("layers", [])]
            out[label]["layers"] = layers
            print(f"    {root}")
            for l in layers[:6]:
                print(f"      layer {l['id']:<3} {l['type']:<14}  {l['name']}")
            # Try a Lexington filter on the first polygon layer.
            for l in layers:
                if l["type"] == "Feature Layer":
                    qurl = f"{root}/{l['id']}/query"
                    for filt in (
                        "TOWN_NAME='LEXINGTON'",
                        "TOWN='LEXINGTON'",
                        "TOWN_ID=155",
                        "TOWN_ID='155'",
                        "MUNICIPAL_='LEXINGTON'",
                        "TOWN_ID='LEXINGTON'",
                    ):
                        cnt = _try_get(qurl, params={"where": filt, "returnCountOnly": "true", "f": "json"})
                        c = (cnt or {}).get("count") if isinstance(cnt, dict) else None
                        if c is not None:
                            print(f"      layer {l['id']} filter '{filt[:30]}' -> {c} parcels")
                            if c > 0:
                                out[label].setdefault("matches", []).append({"layer": l["id"], "filter": filt, "count": c})
                                break
                    break
    return out


def probe_massgis_extras() -> Dict[str, Any]:
    """Wetlands + statewide zoning + historic — try Lexington spatial filter."""
    print(f"\n[C] Other MassGIS statewide layers")
    out: Dict[str, Any] = {}
    bbox = "-71.27,42.41,-71.18,42.48"
    for label, root in MASSGIS_STATEWIDE.items():
        meta = _try_get(root)
        info: Dict[str, Any] = {"root": root, "reachable": bool(meta and "layers" in meta)}
        if meta and "layers" in meta:
            for l in (meta.get("layers") or [])[:1]:  # just probe layer 0
                qurl = f"{root}/{l.get('id')}/query"
                cnt = _try_get(qurl, params={
                    "where": "1=1",
                    "geometry": bbox,
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "returnCountOnly": "true",
                    "f": "json",
                })
                c = (cnt or {}).get("count") if isinstance(cnt, dict) else None
                info["layer_0"] = {"id": l.get("id"), "name": l.get("name"), "intersects_count": c}
                print(f"    {label:<24} layer 0 ({l.get('name')}): {c} polygons in bbox")
        else:
            print(f"    {label:<24} unreachable")
        out[label] = info
    return out


def probe_mapgeo() -> Dict[str, Any]:
    """Try a few MapGeo configuration endpoints."""
    print(f"\n[D] MapGeo dataset metadata for {MAPGEO_BASE}")
    out: Dict[str, Any] = {}
    candidates = [
        f"{MAPGEO_BASE}/api/sites/lexingtonma",
        f"{MAPGEO_BASE}/api/site",
        f"{MAPGEO_BASE}/site/config.json",
        f"{MAPGEO_BASE}/api/v1/sites/lexingtonma",
    ]
    for c in candidates:
        res = _try_get(c, params=None)
        ok = isinstance(res, dict) and "_status" not in res and "_error" not in res
        print(f"    {c} -> {'JSON ok' if ok else (res or {}).get('_status') or (res or {}).get('_error')}")
        if ok:
            datasets = []
            if isinstance(res.get("datasets"), list):
                datasets = res["datasets"]
            elif isinstance(res.get("layers"), list):
                datasets = res["layers"]
            if datasets:
                print(f"      -> {len(datasets)} datasets/layers exposed")
            out[c] = {
                "ok": True,
                "datasets_count": len(datasets) if datasets else 0,
                "snippet": json.dumps(res)[:600],
            }
        else:
            out[c] = {"ok": False, "detail": res}
    return out


def main() -> int:
    print("=" * 78)
    print("  Phase 5.0 round 2 — Lexington data-source discovery")
    print("=" * 78)
    findings: Dict[str, Any] = {
        "town_slug": "lexington-ma",
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    findings["agol_org_content"] = list_agol_org_content()
    findings["massgis_l3_parcels"] = probe_massgis_l3()
    findings["massgis_extras"] = probe_massgis_extras()
    findings["mapgeo"] = probe_mapgeo()

    OUT_PATH.write_text(json.dumps(findings, indent=2))
    print(f"\n  Saved -> {OUT_PATH.relative_to(REPO_ROOT)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
