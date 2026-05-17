"""
Verify the canonical statewide MACRIS feature service hosted by MAPC.
Item: f9478e879cf045b8a17b94bd4b76dd68 — "MHC Historic Inventory Group Layer (from MACRIS)"
URL:  https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/MHC_Inventory_GDB/FeatureServer
"""
import requests

BASE = "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/MHC_Inventory_GDB/FeatureServer"
TOWNS_TO_TEST = ("Arlington", "Boston", "Cambridge", "Bourne")


def main() -> None:
    print(f"=== {BASE} ===")
    r = requests.get(BASE, params={"f": "json"}, timeout=30).json()
    print(f"  serviceItemId: {r.get('serviceItemId')}")
    print(f"  capabilities : {r.get('capabilities')}")
    print(f"  copyrightText: {r.get('copyrightText','')[:200]}")

    layers = r.get("layers", []) + r.get("tables", [])
    print(f"\n  layers/tables: {len(layers)}")
    for L in layers:
        print(f"    layer {L['id']:>2}: {L['name']:50s} ({L.get('geometryType', 'TABLE')})")

    for L in layers:
        lid = L["id"]
        gtype = L.get("geometryType", "TABLE")
        url = f"{BASE}/{lid}/query"

        # Total
        total = requests.get(
            url, params={"f": "json", "where": "1=1", "returnCountOnly": "true"},
            timeout=30,
        ).json().get("count", "ERR")
        print(f"\n  --- layer {lid} ({L['name']}, {gtype}) total={total} ---")

        # Schema (just show town-related fields)
        sch = requests.get(f"{BASE}/{lid}", params={"f": "json"}, timeout=30).json()
        fields = sch.get("fields", [])
        town_field = None
        for f in fields:
            if f["name"].upper() in ("TOWN_NAME", "TOWN", "MUNICIPALITY", "TOWNNAME"):
                town_field = f["name"]
                break
        if town_field:
            print(f"    town_field = {town_field!r}")
            for town in TOWNS_TO_TEST:
                rr = requests.get(
                    url,
                    params={
                        "f": "json",
                        "where": f"{town_field}='{town}'",
                        "returnCountOnly": "true",
                    },
                    timeout=20,
                ).json()
                print(f"    {town!r:14s} -> {rr.get('count', rr)}")
        else:
            print(f"    (no obvious town field; field names: {[f['name'] for f in fields[:15]]})")


if __name__ == "__main__":
    main()
