import json
import requests

r = requests.get(
    "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer",
    params={"f": "json"},
    timeout=15,
)
meta = r.json()
print(json.dumps(
    [{"id": l.get("id"), "name": l.get("name"), "geometryType": l.get("geometryType"), "type": l.get("type")} for l in meta.get("layers", [])],
    indent=2,
))
