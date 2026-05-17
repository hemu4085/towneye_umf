"""Run all queries for 29 Walnut St, Arlington MA. Resilient to per-query failures.

All queries pivot to Arlington's own ArcGIS host (services2.arcgis.com) since
MassGIS hostname does not resolve. Each query writes its own JSON to
data/29_walnut/ so partial failures never lose successful results.
"""
import json
import math
import pathlib
import sys
import traceback

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(InsecureRequestWarning)

ADDRESS = "29 Walnut St"
CITY    = "Arlington"
STATE   = "MA"
ZIP     = "02476"  # confirmed by prior geocode

OUT = pathlib.Path("data/29_walnut")
OUT.mkdir(parents=True, exist_ok=True)

ARLINGTON_AGOL_HOST = (
    "https://services2.arcgis.com/s1Sh73K7qtP9JdrG/arcgis/rest/services"
)


# ── infra helpers ─────────────────────────────────────────────────────
def save(name, obj):
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, indent=2, default=str))
    print(f"  → saved {p} ({p.stat().st_size:,} bytes)")


def step(name, fn):
    print(f"\n=== {name.upper()} ===")
    try:
        result = fn()
        save(name, result)
        return result
    except Exception as exc:
        print(f"  ✗ FAILED: {exc}")
        save(name, {"error": str(exc), "traceback": traceback.format_exc()})
        return None


def _haversine_ft(p1, p2):
    R = 6371000
    lat1, lon1 = math.radians(p1[1]), math.radians(p1[0])
    lat2, lon2 = math.radians(p2[1]), math.radians(p2[0])
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a)) * 3.28084


# ── Q1 GEOCODE ────────────────────────────────────────────────────────
def geocode():
    r = requests.get(
        "https://geocoding.geo.census.gov/geocoder/locations/address",
        params={"street": ADDRESS, "city": CITY, "state": STATE,
                "zip": ZIP, "benchmark": "2020", "format": "json"},
        timeout=10)
    m = r.json().get("result", {}).get("addressMatches", [])
    if not m:
        raise RuntimeError("Geocode returned no matches")
    c = m[0]["coordinates"]
    return {"matched": m[0]["matchedAddress"],
            "lat": float(c["y"]), "lon": float(c["x"]),
            "tigerLine": m[0].get("tigerLine", {})}


# ── Q2 ASSESSOR (Patriot Properties) ──────────────────────────────────
def assessor():
    r = requests.get(
        "https://arlington.patriotproperties.com/SearchResults.asp",
        params={"SearchStreetNumber": "29", "SearchStreetName": "Walnut",
                "SearchOwner": ""},
        headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=20)
    (OUT / "assessor.html").write_text(r.text)
    parsed = None
    try:
        sys.path.insert(0, ".")
        from scrapers.property_scraper import ArlingtonPropertyScraper
        scraper = ArlingtonPropertyScraper("arlington-ma")
        recs = scraper.parse_records(r.text)
        parsed = [x for x in recs
                  if (x.get("location") or x.get("address") or "")
                     .upper().startswith("29 ")]
    except Exception as exc:
        parsed = {"parse_error": str(exc)}
    return {"status": r.status_code, "len": len(r.text),
            "saved_html": str(OUT / "assessor.html"),
            "parsed_29_records": parsed}


# ── Q3 ARLINGTON ARCGIS SERVICE INVENTORY ─────────────────────────────
def arcgis_inventory():
    r = requests.get(f"{ARLINGTON_AGOL_HOST}?f=json", timeout=15)
    data = r.json()
    services = []
    for s in data.get("services", []):
        services.append({"name": s.get("name"), "type": s.get("type"),
                         "url": f"{ARLINGTON_AGOL_HOST}/{s.get('name')}/{s.get('type')}"})
    folders = data.get("folders", [])
    for folder in folders:
        try:
            fr = requests.get(f"{ARLINGTON_AGOL_HOST}/{folder}?f=json",
                              timeout=15).json()
            for s in fr.get("services", []):
                services.append({"name": s.get("name"), "type": s.get("type"),
                                 "url": f"{ARLINGTON_AGOL_HOST}/{s.get('name')}/{s.get('type')}",
                                 "folder": folder})
        except Exception as exc:
            services.append({"folder": folder, "error": str(exc)})
    return {"folders": folders, "services": services}


