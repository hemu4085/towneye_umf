"""Town-scoped Deal Radar scoring rules from configs/{town}/config.yaml."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from backend.config import get_settings

_DEFAULTS: dict[str, Any] = {
    "min_owner_tenure_years": 15,
    "underbuilt_ratio_max": 0.60,
    "min_expansion_room_sqft": 800,
    "default_indicative_far": 0.50,
    "overlay_indicative_far": {
        "NMF": 2.0,
        "MBMF": 2.0,
    },
    "exclude_zone_codes": [],
    "exclude_luc_prefixes": [],
    "scoring": {
        "tenure_weight": 0.35,
        "underbuilt_weight": 0.45,
        "lot_weight": 0.20,
    },
    "output": {
        "top_n": 50,
        "max_scan": 20000,
    },
    "pilot_gaps": [
        "Probate / registry distress signals — not connected in pilot.",
        "Absentee owner (mailing vs site address) — not connected in pilot.",
        "MLS price-reduction history — not connected in pilot.",
    ],
}


@lru_cache(maxsize=8)
def _raw_town_config(town_slug: str) -> dict[str, Any]:
    path = get_settings().config_dir / town_slug / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_town_display_name(town_slug: str) -> str:
    cfg = _raw_town_config(town_slug)
    return str(cfg.get("town_name") or town_slug.split("-")[0].title())


def get_deal_radar_config(town_slug: str) -> dict[str, Any]:
    town_cfg = _raw_town_config(town_slug)
    section = town_cfg.get("deal_radar") or {}
    merged = {**_DEFAULTS, **section}
    merged["scoring"] = {**_DEFAULTS["scoring"], **(section.get("scoring") or {})}
    merged["output"] = {**_DEFAULTS["output"], **(section.get("output") or {})}
    merged["overlay_indicative_far"] = {
        **_DEFAULTS["overlay_indicative_far"],
        **(section.get("overlay_indicative_far") or {}),
    }
    if not section.get("pilot_gaps"):
        merged["pilot_gaps"] = list(_DEFAULTS["pilot_gaps"])
    return merged


def base_zone_far_map(town_slug: str) -> dict[str, float]:
    """Build zone_code → max_far from zoning_bylaws_mock_data in town config."""
    town_cfg = _raw_town_config(town_slug)
    rows = town_cfg.get("zoning_bylaws_mock_data") or []
    far_map: dict[str, float] = {}
    for row in rows:
        code = str(row.get("zone_code") or "").strip().upper()
        if not code:
            continue
        md = row.get("metadata") or {}
        far = md.get("max_far")
        if far is not None:
            try:
                far_map[code] = float(far)
            except (TypeError, ValueError):
                continue
    return far_map
