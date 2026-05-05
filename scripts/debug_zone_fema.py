#!/usr/bin/env python3
"""Debug zone_code values and FEMA data for Arlington property parcels."""
import pandas as pd
import pathlib

# Property data
prop = pd.read_parquet("data/gold/arlington-ma/property.parquet")
print("=== ASSESSOR ZONE CODES (unique) ===")
if "zone_code" in prop.columns:
    print(prop["zone_code"].value_counts().to_string())
print()

# Sample of addresses with zone codes
cols = [c for c in ["address", "zone_code", "assessed_value", "year_built", "beds"] if c in prop.columns]
print("=== SAMPLE PARCELS ===")
print(prop[cols].head(20).to_string())
print()

# Zoning data
zon = pd.read_parquet("data/gold/arlington-ma/zoning.parquet")
print("=== ZONING BYLAW ZONE CODES ===")
if "zone_code" in zon.columns:
    for _, r in zon.iterrows():
        print(f"  {r['zone_code']:6s}  {r.get('zone_description','')}")
print()

# FEMA data
clim = pd.read_parquet("data/gold/arlington-ma/climate-zones.parquet")
print("=== FEMA DATA SAMPLE ===")
print(f"Total rows: {len(clim)}")
sample_cols = [c for c in ["risk_level", "event_type", "metadata", "te_source"] if c in clim.columns]
print(clim[sample_cols].head(5).to_string())
print()
if "metadata" in clim.columns:
    meta_sample = clim["metadata"].iloc[0]
    print(f"metadata[0]: {meta_sample}")
