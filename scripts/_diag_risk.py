#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GOLD_DATA_PATH", str(ROOT / "demo-data" / "gold"))

import pandas as pd
from core.spatial import OverlayResolver
from backend.services.parcel_permits import summarize_parcel_permits, get_parcel_permits

pid = "008.0-0001-0010.0"
stack = OverlayResolver("arlington-ma", data_dir=os.environ["GOLD_DATA_PATH"]).resolve(parcel_id=pid)
print("centroid", stack.point_lat, stack.point_lon)
print("env hits", len(stack.environmental_overlay))

df = pd.read_parquet(Path(os.environ["GOLD_DATA_PATH"]) / "arlington-ma" / "permits.parquet")
print("permits in gold", len(df))
for _, row in df.iterrows():
    md = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
    print(" permit parcel", md.get("parcel_id"), row["status"])

print("belknap", summarize_parcel_permits("arlington-ma", pid))

# parcels with open permits
for _, row in df.iterrows():
    md = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
    p = str(md.get("parcel_id") or "")
    if p and row["status"] in ("APPROVED", "UNDER_REVIEW", "INSPECTIONS", "SUBMITTED"):
        print("OPEN PERMIT PARCEL", p, md.get("address"))

# env hit parcels
props = pd.read_parquet(Path(os.environ["GOLD_DATA_PATH"]) / "arlington-ma" / "property.parquet", columns=["parcel_id"])
found = 0
for p in props["parcel_id"].astype(str):
    s = OverlayResolver("arlington-ma", data_dir=os.environ["GOLD_DATA_PATH"]).resolve(parcel_id=p)
    if s.environmental_overlay:
        print("ENV", p, s.parcel.address, s.environmental_overlay[0].code)
        found += 1
        if found >= 5:
            break
