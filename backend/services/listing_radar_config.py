"""Town-scoped Listing Radar scoring rules from configs/{town}/config.yaml."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

import pandas as pd

from backend.config import get_settings
from backend.services.deal_radar_config import (
    _clamp,
    _normalize_zone_list,
    base_zone_far_map,
    get_town_display_name,
    list_available_zone_codes,
)

_DEFAULTS: dict[str, Any] = {
    "min_owner_tenure_years": 7,
    "max_owner_tenure_years": 35,
    "min_utilization_pct": 25,
    "max_utilization_pct": 75,
    "min_existing_gfa_sqft": 800,
    "default_indicative_far": 0.50,
    "overlay_indicative_far": {
        "NMF": 2.0,
        "MBMF": 2.0,
    },
    "exclude_zone_codes": [],
    "exclude_luc_prefixes": [],
    "scoring": {
        "tenure_sweet_spot_weight": 0.30,
        "utilization_story_weight": 0.30,
        "no_permit_weight": 0.20,
        "lot_weight": 0.10,
        "value_weight": 0.10,
    },
    "output": {
        "top_n": 50,
        "max_scan": 20000,
    },
    "limits": {
        "min_owner_tenure_years": [1, 50],
        "max_owner_tenure_years": [5, 60],
        "min_utilization_pct": [0, 100],
        "max_utilization_pct": [0, 100],
        "min_existing_gfa_sqft": [0, 50000],
        "max_existing_gfa_sqft": [0, 50000],
        "min_assessed_value": [0, 25000000],
        "max_assessed_value": [0, 25000000],
        "min_lot_sqft": [0, 100000],
        "max_lot_sqft": [0, 100000],
        "top_n": [10, 200],
    },
    "presets": {
        "empty_nester": {
            "min_owner_tenure_years": 20,
            "max_owner_tenure_years": 50,
            "min_utilization_pct": 30,
            "max_utilization_pct": 70,
            "top_n": 40,
        },
        "balanced": {},
        "investor_flip": {
            "min_owner_tenure_years": 1,
            "max_owner_tenure_years": 8,
            "min_utilization_pct": 20,
            "max_utilization_pct": 85,
            "top_n": 75,
        },
    },
    "sort_options": ["score", "tenure", "assessed_value", "utilization"],
    "pilot_gaps": [
        "MLS listing history, DOM, and price reductions — not connected in pilot.",
        "Absentee owner (mailing vs site address) — not connected in pilot.",
        "Probate / estate filings — not connected in pilot.",
    ],
}


@lru_cache(maxsize=8)
def _raw_town_config(town_slug: str) -> dict[str, Any]:
    path = get_settings().config_dir / town_slug / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_listing_radar_config(town_slug: str) -> dict[str, Any]:
    town_cfg = _raw_town_config(town_slug)
    section = town_cfg.get("listing_radar") or {}
    merged = {**_DEFAULTS, **section}
    merged["scoring"] = {**_DEFAULTS["scoring"], **(section.get("scoring") or {})}
    merged["output"] = {**_DEFAULTS["output"], **(section.get("output") or {})}
    merged["overlay_indicative_far"] = {
        **_DEFAULTS["overlay_indicative_far"],
        **(section.get("overlay_indicative_far") or {}),
    }
    if not section.get("pilot_gaps"):
        merged["pilot_gaps"] = list(_DEFAULTS["pilot_gaps"])
    merged["limits"] = {**_DEFAULTS["limits"], **(section.get("limits") or {})}
    merged["presets"] = {**_DEFAULTS["presets"], **(section.get("presets") or {})}
    merged["sort_options"] = list(section.get("sort_options") or _DEFAULTS["sort_options"])
    return merged


def merge_criteria_overrides(
    town_slug: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = get_listing_radar_config(town_slug)
    limits = cfg.get("limits") or {}
    merged = dict(cfg)

    raw = dict(overrides or {})
    preset_key = str(raw.pop("preset", "") or "").strip().lower()
    if preset_key and preset_key in (cfg.get("presets") or {}):
        preset_vals = (cfg.get("presets") or {}).get(preset_key) or {}
        for key, val in preset_vals.items():
            if key not in raw:
                raw[key] = val
        merged["active_preset"] = preset_key

    int_keys = {
        "top_n",
        "min_existing_gfa_sqft",
        "max_existing_gfa_sqft",
        "min_lot_sqft",
        "max_lot_sqft",
    }
    float_keys = {
        "min_owner_tenure_years",
        "max_owner_tenure_years",
        "min_utilization_pct",
        "max_utilization_pct",
        "min_assessed_value",
        "max_assessed_value",
    }

    for key in int_keys | float_keys:
        if key not in raw or raw[key] is None or raw[key] == "":
            continue
        val = raw[key]
        if key in limits:
            val = _clamp(val, limits[key])
        merged[key] = int(val) if key in int_keys else float(val)

    if "include_zone_codes" in raw:
        merged["include_zone_codes"] = _normalize_zone_list(raw.get("include_zone_codes"))
    if "exclude_zone_codes" in raw:
        user_ex = _normalize_zone_list(raw.get("exclude_zone_codes"))
        base_ex = _normalize_zone_list(cfg.get("exclude_zone_codes"))
        merged["exclude_zone_codes"] = sorted(set(base_ex) | set(user_ex))

    if "require_no_open_permit" in raw and raw["require_no_open_permit"] is not None:
        merged["require_no_open_permit"] = bool(raw["require_no_open_permit"])

    if "sort_by" in raw and raw["sort_by"]:
        sort_by = str(raw["sort_by"])
        if sort_by in (cfg.get("sort_options") or _DEFAULTS["sort_options"]):
            merged["sort_by"] = sort_by
    else:
        merged["sort_by"] = cfg.get("sort_by") or "score"

    if raw.get("top_n") is not None and raw.get("top_n") != "":
        top_n = int(_clamp(int(raw["top_n"]), limits.get("top_n", [10, 200])))
        merged["top_n"] = int(top_n)
    else:
        merged["top_n"] = int((cfg.get("output") or {}).get("top_n") or 50)

    if "require_no_open_permit" not in merged:
        merged["require_no_open_permit"] = True

    merged["applied_criteria"] = criteria_snapshot(merged)
    return merged


def criteria_snapshot(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "preset": cfg.get("active_preset"),
        "min_owner_tenure_years": cfg.get("min_owner_tenure_years"),
        "max_owner_tenure_years": cfg.get("max_owner_tenure_years"),
        "min_utilization_pct": cfg.get("min_utilization_pct"),
        "max_utilization_pct": cfg.get("max_utilization_pct"),
        "min_existing_gfa_sqft": cfg.get("min_existing_gfa_sqft"),
        "max_existing_gfa_sqft": cfg.get("max_existing_gfa_sqft"),
        "min_assessed_value": cfg.get("min_assessed_value"),
        "max_assessed_value": cfg.get("max_assessed_value"),
        "min_lot_sqft": cfg.get("min_lot_sqft"),
        "max_lot_sqft": cfg.get("max_lot_sqft"),
        "include_zone_codes": list(cfg.get("include_zone_codes") or []),
        "exclude_zone_codes": list(cfg.get("exclude_zone_codes") or []),
        "require_no_open_permit": cfg.get("require_no_open_permit", True),
        "top_n": cfg.get("top_n"),
        "sort_by": cfg.get("sort_by", "score"),
    }


def get_portal_listing_radar_config(town_slug: str) -> dict[str, Any]:
    cfg = get_listing_radar_config(town_slug)
    base = merge_criteria_overrides(town_slug, {})
    return {
        "town_slug": town_slug,
        "defaults": criteria_snapshot(base),
        "limits": cfg.get("limits") or _DEFAULTS["limits"],
        "presets": list((cfg.get("presets") or _DEFAULTS["presets"]).keys()),
        "sort_options": cfg.get("sort_options") or _DEFAULTS["sort_options"],
        "zones": list_available_zone_codes(town_slug),
    }


__all__ = [
    "criteria_snapshot",
    "get_listing_radar_config",
    "get_portal_listing_radar_config",
    "get_town_display_name",
    "merge_criteria_overrides",
]
