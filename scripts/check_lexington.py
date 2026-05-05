#!/usr/bin/env python3
import pandas as pd

df = pd.read_parquet("data/gold/lexington-ma/property.parquet")
print(f"Total rows: {len(df)}")
print()
cols = [c for c in ["address", "assessed_value", "zone_code", "year_built"] if c in df.columns]
print(df[cols].head(15).to_string())

# Also check market source
mkt = pd.read_parquet("data/gold/lexington-ma/market-trends.parquet")
print(f"\nMarket rows: {len(mkt)}, source: {mkt['te_source'].iloc[0]}")
