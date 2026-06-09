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

from backend.services.buildability import collect_brief_data, generate_buildability_html  # noqa: E402
from backend.services.buyer_briefing import render_buyer_briefing_html  # noqa: E402
from backend.services.closing_risk_radar import generate_closing_risk_radar_html
from backend.services.deal_radar import generate_deal_radar_html  # noqa: E402
from backend.services.homeowner_full import generate_homeowner_full_html  # noqa: E402
from backend.services.listing_radar import generate_listing_radar_html  # noqa: E402
from backend.services.proforma import generate_proforma_html  # noqa: E402
from backend.services.risk import render_risk_html  # noqa: E402

DEMO_PARCEL = "008.0-0001-0010.0"
DEMO_TOWN = "arlington-ma"
DEMO_ADDRESS = "5-7 BELKNAP ST, Arlington MA"

REPORT_WRITERS = {
    "buildability": generate_buildability_html,
    "buyer-briefing": lambda town, parcel, pf: render_buyer_briefing_html(
        collect_brief_data(town, parcel, pf),
    ),
    "deal-radar": generate_deal_radar_html,
    "homeowner-full": generate_homeowner_full_html,
    "proforma": generate_proforma_html,
    "risk": lambda town, parcel, pf: render_risk_html(
        collect_brief_data(town, parcel, pf),
    ),
}


def main() -> None:
    out_dir = ROOT / "demo-data" / "reports" / DEMO_TOWN / DEMO_PARCEL
    out_dir.mkdir(parents=True, exist_ok=True)
    for report_type, writer in REPORT_WRITERS.items():
        dest = out_dir / f"{report_type}.html"
        html = writer(DEMO_TOWN, DEMO_PARCEL, None)
        dest.write_text(html, encoding="utf-8")
        print(f"OK: {dest} ({len(html)} bytes) — {DEMO_ADDRESS}")

    town_dir = ROOT / "demo-data" / "reports" / DEMO_TOWN / "_town"
    town_dir.mkdir(parents=True, exist_ok=True)
    town_html = generate_deal_radar_html(DEMO_TOWN, None)
    town_dest = town_dir / "deal-radar.html"
    town_dest.write_text(town_html, encoding="utf-8")
    print(f"OK: {town_dest} ({len(town_html)} bytes) — {DEMO_TOWN} town-wide")

    closing_html = generate_closing_risk_radar_html(DEMO_TOWN, None)
    closing_dest = town_dir / "closing-risk-radar.html"
    closing_dest.write_text(closing_html, encoding="utf-8")
    print(f"OK: {closing_dest} ({len(closing_html)} bytes) — {DEMO_TOWN} closing risk")

    listing_html = generate_listing_radar_html(DEMO_TOWN, None)
    listing_dest = town_dir / "listing-radar.html"
    listing_dest.write_text(listing_html, encoding="utf-8")
    print(f"OK: {listing_dest} ({len(listing_html)} bytes) — {DEMO_TOWN} listing radar")

    highlight_listing = generate_listing_radar_html(DEMO_TOWN, DEMO_PARCEL)
    highlight_dest = out_dir / "listing-radar.html"
    highlight_dest.write_text(highlight_listing, encoding="utf-8")
    print(f"OK: {highlight_dest} ({len(highlight_listing)} bytes) — {DEMO_ADDRESS} listing highlight")


if __name__ == "__main__":
    main()

