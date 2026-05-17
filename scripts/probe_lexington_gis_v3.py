# [FILE PATH]: scripts/probe_lexington_gis_v3.py
# Phase 5.0 finalize — confirm parcel + zoning + historic + env sources
# Date: 2026-05-07
"""
Final round of Lexington discovery.

Round 2 surfaced two real architectural issues:

  1. Lexington's AGOL org publishes 100+ Feature Services but NO town-wide
     parcel layer.  Arlington's "Parcels with CAMA" service is an
     Arlington-ism, not a generic MA pattern.
  2. The MassGIS hosted-service URLs we tried in round 2 were stale.

This round nails down four concrete answers:

  [A] **Correct MassGIS L3 Parcels endpoint.**  Search ArcGIS Online for
      MassGIS-published parcel services and try every candidate.  L3
      Parcels is a single statewide FeatureServer with TOWN_ID-based
      filtering — that's our parcel source for any MA town that doesn't
      self-publish.

  [B] **AGOL pagination beyond 100.**  Re-search Lexington's org with a
      ``start=100`` cursor to collect the second page.

  [C] **MBTA_MULTIFAMILY_ZONING_editing schema.**  Inspect the layer's
      attribute names (we'll need them to populate
      configs/lexington-ma/config.yaml zoning_overlay block).

  [D] **HistoricPropertySurveyView + HistoricPropInventoryView2 schemas.**
      Same as [C] but for local-historic.  Confirms whether the same
      generic field-name candidates from Arlington's local_historic
      block transfer (mhcn / historic_name / common_name / etc.).
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

OUT_PATH = REPO_ROOT / "data" / "lexington-ma_probe_v3.json"

LEXINGTON_AGOL_ORG = "bP0owepHkr9WxF4V"
LEX_BBOX = "-71.27,42.41,-71.18,42.48"


def _try_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 12) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, params=params or {"f": "json"}, timeout=timeout)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return {"_raw": r.text[:300]}
        return {"_status": r.status_code, "_text": r.text[:200]}
    except Exception as exc:
        return {"_error": type(exc).__name__, "_msg": str(exc)[:200]}


def find_massgis_parcels() -> Dict[str, Any]:
    """Search AGOL for MassGIS-owned parcel services."""
    print("\n[A] MassGIS L3 Parcels — finding the correct URL")

    # MassGIS publishes through several AGOL orgs; the simplest path is
    # an AGOL search for owner='MassGIS' or org='MassGIS_GIS' with
    # type='Feature Service' and 'parcel' in the title.
    candidates: List[Dict[str, Any]] = []
    for q in [
        'owner:MassGIS AND title:"L3 Parcels" AND type:"Feature Service"',
        'owner:massgis AND title:parcel AND type:"Feature Service"',
        'title:"MassGIS L3 Parcels" AND type:"Feature Service"',
        'title:"L3 Parcels Geocodable" AND type:"Feature Service"',
        'tags:parcel AND owner:massgis',
    ]:
        res = _try_get(
            "https://www.arcgis.com/sharing/rest/search",
            params={"q": q, "f": "json", "num": 25},
        )
        if not res or "results" not in res:
            continue
        for r in res["results"]:
            url = r.get("url") or ""
            if "parcel" in url.lower() or "parcel" in (r.get("title") or "").lower():
                candidates.append({
                    "title": r.get("title"),
                    "owner": r.get("owner"),
                    "url": url,
                    "id": r.get("id"),
                })

    # de-dup
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for c in candidates:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        deduped.append(c)

    print(f"    {len(deduped)} candidate parcel services found")
    confirmed: List[Dict[str, Any]] = []
    for c in deduped:
        meta = _try_get(c["url"])
        if not meta or "layers" not in meta:
            print(f"      x {c['title']}  ({c['url']}) — not reachable")
            continue
        layers = meta.get("layers") or []
        c["layers"] = [{"id": l.get("id"), "name": l.get("name"), "type": l.get("type")} for l in layers]
        # Try TOWN_ID filter for Lexington (TOWN_ID=155 is Lexington in MassGIS).
        for l in c["layers"]:
            if l["type"] != "Feature Layer":
                continue
            qurl = f"{c['url']}/{l['id']}/query"
            for filt in ("TOWN_ID=155", "TOWN_ID='155'", "MUNICIPAL_='LEXINGTON'", "TOWN_NAME='LEXINGTON'"):
                cnt = _try_get(qurl, params={"where": filt, "returnCountOnly": "true", "f": "json"})
                v = (cnt or {}).get("count") if isinstance(cnt, dict) else None
                if v is not None:
                    print(f"      OK {c['title']}  layer {l['id']} '{filt}' -> {v} parcels")
                    if v > 0:
                        c.setdefault("matches", []).append({"layer": l["id"], "filter": filt, "count": v})
                        break
            if c.get("matches"):
                break
        if c.get("matches"):
            confirmed.append(c)

    print(f"\n    {len(confirmed)} services have Lexington parcels reachable.")
    return {"candidates": deduped, "confirmed": confirmed}


def paginate_lexington_agol() -> List[Dict[str, Any]]:
    """Get pages 2+ of Lexington's AGOL org content."""
    print("\n[B] Lexington AGOL org — pagination beyond first 100")
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for start in (100, 200, 300):
        res = _try_get(
            "https://www.arcgis.com/sharing/rest/search",
            params={
                "q": f'orgid:{LEXINGTON_AGOL_ORG} type:"Feature Service"',
                "f": "json",
                "num": 100,
                "start": start,
            },
        )
        if not res or "results" not in res:
            break
        results = res.get("results") or []
        if not results:
            break
        new = 0
        for r in results:
            if r.get("id") in seen:
                continue
            seen.add(r["id"])
            out.append({
                "title": r.get("title"),
                "owner": r.get("owner"),
                "url": r.get("url"),
                "tags": r.get("tags") or [],
            })
            new += 1
        print(f"    start={start}: +{new} new services (total now {len(out)})")
        if len(results) < 100:
            break

    # Filter for the categories we care about
    keywords = {
        "zoning":   ["zoning", "district", "overlay", "MBTA"],
        "parcel":   ["parcel", "cama", "CAMA"],
        "historic": ["historic", "burial", "monument"],
        "wetland":  ["wetland", "flood", "vernal", "pond", "stream", "brook", "hydro"],
    }
    print("\n    Lexington AGOL services matching Tier-2 keywords:")
    for cat, kws in keywords.items():
        matches = [s for s in out if any(k.lower() in (s["title"] or "").lower() for k in kws)]
        for m in matches:
            print(f"      [{cat}] {m['title']:<48s}  {m['url']}")
    return out


