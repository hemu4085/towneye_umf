#!/usr/bin/env python3
"""Compare data quality across all onboarded towns."""
import pandas as pd
import pathlib

TOWNS = ["arlington-ma", "somerville-ma", "lexington-ma", "winchester-ma", "woburn-ma", "burlington-ma"]
KEY_DOMAINS = ["property", "market-trends", "climate-zones", "transit", "zoning"]

REAL_SOURCES = {
    "property":       ["tax-assessor", "patriot"],
    "market-trends":  ["zillow-zhvi", "redfin", "mls"],
    "climate-zones":  ["fema"],
    "transit":        ["mbta"],
    "zoning":         ["zoning-bylaw", "zoning-json"],
}

def classify(domain, src):
    src_l = src.lower()
    for keyword in REAL_SOURCES.get(domain, []):
        if keyword in src_l:
            return "✅ REAL"
    if any(x in src_l for x in ["synthetic", "mock", "fixture", "opengov"]):
        return "⚠ MOCK/EST"
    return "❓ UNKNOWN"

print(f"\n{'TOWN':<18}", end="")
for d in KEY_DOMAINS:
    print(f" {d[:14]:<15}", end="")
print()
print("─" * 93)

for town in TOWNS:
    gold = pathlib.Path(f"data/gold/{town}")
    print(f"  {town:<16}", end="")
    for domain in KEY_DOMAINS:
        p = gold / f"{domain}.parquet"
        if not p.exists():
            print(f" {'❌ MISSING':<15}", end="")
            continue
        df = pd.read_parquet(p)
        src = df["te_source"].iloc[0] if "te_source" in df.columns and len(df) > 0 else "?"
        label = classify(domain, src)
        print(f" {label:<15}", end="")
    print()

print()
print("Key: ✅ REAL = live government API   ⚠ MOCK/EST = synthetic/estimated   ❌ MISSING = not scraped")
