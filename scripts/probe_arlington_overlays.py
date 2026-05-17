"""
Probe all 7 Arlington-hosted FeatureServers used by Phase 2d.

For each service we report:
  * the layers it exposes (id / name / geometryType),
  * the field schema of the first polygon/point layer,
  * the total row count for that layer.

Output is informational; nothing is written to disk.
"""
import requests

ARLINGTON = "https://services2.arcgis.com/s1Sh73K7qtP9JdrG/arcgis/rest/services"

GROUPS = {
    "noncompliance":   ["LandUse_NonCompliance"],
    "hydrology":       ["ArlingtonMA_Wetlands", "Arlington_Flood_Zones",
                        "Flood_Zones_Preliminary_Changes_2023"],
    "local-historic":  ["Local_Historic_District", "National_Historic_District",
                        "Historic_Overlay_Districts",
                        "Historic_Commission_Inventory_view"],
}


def fetch(url: str) -> dict:
    try:
        r = requests.get(url, params={"f": "json"}, timeout=30)
        return r.json()
    except Exception as exc:
        return {"_err": str(exc)}


def probe_service(service_name: str) -> None:
    base = f"{ARLINGTON}/{service_name}/FeatureServer"
    print(f"\n--- {service_name} -> {base} ---")
    root = fetch(base)
    if "_err" in root:
        print(f"   ! {root['_err']}")
        return
    layers = root.get("layers", []) + root.get("tables", [])
    if not layers:
        print(f"   (no layers / tables; raw keys: {list(root.keys())})")
        return
    for L in layers:
        gtype = L.get("geometryType", "TABLE")
        print(f"   layer {L['id']:>2}: {L['name']:48s} ({gtype})")

    first = layers[0]
    layer_url = f"{base}/{first['id']}"
    sch = fetch(layer_url)
    if "_err" in sch:
        print(f"     ! schema fetch: {sch['_err']}")
        return
    fields = sch.get("fields", [])
    print(f"     schema for layer {first['id']} (first 18 fields):")
    for f in fields[:18]:
        print(f"       {f['name']:30s} {f['type']:25s} alias={f.get('alias','')!r}")

    cnt = fetch(f"{layer_url}/query?where=1=1&returnCountOnly=true")
    print(f"     total rows: {cnt.get('count', cnt)}")


def main() -> None:
    for group_name, services in GROUPS.items():
        print(f"\n========== GROUP: {group_name} ==========")
        for svc in services:
            probe_service(svc)


if __name__ == "__main__":
    main()
