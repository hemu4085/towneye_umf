"""Tests for RE Agent v0 reports."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_demo_gold = ROOT / "demo-data" / "gold"
if _demo_gold.is_dir():
    os.environ.setdefault("GOLD_DATA_PATH", str(_demo_gold))

from backend.services.buyer_briefing import generate_buyer_briefing, render_buyer_briefing_html
from backend.services.buildability import collect_brief_data
from backend.services.listing_radar import generate_listing_radar, render_listing_radar_html
from backend.services.listing_radar_config import get_portal_listing_radar_config, merge_criteria_overrides

DEMO_TOWN = "arlington-ma"
DEMO_PARCEL = "008.0-0001-0010.0"


def test_listing_radar_config_loads():
    cfg = get_portal_listing_radar_config(DEMO_TOWN)
    assert cfg["town_slug"] == DEMO_TOWN
    assert "defaults" in cfg
    assert "empty_nester" in cfg["presets"]


def test_listing_radar_scan_produces_html():
    payload = generate_listing_radar(DEMO_TOWN)
    assert payload["report_type"] == "listing-radar"
    assert payload["total_matches"] >= 0
    assert isinstance(payload.get("listings"), list)
    html = render_listing_radar_html(payload)
    assert "Listing Radar" in html
    assert "Ranked Listing Opportunities" in html


def test_listing_radar_preset_merge():
    merged = merge_criteria_overrides(DEMO_TOWN, {"preset": "investor_flip"})
    assert merged.get("active_preset") == "investor_flip"
    assert merged["max_owner_tenure_years"] <= 10


def test_buyer_briefing_deterministic():
    data = collect_brief_data(DEMO_TOWN, DEMO_PARCEL)
    payload = generate_buyer_briefing(data)
    assert payload["report_type"] == "buyer-briefing"
    assert len(payload["talking_points"]) == 6
    html = render_buyer_briefing_html(data)
    assert "Buyer Briefing Card" in html
    assert payload["parcel_id"] == DEMO_PARCEL
