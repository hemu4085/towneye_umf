"""
Phase 2b verification — point-in-polygon scan of zoning-overlay.parquet
for 29 Walnut Street, Arlington MA.

Confirms that:
  * the new ingestor wrote the file,
  * the file contains every polygon layer the FeatureServer exposes,
  * 29 Walnut's centroid falls inside the expected base zone + any §3A
    MBTA-Communities overlay polygons.
"""
import json
from pathlib import Path

import pandas as pd

PARQUET = Path("data/gold/arlington-ma/zoning-overlay.parquet")
# 29 Walnut St geocode (Census Geocoder, side=R, tigerLineId=86885573)
LAT, LON = 42.418722702051, -71.169852341828


def point_in_ring(ring, lon, lat) -> bool:
    """Standard ray-cast against a single GeoJSON outer ring."""
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


def main() -> None:
    df = pd.read_parquet(PARQUET)
    print(f"zoning-overlay.parquet rows : {len(df)}")
    print(f"Layers ingested             : {sorted(df['layer_name'].unique())}")
    zc = sorted(c for c in df["zone_code"].dropna().unique())
    print(f"Distinct zone codes ({len(zc):>2}) : {zc}")
    ot = sorted(t for t in df["overlay_type"].dropna().unique())
    print(f"Distinct overlay types ({len(ot)}) : {ot}")

    print(f"\n29 Walnut St (lat={LAT}, lon={LON}) intersects:")
    hits = 0
    for _, row in df.iterrows():
        coords = row["geometry_coordinates"]
        if isinstance(coords, str):
            coords = json.loads(coords)
        rings = (
            coords
            if row["geometry_type"] == "Polygon"
            else [r for poly in coords for r in poly]
        )
        if any(point_in_ring(ring, LON, LAT) for ring in rings):
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            district_name = (
                meta.get("district_name") if isinstance(meta, dict) else None
            )
            print(
                f"  - layer={row['layer_name']!r:34s}  "
                f"zone={row['zone_code']!r:8s}  "
                f"overlay_type={row['overlay_type']!r:18s}  "
                f"district_name={district_name!r}"
            )
            hits += 1
    print(f"\nTotal hits: {hits}")


if __name__ == "__main__":
    main()
