#!/usr/bin/env python3
"""Bake demo report HTML into demo-data/reports/ for instant portal previews."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Prefer slim demo gold; fall back to full local lake.
_demo_gold = ROOT / "demo-data" / "gold"
_full_gold = ROOT / "data" / "gold"
if _demo_gold.is_dir() and any(_demo_gold.rglob("*.parquet")):
    os.environ.setdefault("GOLD_DATA_PATH", str(_demo_gold))
else:
    os.environ.setdefault("GOLD_DATA_PATH", str(_full_gold))

from backend.services.buildability import generate_buildability_html  # noqa: E402

DEMO_PARCEL = "128.0-0003-0012.0"
DEMO_TOWN = "arlington-ma"
DEMO_ADDRESS = "29 WALNUT ST, Arlington MA"


def main() -> None:
    dest = ROOT / "demo-data" / "reports" / DEMO_TOWN / DEMO_PARCEL / "buildability.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    html = generate_buildability_html(DEMO_TOWN, DEMO_PARCEL, None)
    dest.write_text(html, encoding="utf-8")
    print(f"OK: {dest} ({len(html)} bytes) — {DEMO_ADDRESS}")


if __name__ == "__main__":
    main()
