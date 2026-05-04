#!/usr/bin/env python3
"""Quick data quality audit for Arlington, MA."""
import pandas as pd
import pathlib

GOLD = pathlib.Path("data/gold/arlington-ma")

DOMAINS = [
    ("property",        "address",      "arlington-ma-tax-assessor",   "REAL"),
    ("market-trends",   "metric_name",  "zillow-zhvi",                 "REAL"),
    ("climate-zones",   "risk_level",   "fema-flood-maps",             "REAL"),
    ("transit",         "event_name",   "arlington-ma-mbta-alerts",    "REAL"),
    ("zoning",          "zone_code",    "arlington-zoning-bylaw-2024", "ACCURATE"),
    ("311",             None,           "seeclickfix",                 "MOCK"),
    ("broadband",       None,           "fcc-broadband",               "MOCK"),
    ("permits",         None,           "arlington-permits",           "MOCK"),
    ("infra-projects",  "project_name", "arlington-dpw",               "ESTIMATED"),
    ("school-calendar", None,           "arlington-schools",           "MOCK"),
    ("str-dynamics",    None,           "str-market",                  "ESTIMATED"),
    ("town-profile",    None,           "arlington-town-profile",      "ESTIMATED"),
    ("equity-index",    None,           "ejscreen",                    "REAL"),
]

print(f"\n{'DOMAIN':<22} {'ROWS':<6} {'ACTUAL SOURCE':<38} {'EXPECTED':<12} STATUS")
print("─" * 100)

for name, sample_col, expected_src, expected_status in DOMAINS:
    p = GOLD / f"{name}.parquet"
    if not p.exists():
        print(f"{'  ' + name:<22} {'—':<6} {'FILE MISSING':<38} {expected_status:<12} ❌ MISSING")
        continue
    df = pd.read_parquet(p)
    rows = len(df)
    actual_src = df["te_source"].iloc[0] if "te_source" in df.columns and rows > 0 else "?"
    sample = ""
    if sample_col and sample_col in df.columns:
        sample = str(df[sample_col].iloc[0])[:35]

    is_synthetic = any(x in str(actual_src).lower() for x in
                       ["synthetic", "mock", "fixture", "llm", "generated"])
    status = "⚠ SYNTHETIC" if is_synthetic else "✅"
    print(f"  {name:<20} {rows:<6} {str(actual_src):<38} {expected_status:<12} {status}  {sample}")

print()
print("LEGEND: REAL=live govt API  ACCURATE=curated static  ESTIMATED=LLM-synthesized  MOCK=placeholder")
