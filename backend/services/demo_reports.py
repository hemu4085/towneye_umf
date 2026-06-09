"""Pre-generated demo reports for reliable instant previews on Render free tier."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Demo cache for town-scoped reports (no parcel highlight).
TOWN_WIDE_DEMO_KEY = "_town"


def _demo_reports_root() -> Path:
    custom = os.getenv("DEMO_REPORTS_PATH", "").strip()
    if custom:
        return Path(custom)
    return REPO_ROOT / "demo-data" / "reports"


@lru_cache(maxsize=64)
def get_demo_report_html(town_slug: str, parcel_id: str, report_type: str) -> str | None:
    path = _demo_reports_root() / town_slug / parcel_id / f"{report_type}.html"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def get_deal_radar_demo_html(town_slug: str, parcel_id: str | None = None) -> str | None:
    """Prefer parcel-highlight cache when present; fall back to town-wide demo."""
    if parcel_id:
        html = get_demo_report_html(town_slug, parcel_id, "deal-radar")
        if html:
            return html
    return get_demo_report_html(town_slug, TOWN_WIDE_DEMO_KEY, "deal-radar")


def get_closing_risk_radar_demo_html(town_slug: str, parcel_id: str | None = None) -> str | None:
    """Prefer parcel-highlight cache when present; fall back to town-wide demo."""
    if parcel_id:
        html = get_demo_report_html(town_slug, parcel_id, "closing-risk-radar")
        if html:
            return html
    return get_demo_report_html(town_slug, TOWN_WIDE_DEMO_KEY, "closing-risk-radar")


def get_listing_radar_demo_html(town_slug: str, parcel_id: str | None = None) -> str | None:
    """Prefer parcel-highlight cache when present; fall back to town-wide demo."""
    if parcel_id:
        html = get_demo_report_html(town_slug, parcel_id, "listing-radar")
        if html:
            return html
    return get_demo_report_html(town_slug, TOWN_WIDE_DEMO_KEY, "listing-radar")
