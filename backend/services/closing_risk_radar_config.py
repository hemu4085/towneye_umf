"""Town-scoped Closing Risk Radar rules from configs/{town}/config.yaml."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from backend.config import get_settings
from backend.services.deal_radar_config import (
    _clamp,
    _normalize_zone_list,
    get_town_display_name,
    list_available_zone_codes,
)

_DEFAULTS: dict[str, Any] = {
    "min_risk_signals": 1,
    "min_open_permit_count": 0,
    "include_open_permit": True,
    "include_expired_permit": True,
    "include_flood_effective": True,
    "include_flood_preliminary": False,
    "require_flood_sfha_only": False,
    "include_wetland": True,
    "include_historic": True,
    "include_21e_sites": True,
    "include_ust_sites": True,
    "exclude_zone_codes": [],
    "exclude_luc_prefixes": [],
    "scoring": {
        "open_permit_weight": 0.35,
        "expired_permit_weight": 0.15,
        "flood_weight": 0.25,
        "wetland_weight": 0.15,
        "historic_weight": 0.10,
        "21e_weight": 0.50,
        "ust_weight": 0.20,
    },
    "output": {
        "top_n": 50,
        "max_scan": 20000,
    },
    "limits": {
        "min_risk_signals": [1, 5],
        "min_open_permit_count": [0, 10],
        "min_assessed_value": [0, 25000000],
        "max_assessed_value": [0, 25000000],
        "min_lot_sqft": [0, 100000],
        "max_lot_sqft": [0, 100000],
        "top_n": [10, 200],
    },
    "presets": {
        "conservative": {
            "include_open_permit": True,
            "include_expired_permit": True,
            "include_flood_effective": True,
            "require_flood_sfha_only": True,
            "include_wetland": False,
            "include_historic": False,
            "min_open_permit_count": 1,
            "top_n": 25,
        },
        "balanced": {},
        "thorough": {
            "include_flood_preliminary": True,
            "include_wetland": True,
            "include_historic": True,
            "min_risk_signals": 1,
            "top_n": 100,
        },
    },
    "sort_options": ["risk_score", "open_permit_count", "assessed_value", "tenure"],
    "pilot_gaps": [
        "Registry of Deeds chain of title, easements, and liens — not connected in pilot.",
        "MassDEP BWSC / 21E contamination sites — not connected in pilot.",
        "Probate court filings and estate proceedings — not connected in pilot.",
        "Code violations and tax liens — not connected in pilot.",
    ],
}


@lru_cache(maxsize=8)
def _raw_town_config(town_slug: str) -> dict[str, Any]:
    path = get_settings().config_dir / town_slug / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_closing_risk_radar_config(town_slug: str) -> dict[str, Any]:
    town_cfg = _raw_town_config(town_slug)
    section = town_cfg.get("closing_risk_radar") or {}
    merged = {**_DEFAULTS, **section}
    merged["scoring"] = {**_DEFAULTS["scoring"], **(section.get("scoring") or {})}
    merged["output"] = {**_DEFAULTS["output"], **(section.get("output") or {})}
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
    cfg = get_closing_risk_radar_config(town_slug)
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

    bool_keys = (
        "include_open_permit",
        "include_expired_permit",
        "include_flood_effective",
        "include_flood_preliminary",
        "require_flood_sfha_only",
        "include_wetland",
        "include_historic",
        "include_21e_sites",
        "include_ust_sites",
    )
    for key in bool_keys:
        if key in raw and raw[key] is not None:
            merged[key] = bool(raw[key])

    int_keys = {"top_n", "min_risk_signals", "min_open_permit_count", "min_lot_sqft", "max_lot_sqft"}
    float_keys = {"min_assessed_value", "max_assessed_value"}

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

    if "sort_by" in raw and raw["sort_by"]:
        sort_by = str(raw["sort_by"])
        if sort_by in (cfg.get("sort_options") or _DEFAULTS["sort_options"]):
            merged["sort_by"] = sort_by
    else:
        merged["sort_by"] = cfg.get("sort_by") or "risk_score"

    if raw.get("top_n") is not None and raw.get("top_n") != "":
        merged["top_n"] = int(_clamp(int(raw["top_n"]), limits.get("top_n", [10, 200])))
    else:
        merged["top_n"] = int((cfg.get("output") or {}).get("top_n") or 50)

    merged["applied_criteria"] = criteria_snapshot(merged)
    return merged


def criteria_snapshot(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "preset": cfg.get("active_preset"),
        "min_risk_signals": cfg.get("min_risk_signals", 1),
        "min_open_permit_count": cfg.get("min_open_permit_count", 0),
        "include_open_permit": cfg.get("include_open_permit", True),
        "include_expired_permit": cfg.get("include_expired_permit", True),
        "include_flood_effective": cfg.get("include_flood_effective", True),
        "include_flood_preliminary": cfg.get("include_flood_preliminary", False),
        "require_flood_sfha_only": cfg.get("require_flood_sfha_only", False),
        "include_wetland": cfg.get("include_wetland", True),
        "include_historic": cfg.get("include_historic", True),
        "include_21e_sites": cfg.get("include_21e_sites", True),
        "include_ust_sites": cfg.get("include_ust_sites", True),
        "min_assessed_value": cfg.get("min_assessed_value"),
        "max_assessed_value": cfg.get("max_assessed_value"),
        "min_lot_sqft": cfg.get("min_lot_sqft"),
        "max_lot_sqft": cfg.get("max_lot_sqft"),
        "include_zone_codes": list(cfg.get("include_zone_codes") or []),
        "exclude_zone_codes": list(cfg.get("exclude_zone_codes") or []),
        "top_n": cfg.get("top_n"),
        "sort_by": cfg.get("sort_by", "risk_score"),
    }


def get_portal_closing_risk_radar_config(town_slug: str) -> dict[str, Any]:
    cfg = get_closing_risk_radar_config(town_slug)
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
    "get_closing_risk_radar_config",
    "get_portal_closing_risk_radar_config",
    "get_town_display_name",
    "merge_criteria_overrides",
]
