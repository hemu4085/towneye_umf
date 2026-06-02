#!/usr/bin/env python3
"""Build a compact address index for portal autocomplete (demo deploy)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def build_index(town_slug: str) -> Path:
    src = ROOT / "data" / "gold" / town_slug / "parcel.parquet"
    dest_dir = ROOT / "demo-data" / "gold" / town_slug
    dest = dest_dir / "address-index.json"

    if not src.is_file():
        raise FileNotFoundError(f"Missing source parquet: {src}")

    df = pd.read_parquet(src, columns=["address", "parcel_id"])
    df = df.dropna(subset=["address", "parcel_id"])
    df["address"] = df["address"].astype(str).str.strip()
    df["parcel_id"] = df["parcel_id"].astype(str).str.strip()
    df = df[df["address"].astype(bool) & df["parcel_id"].astype(bool)]
    df = df.drop_duplicates(subset=["address", "parcel_id"])

    entries = [
        {"address": row.address, "parcel_id": row.parcel_id}
        for row in df.itertuples(index=False)
    ]

    dest_dir.mkdir(parents=True, exist_ok=True)
    payload = {"town_slug": town_slug, "count": len(entries), "entries": entries}
    dest.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    print(f"OK: {town_slug} — {len(entries)} addresses → {dest} ({dest.stat().st_size // 1024} KiB)")
    return dest


if __name__ == "__main__":
    towns = sys.argv[1:] or ["arlington-ma"]
    for town in towns:
        build_index(town)
