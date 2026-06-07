"""Town-scoped developer pro forma assumptions from configs/{town}/config.yaml."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from backend.config import get_settings

_DEFAULTS: dict[str, Any] = {
    "hard_cost_psf": 475.0,
    "sale_psf": 875.0,
    "soft_cost_pct": 0.18,
    "avg_unit_sf": 900,
    "financing": {
        "annual_carry_pct": 0.075,
        "construction_months": 14,
    },
    "irr_grid": {
        "land_price_multiples": [0.90, 1.00, 1.10],
        "hard_cost_multiples": [0.90, 1.10],
    },
    "permit_fees": [],
}


@lru_cache(maxsize=8)
def _raw_town_config(town_slug: str) -> dict[str, Any]:
    path = get_settings().config_dir / town_slug / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_developer_proforma_config(town_slug: str) -> dict[str, Any]:
    town_cfg = _raw_town_config(town_slug)
    section = town_cfg.get("developer_proforma") or {}
    merged = {**_DEFAULTS, **section}
    merged["financing"] = {**_DEFAULTS["financing"], **(section.get("financing") or {})}
    merged["irr_grid"] = {**_DEFAULTS["irr_grid"], **(section.get("irr_grid") or {})}
    return merged


def compute_permit_fees(gfa: float, fee_rules: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    """Return (total_usd, line_items) from config fee rules."""
    lines: list[dict[str, Any]] = []
    total = 0.0
    for rule in fee_rules:
        label = str(rule.get("label") or "Permit fee")
        flat = float(rule.get("amount") or 0)
        per_sf = float(rule.get("per_gfa_sf") or 0)
        amount = flat + (gfa * per_sf if per_sf else 0)
        if amount <= 0:
            continue
        lines.append({"label": label, "amount": int(round(amount))})
        total += amount
    return int(round(total)), lines