# ── Q4 ZONING + OVERLAY (ALL features, ALL layers) ────────────────────
def zoning(lat, lon):
    base = f"{ARLINGTON_AGOL_HOST}/Zoning_and_Overlay_Districts/FeatureServer"
    enum = requests.get(base, params={"f": "json"}, timeout=15).json()
    layers = [{"id": L["id"], "name": L["name"],
               "geometryType": L.get("geometryType")}
              for L in enum.get("layers", [])]
    out = {"layers": layers, "features_per_layer": {}}
    for L in layers:
        r = requests.get(f"{base}/{L['id']}/query",
            params={"f": "json",
                    "geometry": json.dumps({"x": lon, "y": lat,
                                            "spatialReference": {"wkid": 4326}}),
                    "geometryType": "esriGeometryPoint", "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "*", "returnGeometry": "false"},
            timeout=15).json()
        out["features_per_layer"][L["name"]] = [
            f.get("attributes", {}) for f in r.get("features", [])]
    return out


# ── Q5 PARCEL POLYGON via "Parcels with CAMA" ─────────────────────────
def parcel(lat, lon):
    base = f"{ARLINGTON_AGOL_HOST}/Parcels%20with%20CAMA/FeatureServer"
    enum = requests.get(base, params={"f": "json"}, timeout=15).json()
    layers = [{"id": L["id"], "name": L["name"],
               "geometryType": L.get("geometryType")}
              for L in enum.get("layers", [])]
    out = {"layers": layers, "polygon_features": []}
    for L in layers:
        if L.get("geometryType") != "esriGeometryPolygon":
            continue
        r = requests.get(f"{base}/{L['id']}/query",
            params={"f": "geojson",
                    "geometry": json.dumps({"x": lon, "y": lat,
                                            "spatialReference": {"wkid": 4326}}),
                    "geometryType": "esriGeometryPoint", "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "*", "returnGeometry": "true"},
            timeout=15)
        gj = r.json()
        if not gj.get("features"):
            continue
        (OUT / f"parcel_layer{L['id']}.geojson").write_text(json.dumps(gj, indent=2))
        for feat in gj["features"]:
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if not coords:
                continue
            ring = coords[0]
            if isinstance(ring[0][0], list):  # MultiPolygon
                ring = ring[0]
            edges_ft = [round(_haversine_ft(ring[i], ring[i + 1]), 1)
                        for i in range(len(ring) - 1)]
            out["polygon_features"].append({
                "layer_id": L["id"],
                "properties": feat.get("properties", {}),
                "edges_ft": edges_ft,
                "perimeter_ft": round(sum(edges_ft), 1),
                "longest_edge_ft": max(edges_ft) if edges_ft else None,
            })
    if not out["polygon_features"]:
        raise RuntimeError("No polygon features at point in 'Parcels with CAMA'")
    return out


# ── Q6 FEMA NFHL ──────────────────────────────────────────────────────
def fema(lat, lon):
    r = requests.get(
        "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query",
        params={"f": "json", "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint", "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "FLD_ZONE,SFHA_TF,ZONE_SUBTY,DFIRM_ID",
                "returnGeometry": "false"},
        timeout=15).json()
    return [f.get("attributes", {}) for f in r.get("features", [])]


# ── Q7 MACRIS POLYGON + POINT ─────────────────────────────────────────
def macris(lat, lon):
    out = {"polygon": [], "point": []}
    fields = ("MHCN,DESIGNATIO,LEGEND,HISTORIC_N,COMMON_NAM,ADDRESS,"
              "CONSTRUCTI,ARCH,ARCHITECTU,USE_TYPE,SIGNIFICAN")
    base = ("https://gis.bostonplans.org/hosting/rest/services/"
            "MHC_Historic_Inventory/MapServer")
    for layer, key, extra in [(2, "polygon", {}),
                              (1, "point", {"distance": "30",
                                            "units": "esriSRUnit_Meter"})]:
        params = {"f": "json", "geometry": f"{lon},{lat}",
                  "geometryType": "esriGeometryPoint", "inSR": "4326",
                  "spatialRel": "esriSpatialRelIntersects",
                  "outFields": fields, "returnGeometry": "false", **extra}
        r = requests.get(f"{base}/{layer}/query", params=params, timeout=15).json()
        out[key] = [f.get("attributes", {}) for f in r.get("features", [])]
    return out


# ── Q8 LAND USE NON-COMPLIANCE (open zoning violations) ───────────────
def noncompliance(lat, lon):
    base = f"{ARLINGTON_AGOL_HOST}/LandUse_NonCompliance/FeatureServer"
    enum = requests.get(base, params={"f": "json"}, timeout=15).json()
    out = {}
    for L in enum.get("layers", []):
        r = requests.get(f"{base}/{L['id']}/query",
            params={"f": "json",
                    "geometry": json.dumps({"x": lon, "y": lat,
                                            "spatialReference": {"wkid": 4326}}),
                    "geometryType": "esriGeometryPoint", "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "*", "returnGeometry": "false"},
            timeout=15).json()
        out[L["name"]] = [f.get("attributes", {}) for f in r.get("features", [])]
    return out


# ── Q9 WETLANDS / FLOOD CROSS-CHECK ───────────────────────────────────
def env_overlays(lat, lon):
    services = ["ArlingtonMA_Wetlands", "Arlington_Flood_Zones",
                "Flood_Zones_Preliminary_Changes_2023"]
    out = {}
    for svc in services:
        try:
            base = f"{ARLINGTON_AGOL_HOST}/{svc}/FeatureServer"
            enum = requests.get(base, params={"f": "json"}, timeout=10).json()
            for L in enum.get("layers", []):
                r = requests.get(f"{base}/{L['id']}/query",
                    params={"f": "json",
                            "geometry": json.dumps({"x": lon, "y": lat,
                                                    "spatialReference": {"wkid": 4326}}),
                            "geometryType": "esriGeometryPoint", "inSR": "4326",
                            "spatialRel": "esriSpatialRelIntersects",
                            "outFields": "*", "returnGeometry": "false"},
                    timeout=10).json()
                out[f"{svc}.{L['name']}"] = [
                    f.get("attributes", {}) for f in r.get("features", [])]
        except Exception as exc:
            out[svc] = {"error": str(exc)}
    return out


# ── Q10 ARLINGTON LOCAL HISTORIC LAYERS (cross-check vs MACRIS) ───────
def arl_historic(lat, lon):
    services = ["Local_Historic_District", "National_Historic_District",
                "Historic_Overlay_Districts",
                "Historic_Commission_Inventory_view"]
    out = {}
    for svc in services:
        try:
            base = f"{ARLINGTON_AGOL_HOST}/{svc}/FeatureServer"
            enum = requests.get(base, params={"f": "json"}, timeout=10).json()
            for L in enum.get("layers", []):
                r = requests.get(f"{base}/{L['id']}/query",
                    params={"f": "json",
                            "geometry": json.dumps({"x": lon, "y": lat,
                                                    "spatialReference": {"wkid": 4326}}),
                            "geometryType": "esriGeometryPoint", "inSR": "4326",
                            "spatialRel": "esriSpatialRelIntersects",
                            "outFields": "*", "returnGeometry": "false"},
                    timeout=10).json()
                out[f"{svc}.{L['name']}"] = [
                    f.get("attributes", {}) for f in r.get("features", [])]
        except Exception as exc:
            out[svc] = {"error": str(exc)}
    return out


# ── Q11 PARCEL BY ID (authoritative — bypass the geocoder mismatch) ───
def parcel_by_id(parcel_id="128.0-0003-0012.0"):
    base = f"{ARLINGTON_AGOL_HOST}/Parcels%20with%20CAMA/FeatureServer/0/query"
    r = requests.get(base,
        params={"f": "geojson",
                "where": f"MAP_PAR_ID='{parcel_id}'",
                "outFields": "*", "returnGeometry": "true"},
        timeout=15)
    gj = r.json()
    if not gj.get("features"):
        r = requests.get(base,
            params={"f": "geojson",
                    "where": f"CAMA_ID='{parcel_id}'",
                    "outFields": "*", "returnGeometry": "true"},
            timeout=15)
        gj = r.json()
    if not gj.get("features"):
        raise RuntimeError(f"No parcel feature found for {parcel_id}")
    (OUT / "parcel_29.geojson").write_text(json.dumps(gj, indent=2))
    out = []
    for feat in gj["features"]:
        ring = feat["geometry"]["coordinates"][0]
        if isinstance(ring[0][0], list):
            ring = ring[0]
        edges_ft = [round(_haversine_ft(ring[i], ring[i + 1]), 1)
                    for i in range(len(ring) - 1)]
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        out.append({
            "properties": feat["properties"],
            "edges_ft": edges_ft,
            "perimeter_ft": round(sum(edges_ft), 1),
            "longest_edge_ft": max(edges_ft) if edges_ft else None,
            "centroid": {"lon": round(cx, 7), "lat": round(cy, 7)},
        })
    return out


# ── DRIVER ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    g = step("geocode", geocode)
    if not g:
        sys.exit(1)
    lat, lon = g["lat"], g["lon"]

    step("assessor",         assessor)
    step("arcgis_inventory", arcgis_inventory)
    step("zoning",           lambda: zoning(lat, lon))
    step("parcel",           lambda: parcel(lat, lon))
    step("parcel_by_id",     lambda: parcel_by_id("128.0-0003-0012.0"))
    step("fema",             lambda: fema(lat, lon))
    step("macris",           lambda: macris(lat, lon))
    step("noncompliance",    lambda: noncompliance(lat, lon))
    step("env_overlays",     lambda: env_overlays(lat, lon))
    step("arl_historic",     lambda: arl_historic(lat, lon))

    print(f"\n✓ Done. Per-query results in {OUT}/")