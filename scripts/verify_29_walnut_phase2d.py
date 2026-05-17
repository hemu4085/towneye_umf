"""
Phase 2d verification — point-in-polygon scan of all three new domains
for 29 Walnut Street, Arlington MA.

Answers, for each domain:
  * total rows + sample
  * any polygon containing 29 Walnut?
"""
import json
from pathlib import Path

import pandas as pd

LAT, LON = 42.418722702051, -71.169852341828

DOMAINS = [
    ("noncompliance",          "data/gold/arlington-ma/noncompliance.parquet"),
    ("local-historic",         "data/gold/arlington-ma/local-historic.parquet"),
    ("environmental-overlay",  "data/gold/arlington-ma/environmental-overlay.parquet"),
]


def point_in_ring(ring, lon, lat) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def pip_any(geom_type: str, coords) -> bool:
    if geom_type == "Polygon":
        rings = coords
    elif geom_type == "MultiPolygon":
        rings = [r for poly in coords for r in poly]
    else:
        return False
    return any(point_in_ring(ring, LON, LAT) for ring in rings)


def main() -> None:
    for label, path in DOMAINS:
        p = Path(path)
        print(f"\n=== {label}  ({p}) ===")
        if not p.exists():
            print("  (file missing)")
            continue
        df = pd.read_parquet(p)
        print(f"  total rows: {len(df)}")
        print(f"  geometry types: {df['geometry_type'].value_counts().to_dict()}")
        if "category" in df.columns:
            print(f"  category mix : {df['category'].value_counts().to_dict()}")

        # Find spatial hits
        hits = []
        for _, row in df.iterrows():
            coords = row["geometry_coordinates"]
            if isinstance(coords, str):
                coords = json.loads(coords)
            if pip_any(row["geometry_type"], coords):
                hits.append(row)
        print(f"  29 Walnut polygon hits: {len(hits)}")
        for row in hits:
            cols_to_show = ["land_use_code", "zone_code_numeric", "land_use_zone_diff", "status",
                            "category", "zone_code", "zone_subtype", "sfha_flag",
                            "legend", "designation", "historic_name", "address",
                            "source_layer_name"]
            sample = {k: row[k] for k in cols_to_show if k in row.index and pd.notna(row[k])}
            print(f"    -> {sample}")


if __name__ == "__main__":
    main()