def inspect_layer(name: str, url: str) -> Dict[str, Any]:
    """Pull layer metadata + a single feature to see attribute names."""
    print(f"\n[C/D] Inspecting {name}")
    print(f"    {url}")
    meta = _try_get(url)
    if not meta or "layers" not in meta:
        # Maybe url already includes /<layerId>
        meta = _try_get(url)
    out: Dict[str, Any] = {"name": name, "url": url, "layers": []}
    if not meta or ("layers" not in meta and "fields" not in meta):
        print("    x not reachable / no metadata")
        return out

    if "layers" in meta:
        for l in meta.get("layers", []):
            sub_url = f"{url}/{l.get('id')}"
            sub_meta = _try_get(sub_url)
            fields = [f.get("name") for f in (sub_meta or {}).get("fields", [])]
            print(f"    layer {l.get('id')} ({l.get('type')}, {l.get('name')}): {len(fields)} fields")
            print(f"      fields: {fields[:18]}{'...' if len(fields) > 18 else ''}")
            out["layers"].append({
                "id": l.get("id"),
                "name": l.get("name"),
                "type": l.get("type"),
                "fields": fields,
            })
    elif "fields" in meta:
        fields = [f.get("name") for f in meta.get("fields", [])]
        print(f"    direct layer: {len(fields)} fields")
        print(f"      fields: {fields[:18]}{'...' if len(fields) > 18 else ''}")
        out["layers"].append({"id": meta.get("id"), "fields": fields})
    return out


def main() -> int:
    print("=" * 78)
    print("  Phase 5.0 round 3 — finalize Lexington discovery")
    print("=" * 78)
    findings: Dict[str, Any] = {
        "town_slug": "lexington-ma",
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    findings["massgis_parcels"] = find_massgis_parcels()
    findings["agol_pages_2plus"] = paginate_lexington_agol()

    # Inspect specific layers we already know about (from round 2 results).
    findings["mbta_zoning"] = inspect_layer(
        "MBTA_MULTIFAMILY_ZONING_editing",
        "https://services.arcgis.com/bP0owepHkr9WxF4V/arcgis/rest/services/"
        "MBTA_MULTIFAMILY_ZONING_editing/FeatureServer",
    )
    findings["historic_survey"] = inspect_layer(
        "HistoricPropertySurveyView",
        "https://services.arcgis.com/bP0owepHkr9WxF4V/arcgis/rest/services/"
        "HistoricPropertySurveyView/FeatureServer",
    )
    findings["historic_inventory"] = inspect_layer(
        "HistoricPropInventoryView2",
        "https://services.arcgis.com/bP0owepHkr9WxF4V/arcgis/rest/services/"
        "HistoricPropInventoryView2/FeatureServer",
    )
    findings["wetlands"] = inspect_layer(
        "Pine_Meadows_Wetlands",
        "https://services.arcgis.com/bP0owepHkr9WxF4V/arcgis/rest/services/"
        "Pine_Meadows_Wetlands/FeatureServer",
    )

    OUT_PATH.write_text(json.dumps(findings, indent=2))
    print(f"\n  Saved -> {OUT_PATH.relative_to(REPO_ROOT)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
