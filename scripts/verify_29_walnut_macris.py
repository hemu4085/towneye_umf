"""
Phase 2c verification — answer two questions about 29 Walnut St:

  1. Is 29 Walnut St directly listed in MACRIS?  (point match by ADDRESS string)
  2. Does any MACRIS historic-district POLYGON contain its centroid?

Also prints summary statistics that make sense as a smoke test:
  * total rows / split between Point and Polygon
  * top legend categories (NRHP / LHD / Inv. ...)
  * sample records of each kind
"""
import json
import re
from pathlib import Path

import pandas as pd

PARQUET = Path("data/gold/arlington-ma/macris.parquet")
LAT, LON = 42.418722702051, -71.169852341828
ADDRESS_NEEDLE = re.compile(r"\b29\s+walnut\b", re.IGNORECASE)


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


def main() -> None:
    df = pd.read_parquet(PARQUET)
    print(f"macris.parquet rows : {len(df)}")

    geom_counts = df["geometry_type"].value_counts().to_dict()
    print(f"by geometry_type    : {geom_counts}")

    legend_counts = df["legend"].value_counts(dropna=False).head(8).to_dict()
    print(f"top legend values   : {legend_counts}")

    kind_counts = df["resource_kind"].value_counts(dropna=False).head(8).to_dict()
    print(f"top resource_kind   : {kind_counts}")

    sample_pt = df[df["geometry_type"] == "Point"].head(1).to_dict("records")
    sample_pg = df[df["geometry_type"].isin(("Polygon", "MultiPolygon"))].head(1).to_dict("records")

    if sample_pt:
        s = sample_pt[0]
        print(
            f"\nsample point: mhcn={s['mhcn']!r} address={s['address']!r} "
            f"legend={s['legend']!r} historic_name={s['historic_name']!r}"
        )
    if sample_pg:
        s = sample_pg[0]
        print(
            f"sample polygon: mhcn={s['mhcn']!r} historic_name={s['historic_name']!r} "
            f"legend={s['legend']!r}"
        )

    print(f"\n=== Q1: any MACRIS row whose ADDRESS mentions '29 Walnut'? ===")
    addr_hits = df[df["address"].fillna("").apply(lambda s: bool(ADDRESS_NEEDLE.search(s)))]
    if len(addr_hits) == 0:
        print("  (none — 29 Walnut is not directly MACRIS-listed)")
    else:
        for _, row in addr_hits.iterrows():
            print(
                f"  - mhcn={row['mhcn']!r}  address={row['address']!r}  "
                f"legend={row['legend']!r}  historic_name={row['historic_name']!r}"
            )

    print(f"\n=== Q2: any historic-district polygon containing 29 Walnut's centroid? ===")
    polygons = df[df["geometry_type"].isin(("Polygon", "MultiPolygon"))]
    hits = 0
    for _, row in polygons.iterrows():
        coords = row["geometry_coordinates"]
        if isinstance(coords, str):
            coords = json.loads(coords)
        rings = (
            coords
            if row["geometry_type"] == "Polygon"
            else [r for poly in coords for r in poly]
        )
        if any(point_in_ring(ring, LON, LAT) for ring in rings):
            print(
                f"  - mhcn={row['mhcn']!r}  legend={row['legend']!r}  "
                f"historic_name={row['historic_name']!r}  designation={row['designation']!r}"
            )
            hits += 1
    if hits == 0:
        print("  (none — 29 Walnut is not inside any MACRIS historic district)")
    else:
        print(f"\n  Total polygon hits: {hits}")


if __name__ == "__main__":
    main()
