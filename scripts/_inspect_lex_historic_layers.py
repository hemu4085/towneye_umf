# [FILE PATH]: scripts/_inspect_lex_historic_layers.py
"""List the layers inside Lexington's two historic FeatureServers + count
features per layer, so we know which layer_ids to include."""
from __future__ import annotations

import requests

URLS = {
    "survey": (
        "https://services.arcgis.com/bP0owepHkr9WxF4V/arcgis/rest/services/"
        "HistoricPropertySurveyView/FeatureServer"
    ),
    "inventory": (
        "https://services.arcgis.com/bP0owepHkr9WxF4V/arcgis/rest/services/"
        "HistoricPropInventoryView2/FeatureServer"
    ),
}

for src, root in URLS.items():
    print(f"\n=== {src} ===\n  root: {root}")
    layers = requests.get(root, params={"f": "json"}, timeout=15).json().get("layers", [])
    print(f"  {len(layers)} layer(s):")
    for L in layers:
        cnt = requests.get(
            f"{root}/{L['id']}/query",
            params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
            timeout=15,
        ).json().get("count")
        print(f"    layer {L['id']:>3}  ({L.get('geometryType','?'):<22}) "
              f"{(L.get('name','') or '')[:50]:<50}  count={cnt}")
