"""Development Pro Forma — envelope-grounded economics + optional Claude synthesis."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.buildability import collect_brief_data
from backend.services.lender import _load_market_metrics, _zip_from_address
from backend.services.lender_phase3 import _analyze_sale_comps
from backend.services.llm import generate_json_report
from backend.utils.parcel_lookup import _load_town_config
from backend.services.town_proforma_config import (
    compute_permit_fees,
    get_developer_proforma_config,
)
from reports.buildability_brief import BriefData, BuildableEnvelope

_STATUS_LABEL = {"clear": "Clear", "caution": "Caution", "flagged": "Flagged"}


def _fmt_int(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _resolve_land_basis(
    data: BriefData,
    overrides: dict[str, Any] | None = None,
) -> tuple[float, str]:
    o = overrides or {}
    mode = str(o.get("land_basis_mode") or "assessed").lower()
    pi = data.property_info

    if mode == "acquisition" and o.get("acquisition_price") is not None:
        try:
            price = float(o["acquisition_price"])
            if price > 0:
                return price, "User acquisition / option price"
        except (TypeError, ValueError):
            pass

    if mode == "last_sale" and pi and pi.last_sale_price:
        try:
            price = float(pi.last_sale_price)
            if price > 0:
                return price, "Last recorded sale (assessor/CAMA)"
        except (TypeError, ValueError):
            pass

    assessed = _assessed_value(data)
    if assessed is not None and assessed > 0:
        return assessed, "Assessed value (Mass. CAMA)"

    lot = data.parcel.area_sqft or 0.0
    return lot * 55.0, "Lot area × $55/sf indicative proxy"


def _land_basis(data: BriefData, overrides: dict[str, Any] | None = None) -> float:
    return _resolve_land_basis(data, overrides)[0]


def _resolve_exit_pricing(
    pf_cfg: dict[str, Any],
    market: dict[str, Any],
    comps: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    o = overrides or {}
    config_psf = float(pf_cfg["sale_psf"])
    premium = float(pf_cfg.get("new_construction_premium_pct", 0.40))
    comp_resale = comps.get("median_ppsf")
    zip_psf = market.get("price_per_sqft")

    comp_new_psf = round(comp_resale * (1.0 + premium), 0) if comp_resale else None
    zip_new_psf = round(zip_psf * (1.0 + premium * 0.5), 0) if zip_psf else None

    if o.get("sale_psf") is not None:
        chosen = float(o["sale_psf"])
        method = "User override"
    elif comp_new_psf and zip_new_psf:
        chosen = round(0.55 * comp_new_psf + 0.25 * zip_new_psf + 0.20 * config_psf, 0)
        method = (
            "Blend: CAMA comps (+new-construction premium), zip MLS trend, town config"
        )
    elif comp_new_psf:
        chosen = round(0.70 * comp_new_psf + 0.30 * config_psf, 0)
        method = "CAMA comparable sales (+new-construction premium) blended with town config"
    elif zip_new_psf:
        chosen = round(0.60 * zip_new_psf + 0.40 * config_psf, 0)
        method = "Zip price/sf trend (+premium) blended with town config"
    else:
        chosen = config_psf
        method = "Town config indicative new-construction $/sf (no comps in radius)"

    return {
        "sale_psf_used": chosen,
        "method": method,
        "comp_median_resale_psf": comp_resale,
        "comp_adjusted_new_psf": comp_new_psf,
        "zip_price_per_sqft": zip_psf,
        "zip_adjusted_new_psf": zip_new_psf,
        "config_indicative_psf": config_psf,
        "new_construction_premium_pct": premium,
    }


def _scenario_equity_returns(
    scenario: dict[str, Any],
    pf_cfg: dict[str, Any],
) -> dict[str, Any]:
    inv = pf_cfg.get("investor_financing") or {}
    fin = pf_cfg.get("financing") or {}
    ltc = float(inv.get("ltc_pct", 0.70))
    sellout_mo = int(inv.get("sellout_months", 6))
    construction_mo = int(fin.get("construction_months", 14))
    total_mo = max(1, construction_mo + sellout_mo)

    construction_cost = (
        float(scenario.get("hard_cost") or 0)
        + float(scenario.get("soft_cost") or 0)
        + float(scenario.get("permit_fees") or 0)
        + float(scenario.get("contingency") or 0)
    )
    total_uses = float(scenario.get("total_cost") or 0)
    sale = float(scenario.get("sale_price") or 0)

    debt = int(round(construction_cost * ltc))
    equity = int(round(max(0.0, total_uses - debt)))
    net_to_equity = int(round(sale - debt))
    equity_profit = int(round(net_to_equity - equity))

    equity_multiple = round(net_to_equity / equity, 2) if equity > 0 else None
    equity_irr = None
    if equity_multiple and equity_multiple > 0:
        equity_irr = round((equity_multiple ** (12.0 / total_mo) - 1.0) * 100.0, 1)

    return {
        "ltc_pct": ltc,
        "construction_loan": debt,
        "equity_required": equity,
        "net_sale_proceeds": net_to_equity,
        "equity_profit": equity_profit,
        "equity_multiple": equity_multiple,
        "equity_irr_pct": equity_irr,
        "hold_months": total_mo,
    }


def _overlay_economics_delta(
    scenarios: list[dict[str, Any]],
    primary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not primary:
        return None
    base = next((s for s in scenarios if not s.get("is_overlay")), None)
    if not base or base.get("name") == primary.get("name"):
        return None
    pe = primary.get("equity_returns") or {}
    be = base.get("equity_returns") or {}
    return {
        "base_scenario": base.get("name"),
        "primary_scenario": primary.get("name"),
        "profit_delta": int(primary.get("profit", 0) - base.get("profit", 0)),
        "roi_delta_pct": round(float(primary.get("roi_pct", 0)) - float(base.get("roi_pct", 0)), 1),
        "units_delta": int(primary.get("units", 0) - base.get("units", 0)),
        "gfa_delta": int(primary.get("total_gfa", 0) - base.get("total_gfa", 0)),
        "equity_multiple_delta": round(
            float(pe.get("equity_multiple") or 0) - float(be.get("equity_multiple") or 0),
            2,
        ) if pe.get("equity_multiple") and be.get("equity_multiple") else None,
    }


def _investor_verdict(
    primary: dict[str, Any] | None,
    constraints: list[dict[str, str]],
    pf_cfg: dict[str, Any],
) -> dict[str, Any]:
    inv = pf_cfg.get("investor_financing") or {}
    hurdle_em = float(inv.get("hurdle_equity_multiple", 1.35))
    hurdle_irr = float(inv.get("hurdle_equity_irr_pct", 18.0))
    hurdle_roi = float(inv.get("hurdle_project_roi_pct", 12.0))

    if primary is None:
        return {
            "rating": "pass",
            "label": "Pass — no buildable envelope economics computed",
            "summary": "Indicative returns could not be anchored to a zoning envelope.",
        }

    equity = primary.get("equity_returns") or {}
    em = float(equity.get("equity_multiple") or 0)
    irr = float(equity.get("equity_irr_pct") or 0)
    roi = float(primary.get("roi_pct") or 0)
    flagged = any(c.get("status") == "flagged" for c in constraints)
    caution_layers = sum(1 for c in constraints if c.get("status") in ("caution", "flagged"))

    if roi < 0 or em < 1.0:
        rating = "pass"
        label = "Pass — does not clear minimum return thresholds"
        summary = (
            f"Indicative project ROI {roi:.1f}% and equity multiple {em:.2f}× do not support "
            "capital deployment at current land and exit assumptions."
        )
    elif flagged or em < 1.15 or roi < 5:
        rating = "caution"
        label = "Caution — marginal economics or regulatory friction"
        summary = (
            f"Overlay path shows {em:.2f}× equity multiple and {irr:.1f}% annualized equity IRR "
            f"at {int(inv.get('ltc_pct', 0.70) * 100)}% LTC — validate land basis, exit comps, "
            "and entitlement path before IC."
        )
    elif em >= hurdle_em and irr >= hurdle_irr and roi >= hurdle_roi and caution_layers == 0:
        rating = "pursue"
        label = "Pursue — indicative returns clear investor hurdles"
        summary = (
            f"Recommended regime {primary.get('name')} clears hurdles "
            f"({em:.2f}× equity, {irr:.1f}% IRR, {roi:.1f}% project ROI) with a clean constraint stack."
        )
    else:
        rating = "caution"
        label = "Caution — returns below target hurdle or open constraint layers"
        summary = (
            f"Indicative {em:.2f}× equity / {irr:.1f}% IRR vs hurdles "
            f"{hurdle_em:.2f}× / {hurdle_irr:.0f}% — re-trade land or confirm overlay election."
        )

    return {"rating": rating, "label": label, "summary": summary}


def _investor_exhibit(
    data: BriefData,
    primary: dict[str, Any] | None,
    exit_pricing: dict[str, Any],
    land_source: str,
    verdict: dict[str, Any],
    overlay_delta: dict[str, Any] | None,
    constraints: list[dict[str, str]],
) -> dict[str, Any]:
    equity = (primary or {}).get("equity_returns") or {}
    key_risks = [
        f"{c['label']}: {c['detail']}"
        for c in constraints
        if c.get("status") in ("caution", "flagged")
    ][:4]
    if not key_risks:
        key_risks = ["No historic, flood, wetland, or non-compliance flags in TownEye Gold."]

    return {
        "report_title": "Investor Feasibility Exhibit",
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "prepared_on": (data.inputs.prepared_on or date.today()).isoformat(),
        "investor_verdict": verdict.get("rating"),
        "investor_verdict_label": verdict.get("label"),
        "investor_thesis": verdict.get("summary"),
        "recommended_regime": primary.get("name") if primary else None,
        "units": primary.get("units") if primary else None,
        "total_gfa": primary.get("total_gfa") if primary else None,
        "equity_required": equity.get("equity_required"),
        "equity_profit": equity.get("equity_profit"),
        "equity_multiple": equity.get("equity_multiple"),
        "equity_irr_pct": equity.get("equity_irr_pct"),
        "project_roi_pct": primary.get("roi_pct") if primary else None,
        "sale_proceeds": primary.get("sale_price") if primary else None,
        "total_project_cost": primary.get("total_cost") if primary else None,
        "exit_sale_psf": exit_pricing.get("sale_psf_used"),
        "exit_pricing_method": exit_pricing.get("method"),
        "land_basis": primary.get("land_basis") if primary else None,
        "land_basis_source": land_source,
        "overlay_profit_uplift": overlay_delta.get("profit_delta") if overlay_delta else None,
        "overlay_equity_uplift": overlay_delta.get("equity_multiple_delta") if overlay_delta else None,
        "key_risks": key_risks,
    }


def _load_proforma_context(
    data: BriefData,
    pf_cfg: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    town_cfg = _load_town_config(data.inputs.town_slug)
    zipcode = _zip_from_address(data.parcel.address)
    market = _load_market_metrics(data.inputs.town_slug, zipcode)
    comps = _analyze_sale_comps(data, town_cfg)
    exit_pricing = _resolve_exit_pricing(pf_cfg, market, comps, overrides)
    land_basis, land_source = _resolve_land_basis(data, overrides)
    return {
        "market": market,
        "comps": comps,
        "exit_pricing": exit_pricing,
        "land_basis": land_basis,
        "land_source": land_source,
        "zipcode": zipcode,
    }


def _build_scenarios(
    data: BriefData,
    pf_cfg: dict[str, Any],
    ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    land_basis = float(ctx["land_basis"])
    sale_psf = float(ctx["exit_pricing"]["sale_psf_used"])
    envelopes = data.envelopes[:3] if data.envelopes else []
    scenarios: list[dict[str, Any]] = []
    for envelope in envelopes:
        scenario = _scenario_from_envelope(
            envelope,
            data,
            pf_cfg,
            land_basis=land_basis,
            sale_psf=sale_psf,
        )
        scenario["equity_returns"] = _scenario_equity_returns(scenario, pf_cfg)
        scenarios.append(scenario)

    if not scenarios:
        lot = data.parcel.area_sqft or 0.0
        fake = BuildableEnvelope(
            zone_code=data.primary_zone_code or "—",
            is_overlay=False,
            label="Base (parcel area)",
            rationale="Derived from parcel area — refine with full envelope",
            lot_sqft=lot,
        )
        scenario = _scenario_from_envelope(
            fake,
            data,
            pf_cfg,
            land_basis=land_basis,
            sale_psf=sale_psf,
        )
        scenario["equity_returns"] = _scenario_equity_returns(scenario, pf_cfg)
        scenarios.append(scenario)
    return scenarios


def _assessed_value(data: BriefData) -> float | None:
    if data.property_info is not None and data.property_info.assessed_value is not None:
        return float(data.property_info.assessed_value)
    return None


def _indicative_gfa(envelope: BuildableEnvelope, data: BriefData) -> float:
    if envelope.max_gfa_sqft is not None and envelope.max_gfa_sqft > 0:
        return float(envelope.max_gfa_sqft)
    lot = envelope.lot_sqft or data.parcel.area_sqft or 0.0
    if envelope.is_overlay and lot > 0:
        return lot * 0.65 * 2.0
    return lot * 0.5


def _pf_cfg(data: BriefData, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = get_developer_proforma_config(data.inputs.town_slug)
    if not overrides:
        return base
    
    merged = dict(base)
    for k in ["hard_cost_psf", "soft_cost_pct", "sale_psf", "avg_unit_sf", "contingency_pct"]:
        if k in overrides and overrides[k] is not None:
            merged[k] = overrides[k]

    if "investor_financing" in overrides and isinstance(overrides["investor_financing"], dict):
        merged["investor_financing"] = {
            **(merged.get("investor_financing") or {}),
            **overrides["investor_financing"],
        }
            
    if "financing" in overrides and isinstance(overrides["financing"], dict):
        merged["financing"] = {**(merged.get("financing") or {}), **overrides["financing"]}
        
    return merged


def _units_from_gfa(gfa: float, avg_unit_sf: float) -> int:
    return max(1, int(round(gfa / avg_unit_sf)))


def _carry_cost(subtotal: float, pf_cfg: dict[str, Any]) -> float:
    fin = pf_cfg.get("financing") or {}
    rate = float(fin.get("annual_carry_pct") or 0)
    months = float(fin.get("construction_months") or 12)
    return subtotal * rate * (months / 12.0)


def _scenario_from_envelope(
    envelope: BuildableEnvelope,
    data: BriefData,
    pf_cfg: dict[str, Any],
    *,
    land_basis: float | None = None,
    sale_psf: float | None = None,
) -> dict[str, Any]:
    hard_psf = float(pf_cfg["hard_cost_psf"])
    soft_pct = float(pf_cfg["soft_cost_pct"])
    sale_psf_val = float(sale_psf if sale_psf is not None else pf_cfg["sale_psf"])
    avg_unit_sf = float(pf_cfg["avg_unit_sf"])
    contingency_pct = float(pf_cfg.get("contingency_pct", 0.05))

    gfa = _indicative_gfa(envelope, data)
    units = _units_from_gfa(gfa, avg_unit_sf)
    hard = gfa * hard_psf
    soft = hard * soft_pct
    land = land_basis if land_basis is not None else _resolve_land_basis(data, None)[0]
    permit_total, permit_lines = compute_permit_fees(gfa, pf_cfg.get("permit_fees") or [])
    contingency = hard * contingency_pct
    subtotal = hard + soft + land + permit_total + contingency
    carry = _carry_cost(subtotal, pf_cfg)
    total_cost = subtotal + carry
    sale = gfa * sale_psf_val
    profit = sale - total_cost
    roi = ((sale - total_cost) / total_cost * 100.0) if total_cost > 0 else 0.0
    avg_unit_sf_val = gfa / units if units else gfa
    return {
        "name": envelope.label,
        "zone_code": envelope.zone_code,
        "is_overlay": envelope.is_overlay,
        "units": units,
        "total_gfa": int(round(gfa)),
        "avg_unit_sf": int(round(avg_unit_sf_val)),
        "hard_cost": int(round(hard)),
        "soft_cost": int(round(soft)),
        "land_basis": int(round(land)),
        "permit_fees": permit_total,
        "permit_fee_lines": permit_lines,
        "contingency": int(round(contingency)),
        "carry_cost": int(round(carry)),
        "total_cost": int(round(total_cost)),
        "sale_price": int(round(sale)),
        "profit": int(round(profit)),
        "margin_pct": round((profit / sale * 100.0) if sale > 0 else 0.0, 1),
        "cost_per_sf": int(round(total_cost / gfa)) if gfa > 0 else None,
        "sale_per_sf": int(round(sale / gfa)) if gfa > 0 else None,
        "sale_per_unit": int(round(sale / units)) if units else None,
        "cost_per_unit": int(round(total_cost / units)) if units else None,
        "roi_pct": round(max(-99.0, min(99.0, roi)), 1),
        "qualifies": envelope.qualifies,
        "max_far": envelope.max_far,
        "notes": envelope.rationale or "Envelope from live zoning stack",
    }


def _site_snapshot(data: BriefData) -> dict[str, Any]:
    pi = data.property_info
    lot_reg = pi.lot_size_sqft if pi and pi.lot_size_sqft else None
    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "owner": pi.owner_name if pi else None,
        "year_built": pi.year_built if pi else None,
        "building_type": pi.building_type if pi else None,
        "assessed_value": _assessed_value(data),
        "lot_sqft_gis": data.parcel.area_sqft,
        "lot_sqft_regulatory": lot_reg,
        "finished_area_sqft": pi.finished_area_sqft if pi else None,
        "last_sale_price": pi.last_sale_price if pi else None,
        "last_sale_date": pi.last_sale_date if pi else None,
        "primary_zone": data.primary_zone_code,
        "primary_overlay": data.primary_overlay_code,
        "verdict_class": data.headline_verdict_class.replace("v-", ""),
        "verdict_text": data.headline_verdict_text,
    }


def _constraints_summary(data: BriefData) -> list[dict[str, str]]:
    rows = []
    for c in data.wraparound:
        rows.append({
            "label": c.label,
            "status": c.status,
            "status_label": _STATUS_LABEL.get(c.status, c.status),
            "detail": c.detail,
        })
    if not rows:
        rows.append({
            "label": "Wraparound stack",
            "status": "clear",
            "status_label": "Clear",
            "detail": "No historic, flood, wetland, or non-compliance hits in TownEye Gold.",
        })
    return rows


def _market_section(
    data: BriefData,
    pf_cfg: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    market = ctx.get("market") or {}
    exit_pricing = ctx.get("exit_pricing") or {}
    assessed = _assessed_value(data)
    return {
        **market,
        "zipcode": ctx.get("zipcode"),
        "months_of_inventory": market.get("months_supply"),
        "assessed_value": assessed,
        "indicative_sale_psf": exit_pricing.get("sale_psf_used") or float(pf_cfg["sale_psf"]),
        "indicative_hard_cost_psf": float(pf_cfg["hard_cost_psf"]),
        "exit_pricing": exit_pricing,
    }


def _envelope_rows(data: BriefData) -> list[dict[str, Any]]:
    rows = []
    for e in data.envelopes:
        rows.append({
            "label": e.label,
            "max_far": e.max_far,
            "max_gfa_sqft": e.max_gfa_sqft,
            "qualifies": e.qualifies,
            "height_max_ft": e.height_max_ft,
            "rationale": e.rationale,
        })
    return rows


def _land_mult_label(mult: float) -> str:
    if mult < 0.995:
        return "Land −10%"
    if mult > 1.005:
        return "Land +10%"
    return "Land base"


def _hard_mult_label(mult: float) -> str:
    if mult < 0.995:
        return "Hard −10%"
    if mult > 1.005:
        return "Hard +10%"
    return "Hard base"


def _irr_grid(scenario: dict[str, Any], pf_cfg: dict[str, Any]) -> dict[str, Any]:
    """3 land × 2 hard project ROI matrix for the primary scenario."""
    gfa = float(scenario.get("total_gfa") or 0)
    base_land = float(scenario.get("land_basis") or 0)
    if gfa <= 0:
        return {"columns": [], "rows": []}

    hard_psf = float(pf_cfg["hard_cost_psf"])
    sale_psf = float(scenario.get("sale_per_sf") or pf_cfg["sale_psf"])
    soft_pct = float(pf_cfg["soft_cost_pct"])
    contingency_pct = float(pf_cfg.get("contingency_pct", 0.05))
    grid = pf_cfg.get("irr_grid") or {}
    land_mults = list(grid.get("land_price_multiples") or [0.90, 1.00, 1.10])
    hard_mults = list(grid.get("hard_cost_multiples") or [0.90, 1.10])
    permit_total, _ = compute_permit_fees(gfa, pf_cfg.get("permit_fees") or [])

    columns = [_land_mult_label(m) for m in land_mults]
    rows: list[dict[str, Any]] = []
    for hm in hard_mults:
        cells: list[float] = []
        for lm in land_mults:
            land = base_land * lm
            hard = gfa * hard_psf * hm
            soft = hard * soft_pct
            contingency = hard * contingency_pct
            subtotal = hard + soft + land + permit_total + contingency
            carry = _carry_cost(subtotal, pf_cfg)
            total = subtotal + carry
            sale = gfa * sale_psf
            roi = ((sale - total) / total * 100.0) if total > 0 else 0.0
            cells.append(round(max(-99.0, min(99.0, roi)), 1))
        rows.append({"label": _hard_mult_label(hm), "cells": cells})
    return {"columns": columns, "rows": rows}


def _sensitivity_rows(scenario: dict[str, Any], pf_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Flat sensitivity list derived from IRR grid corners."""
    grid = _irr_grid(scenario, pf_cfg)
    if not grid.get("rows"):
        return []
    flat: list[dict[str, Any]] = []
    for row in grid["rows"]:
        for col, roi in zip(grid["columns"], row["cells"]):
            flat.append({"case": f"{row['label']} · {col}", "roi_pct": roi})
    return flat


def _pick_primary_scenario(scenarios: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not scenarios:
        return None
    overlay = [s for s in scenarios if s.get("is_overlay")]
    pool = overlay or scenarios

    def _score(item: dict[str, Any]) -> float:
        equity = item.get("equity_returns") or {}
        em = equity.get("equity_multiple")
        if em is not None:
            return float(em)
        return float(item.get("roi_pct") or -999)

    return max(pool, key=_score)


def _executive_summary(
    data: BriefData,
    primary: dict[str, Any] | None,
    pf_cfg: dict[str, Any],
    exit_pricing: dict[str, Any],
    verdict: dict[str, Any],
    overlay_delta: dict[str, Any] | None,
) -> str:
    if primary is None:
        return "Indicative economics could not be anchored to a buildable envelope."
    units = primary.get("units", "—")
    gfa = _fmt_int(primary.get("total_gfa"))
    name = primary.get("name", "Primary scenario")
    equity = primary.get("equity_returns") or {}
    em = equity.get("equity_multiple", "—")
    irr = equity.get("equity_irr_pct", "—")
    sale_psf = exit_pricing.get("sale_psf_used", pf_cfg["sale_psf"])
    uplift = ""
    if overlay_delta and overlay_delta.get("profit_delta") is not None:
        uplift = (
            f" Overlay election adds {_fmt_money(overlay_delta['profit_delta'])} profit vs "
            f"{overlay_delta.get('base_scenario')} base case."
        )
    return (
        f"{verdict.get('label', 'Indicative screening')}. Recommended regime: {name} "
        f"(~{units} units / {gfa} sf GFA). Exit modeled at ${int(float(sale_psf)):,}/sf "
        f"({exit_pricing.get('method', 'town config')}). "
        f"Indicative {em}× equity multiple, {irr}% annualized equity IRR "
        f"at {int(float((pf_cfg.get('investor_financing') or {}).get('ltc_pct', 0.70)) * 100)}% LTC."
        f"{uplift} Validate land basis and comps before investment committee."
    )


def _enrich_payload(data: BriefData, payload: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    pf_cfg = _pf_cfg(data, overrides)
    o = overrides or {}
    pctx = _load_proforma_context(data, pf_cfg, overrides)
    scenarios = payload.get("scenarios") or _build_scenarios(data, pf_cfg, pctx)
    for scenario in scenarios:
        if not scenario.get("equity_returns"):
            scenario["equity_returns"] = _scenario_equity_returns(scenario, pf_cfg)
    primary = _pick_primary_scenario(scenarios)
    constraints = _constraints_summary(data)
    overlay_delta = _overlay_economics_delta(scenarios, primary)
    verdict = _investor_verdict(primary, constraints, pf_cfg)
    exit_pricing = pctx["exit_pricing"]
    land_source = pctx["land_source"]
    fin = pf_cfg.get("financing") or {}
    inv = pf_cfg.get("investor_financing") or {}
    permit_lines = primary.get("permit_fee_lines") if primary else []
    comps = pctx["comps"]
    market = _market_section(data, pf_cfg, pctx)
    sensitivity_grid = _irr_grid(primary, pf_cfg) if primary else {"columns": [], "rows": []}

    return {
        **payload,
        "report_kind": "investor_feasibility",
        "prepared_on": (data.inputs.prepared_on or date.today()).isoformat(),
        "site_snapshot": _site_snapshot(data),
        "market": market,
        "comps": comps,
        "exit_pricing": exit_pricing,
        "constraints": constraints,
        "envelopes": _envelope_rows(data),
        "scenarios": scenarios,
        "primary_scenario": primary.get("name") if primary else None,
        "overlay_economics": overlay_delta,
        "investor_verdict": verdict,
        "investor_exhibit": _investor_exhibit(
            data, primary, exit_pricing, land_source, verdict, overlay_delta, constraints,
        ),
        "executive_summary": _executive_summary(
            data, primary, pf_cfg, exit_pricing, verdict, overlay_delta,
        ),
        "irr_grid": sensitivity_grid,
        "return_sensitivity": sensitivity_grid,
        "sensitivity_detail": _sensitivity_rows(primary, pf_cfg) if primary else [],
        "assumptions": payload.get("assumptions") or [
            f"Hard cost ${float(pf_cfg['hard_cost_psf']):,.0f}/sf"
            + (" <strong>(User override)</strong>" if "hard_cost_psf" in o else " (town config)"),
            f"Soft costs {int(float(pf_cfg['soft_cost_pct']) * 100)}% of hard"
            + (" <strong>(User override)</strong>" if "soft_cost_pct" in o else ""),
            f"Construction contingency {int(float(pf_cfg.get('contingency_pct', 0.05)) * 100)}% of hard",
            f"Land basis {_fmt_money(pctx['land_basis'])} — {land_source}"
            + (" <strong>(User override)</strong>" if o.get("acquisition_price") or o.get("land_basis_mode") else ""),
            f"Exit pricing ${float(exit_pricing['sale_psf_used']):,.0f}/sf GFA — {exit_pricing['method']}"
            + (" <strong>(User override)</strong>" if "sale_psf" in o else ""),
            f"New-construction premium {int(float(pf_cfg.get('new_construction_premium_pct', 0.40)) * 100)}% applied to resale comps",
            f"Equity model: {int(float(inv.get('ltc_pct', 0.70)) * 100)}% LTC on construction, "
            f"{int(fin.get('construction_months', 14))} mo build + {int(inv.get('sellout_months', 6))} mo sellout",
            f"Unit count derived from GFA ÷ {int(pf_cfg['avg_unit_sf'])} sf average unit size"
            + (" <strong>(User override)</strong>" if "avg_unit_sf" in o else ""),
            *([f"Permit fees (town schedule): {', '.join(l['label'] for l in permit_lines)}"]
              if permit_lines else []),
            f"Financing carry {float(fin.get('annual_carry_pct', 0)) * 100:.1f}% × "
            f"{fin.get('construction_months', 14)} mo construction"
            + (" <strong>(User override)</strong>" if "financing" in o else ""),
            *(
                [f"Town median sale (Gold zip {pctx.get('zipcode') or 'town'}): "
                 f"{_fmt_money(market.get('median_sale_price'))}"]
                if market.get("median_sale_price")
                else []
            ),
            *(
                [f"Comparable sales median (CAMA, {comps.get('radius_mi')} mi): "
                 f"{_fmt_money(comps.get('median_ppsf'))}/sf resale"]
                if comps.get("median_ppsf")
                else []
            ),
            "Zoning envelopes sourced from same stack as Buildability Brief",
        ],
        "data_sources": payload.get("data_sources") or [
            "TownEye Gold parcel + property.parquet",
            "Buildability envelope math (Buildability Brief stack)",
            "market-trends.parquet (zip MLS aggregates)",
            "Assessor/CAMA comparable sales (property.parquet)",
        ],
    }


def _proforma_fallback(data: BriefData, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    pf_cfg = _pf_cfg(data, overrides)
    pctx = _load_proforma_context(data, pf_cfg, overrides)
    scenarios = _build_scenarios(data, pf_cfg, pctx)
    primary = _pick_primary_scenario(scenarios)
    rois = [float(s["roi_pct"]) for s in scenarios]
    mid = rois[len(rois) // 2] if rois else 12.0
    payload = {
        "headline": data.headline_verdict_text,
        "parcel_id": data.parcel.parcel_id,
        "lot_sqft": data.parcel.area_sqft,
        "primary_zone": data.primary_zone_code,
        "primary_overlay": data.primary_overlay_code,
        "assessed_value": _assessed_value(data),
        "scenarios": scenarios,
        "sensitivity": {
            "low": round(max(-99.0, mid - 6.0), 1),
            "mid": round(mid, 1),
            "high": round(min(99.0, mid + 8.0), 1),
        },
        "fallback": True,
    }
    return _enrich_payload(data, payload, overrides)


def _brief_context(data: BriefData) -> str:
    zones = ", ".join(h.code for h in data.base_zoning_hits[:3]) or "—"
    overlays = ", ".join(h.code for h in data.overlay_zoning_hits[:3]) or "none"
    env_lines = []
    for e in data.envelopes:
        env_lines.append(
            f"  {e.label}: lot={_fmt_int(e.lot_sqft)} sf, max_far={e.max_far}, "
            f"max_gfa={_fmt_int(e.max_gfa_sqft) if e.max_gfa_sqft else 'unbounded/indicative'}, "
            f"qualifies={e.qualifies}, rationale={e.rationale}",
        )
    assessed = _assessed_value(data)
    zipcode = _zip_from_address(data.parcel.address)
    ctx = _load_market_metrics(data.inputs.town_slug, zipcode)
    return f"""Parcel: {data.parcel.address} ({data.parcel.parcel_id})
Lot size: {_fmt_int(data.parcel.area_sqft)} sf
Base zone(s): {zones}
Overlay(s): {overlays}
Zoning verdict: {data.headline_verdict_text}
Assessed value: {_fmt_money(assessed)}
Finished area: {_fmt_int(data.property_info.finished_area_sqft if data.property_info else None)} sf
Town market context: {ctx}

Buildable envelopes (anchor scenario GFA/units to these — do not exceed max GFA):
{chr(10).join(env_lines) if env_lines else '  (none computed)'}
"""


def _normalize_scenarios(payload: dict[str, Any], data: BriefData, overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    raw = payload.get("scenarios") or []
    if not isinstance(raw, list) or not raw:
        return _proforma_fallback(data, overrides)["scenarios"]

    pf_cfg = _pf_cfg(data, overrides)
    pctx = _load_proforma_context(data, pf_cfg, overrides)
    land_basis = float(pctx["land_basis"])
    sale_psf = float(pctx["exit_pricing"]["sale_psf_used"])
    envelopes = data.envelopes or []
    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(raw[:3]):
        if not isinstance(item, dict):
            continue
        anchor = envelopes[i] if i < len(envelopes) else (envelopes[0] if envelopes else None)
        if anchor is not None:
            cap_gfa = _indicative_gfa(anchor, data)
            gfa = item.get("total_gfa")
            try:
                gfa = float(gfa) if gfa is not None else cap_gfa
            except (TypeError, ValueError):
                gfa = cap_gfa
            gfa = min(gfa, cap_gfa * 1.15) if cap_gfa > 0 else gfa
            units = item.get("units")
            try:
                units = int(units) if units is not None else _units_from_gfa(
                    gfa, float(pf_cfg["avg_unit_sf"]),
                )
            except (TypeError, ValueError):
                units = _units_from_gfa(gfa, float(pf_cfg["avg_unit_sf"]))
            units = min(units, max(1, _units_from_gfa(gfa, float(pf_cfg["avg_unit_sf"])) + 1))
            rebuilt = _scenario_from_envelope(
                anchor, data, pf_cfg, land_basis=land_basis, sale_psf=sale_psf,
            )
            item = {
                **rebuilt,
                **item,
                "total_gfa": int(round(gfa)),
                "units": units,
                "name": item.get("name") or rebuilt["name"],
            }
            item["equity_returns"] = _scenario_equity_returns(item, pf_cfg)
        normalized.append(item)
    return normalized or _proforma_fallback(data, overrides)["scenarios"]


def generate_proforma(data: BriefData, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = _proforma_fallback(data, overrides)
    if not get_settings().anthropic_api_key.strip():
        return fallback

    pf_cfg = _pf_cfg(data, overrides)
    o = overrides or {}

    prompt = f"""Build a development pro forma JSON for a Massachusetts infill developer.
Use ONLY the parcel/zoning facts below — scenarios must match envelope math (do not exceed max GFA).

{_brief_context(data)}

Cost/sale assumptions ({'user overrides applied' if o else 'pilot'}):
- Hard cost ~${float(pf_cfg['hard_cost_psf']):,.0f}/sf
- Soft costs ~{int(float(pf_cfg['soft_cost_pct']) * 100)}% of hard; land basis from assessed value shown above
- Indicative new-construction sale ~${float(pf_cfg['sale_psf']):,.0f}/sf GFA for this submarket

Return JSON with keys:
headline (string, one line),
scenarios (array of exactly 3 objects: name, units, total_gfa, hard_cost, soft_cost, land_basis, total_cost, sale_price, roi_pct, notes),
assumptions (array of strings citing real parcel/zoning facts),
sensitivity (object: low, mid, high roi_pct numbers),
data_sources (array of strings).
"""
    raw = generate_json_report("You are a MA development analyst for TownEye.", prompt)
    if raw.get("error") or raw.get("fallback") or "scenarios" not in raw:
        return fallback

    merged = {
        **fallback,
        **{k: v for k, v in raw.items() if k not in ("scenarios", "fallback", "site_snapshot")},
        "scenarios": _normalize_scenarios(raw, data, overrides),
        "fallback": False,
    }
    return _enrich_payload(data, merged, overrides)


import io
import csv

def proforma_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    
    # 1. Site Info
    snap = payload.get("site_snapshot") or {}
    writer.writerow(["--- SITE SNAPSHOT ---"])
    writer.writerow(["Address", snap.get("address", "")])
    writer.writerow(["Parcel ID", snap.get("parcel_id", "")])
    writer.writerow(["Lot SqFt (GIS)", snap.get("lot_sqft_gis", "")])
    writer.writerow(["Primary Zone", snap.get("primary_zone", "")])
    writer.writerow([])
    
    # 2. Scenarios
    writer.writerow(["--- DEVELOPMENT SCENARIOS ---"])
    scenarios = payload.get("scenarios") or []
    if scenarios:
        headers = ["Scenario", "Units", "Total GFA", "Avg Unit SF", "Land Basis", "Hard Cost", "Soft Cost", "Permit Fees", "Carry Cost", "Total Cost", "Sale Price", "Profit", "Margin %", "ROI %", "Notes"]
        writer.writerow(headers)
        for s in scenarios:
            writer.writerow([
                s.get("name", ""),
                s.get("units", ""),
                s.get("total_gfa", ""),
                s.get("avg_unit_sf", ""),
                s.get("land_basis", ""),
                s.get("hard_cost", ""),
                s.get("soft_cost", ""),
                s.get("permit_fees", ""),
                s.get("carry_cost", ""),
                s.get("total_cost", ""),
                s.get("sale_price", ""),
                s.get("profit", ""),
                s.get("margin_pct", ""),
                s.get("roi_pct", ""),
                s.get("notes", "")
            ])
    writer.writerow([])
    
    # 3. Assumptions
    writer.writerow(["--- ASSUMPTIONS ---"])
    for a in (payload.get("assumptions") or []):
        import re
        clean_a = re.sub(r'<[^>]+>', '', a)
        writer.writerow([clean_a])
        
    return buf.getvalue()

def _verdict_block(snapshot: dict[str, Any]) -> str:
    vc = snapshot.get("verdict_class") or "yellow"
    css = {"green": "v-green", "yellow": "v-yellow", "red": "v-red"}.get(vc, "v-yellow")
    return f'<div class="verdict {css}">{snapshot.get("verdict_text", "")}</div>'


import base64

def render_proforma_html(payload: dict[str, Any], address: str) -> str:
    snap = payload.get("site_snapshot") or {}
    market = payload.get("market") or {}
    scenarios = payload.get("scenarios") or []
    constraints = payload.get("constraints") or []
    envelopes = payload.get("envelopes") or []
    assumptions = payload.get("assumptions") or []
    sources = payload.get("data_sources") or []
    primary_name = payload.get("primary_scenario")
    prepared = payload.get("prepared_on") or date.today().isoformat()

    exhibit = payload.get("investor_exhibit") or {}
    verdict = payload.get("investor_verdict") or {}
    comps = payload.get("comps") or {}
    exit_pricing = payload.get("exit_pricing") or market.get("exit_pricing") or {}

    comp_rows = ""
    for c in comps.get("rows") or []:
        comp_rows += f"""<tr>
          <td>{c.get('address', '—')}</td>
          <td class="num">{int(c.get('distance_ft', 0)):,} ft</td>
          <td class="num">{_fmt_money(c.get('sale_price'))}</td>
          <td>{c.get('sale_date', '—')}</td>
          <td class="num">{_fmt_int(c.get('finished_sf'))} sf</td>
          <td class="num">{_fmt_money(c.get('price_per_sf'))}/sf</td>
        </tr>"""

    verdict_css = {"pursue": "v-green", "caution": "v-yellow", "pass": "v-red"}.get(
        verdict.get("rating", ""), "v-yellow",
    )
    exhibit_block = f"""
<h2>Investor Feasibility Exhibit</h2>
<div class="verdict {verdict_css}"><strong>{verdict.get('label', 'Indicative screening')}</strong></div>
<p class="exec">{exhibit.get('investor_thesis') or payload.get('executive_summary', '')}</p>
<table class="kv">
<tr><td>Recommended regime</td><td><strong>{exhibit.get('recommended_regime') or '—'}</strong></td></tr>
<tr><td>Scale</td><td class="num">{exhibit.get('units') or '—'} units · {_fmt_int(exhibit.get('total_gfa'))} sf GFA</td></tr>
<tr><td>Equity required</td><td class="num">{_fmt_money(exhibit.get('equity_required'))}</td></tr>
<tr><td>Equity profit (indicative)</td><td class="num">{_fmt_money(exhibit.get('equity_profit'))}</td></tr>
<tr><td>Equity multiple</td><td class="num"><strong>{exhibit.get('equity_multiple', '—')}×</strong></td></tr>
<tr><td>Equity IRR (annualized)</td><td class="num"><strong>{exhibit.get('equity_irr_pct', '—')}%</strong></td></tr>
<tr><td>Project ROI</td><td class="num">{exhibit.get('project_roi_pct', '—')}%</td></tr>
<tr><td>Exit pricing</td><td class="num">{_fmt_money(exhibit.get('exit_sale_psf'))}/sf — {exit_pricing.get('method', '—')}</td></tr>
<tr><td>Land basis</td><td class="num">{_fmt_money(exhibit.get('land_basis'))} ({exhibit.get('land_basis_source', '—')})</td></tr>
</table>"""

    csv_text = proforma_to_csv(payload)
    csv_b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
    csv_href = f"data:text/csv;base64,{csv_b64}"
    
    # --- scenario tables ---
    scenario_rows = ""
    for s in scenarios:
        is_primary = s.get("name") == primary_name
        row_cls = ' class="primary"' if is_primary else ""
        scenario_rows += f"""<tr{row_cls}>
          <td>{s.get('name', '—')}{' <span class="tag">Recommended</span>' if is_primary else ''}</td>
          <td class="num">{s.get('units', '—')}</td>
          <td class="num">{_fmt_int(s.get('total_gfa'))}</td>
          <td class="num">{_fmt_money(s.get('land_basis'))}</td>
          <td class="num">{_fmt_money(s.get('hard_cost'))}</td>
          <td class="num">{_fmt_money(s.get('soft_cost'))}</td>
          <td class="num">{_fmt_money(s.get('permit_fees'))}</td>
          <td class="num">{_fmt_money(s.get('carry_cost'))}</td>
          <td class="num">{_fmt_money(s.get('total_cost'))}</td>
          <td class="num">{_fmt_money(s.get('sale_price'))}</td>
          <td class="num">{_fmt_money(s.get('profit'))}</td>
          <td class="num"><strong>{s.get('roi_pct', '—')}%</strong></td>
        </tr>"""
        note = s.get("notes")
        if note:
            scenario_rows += f'<tr><td colspan="12" class="small">{note}</td></tr>'

    unit_rows = ""
    for s in scenarios:
        unit_rows += f"""<tr>
          <td>{s.get('name', '—')}</td>
          <td class="num">{_fmt_int(s.get('avg_unit_sf'))} sf</td>
          <td class="num">{_fmt_money(s.get('sale_per_unit'))}</td>
          <td class="num">{_fmt_money(s.get('cost_per_unit'))}</td>
          <td class="num">{_fmt_money(s.get('sale_per_sf'))}/sf</td>
          <td class="num">{_fmt_money(s.get('cost_per_sf'))}/sf</td>
          <td class="num">{_fmt_pct(s.get('margin_pct'))}</td>
        </tr>"""

    env_rows = ""
    for e in envelopes:
        qual = "Yes" if e.get("qualifies") else ("No" if e.get("qualifies") is False else "—")
        gfa = _fmt_int(e.get("max_gfa_sqft")) if e.get("max_gfa_sqft") else "Indicative / unbounded"
        env_rows += f"""<tr>
          <td>{e.get('label', '—')}</td>
          <td>{e.get('max_far') if e.get('max_far') is not None else '—'}</td>
          <td class="num">{gfa}</td>
          <td>{qual}</td>
        </tr>"""

    constraint_rows = ""
    for c in constraints:
        pill = {"clear": "ok", "caution": "wn", "flagged": "fl"}.get(c.get("status", ""), "")
        constraint_rows += f"""<tr>
          <td>{c.get('label', '—')}</td>
          <td><span class="{pill}">{c.get('status_label', '—')}</span></td>
          <td>{c.get('detail', '—')}</td>
        </tr>"""

    irr = payload.get("irr_grid") or {}
    irr_header = "".join(f"<th>{c}</th>" for c in irr.get("columns") or [])
    irr_body = ""
    for row in irr.get("rows") or []:
        cells = "".join(f'<td class="num"><strong>{v}%</strong></td>' for v in row.get("cells") or [])
        irr_body += f"<tr><td>{row.get('label', '—')}</td>{cells}</tr>"

    lot_line = _fmt_int(snap.get("lot_sqft_regulatory") or snap.get("lot_sqft_gis"))
    gis_line = (
        f' &nbsp;·&nbsp; <span class="lbl">GIS polygon:</span> {_fmt_int(snap.get("lot_sqft_gis"))} sf'
        if snap.get("lot_sqft_regulatory") and snap.get("lot_sqft_gis")
        else ""
    )

    fallback_note = ""
    if payload.get("fallback"):
        fallback_note = (
            '<p class="note">Pilot screening model from TownEye Gold envelopes. '
            "Not a lender-grade pro forma — validate costs and sales with local comps.</p>"
        )

    overlay_bit = ""
    if snap.get("primary_overlay"):
        overlay_bit = f" + {snap.get('primary_overlay')} overlay"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Development Pro Forma — {address}</title>
<style>
  body{{font-family:Georgia,'Times New Roman',serif;font-size:13px;line-height:1.55;color:#1a1a1a;max-width:780px;margin:36px auto;padding:0 28px;background:#fff}}
  h1{{font-size:22px;margin:0 0 4px;color:#0b2545;letter-spacing:.5px}}
  h2{{font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#0b2545;border-bottom:2px solid #0b2545;padding:18px 0 4px;margin:18px 0 10px}}
  .hd{{border-bottom:1px solid #ccc;padding-bottom:10px;margin-bottom:8px}}
  .meta{{font-size:11px;color:#555;margin-top:6px}}
  .verdict{{padding:10px 14px;margin:10px 0 12px;border-radius:4px;font-weight:bold}}
  .v-green{{background:#dff1d6;color:#1a5b22;border-left:6px solid #1a7a1a}}
  .v-yellow{{background:#fff3cf;color:#7a5a00;border-left:6px solid #c89800}}
  .v-red{{background:#fadcdc;color:#7a1a1a;border-left:6px solid #a02020}}
  table{{width:100%;border-collapse:collapse;margin:6px 0 10px;font-size:12.5px}}
  th{{background:#0b2545;color:#fff;text-align:left;padding:6px 9px;font-size:11.5px;letter-spacing:.5px}}
  td{{padding:5px 9px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#f7f9fc}}
  tr.primary td{{background:#f0f4fa;font-weight:600}}
  .kv td:first-child{{color:#555;width:34%}}
  .num{{font-variant-numeric:tabular-nums}}
  .small{{font-size:11px;color:#555}}
  .note{{font-size:12px;color:#555;font-style:italic;margin:8px 0}}
  .btn{{display:inline-block;margin:8px 0 12px;padding:8px 14px;background:#0b2545;color:#fff;text-decoration:none;border-radius:4px;font-size:12px}}
  .ok{{color:#1a7a1a;font-weight:bold}}
  .wn{{color:#a06b00;font-weight:bold}}
  .fl{{color:#a02020;font-weight:bold}}
  .tag{{display:inline-block;background:#0b2545;color:#fff;font-size:9px;padding:1px 6px;border-radius:8px;margin-left:4px;letter-spacing:.4px;vertical-align:middle}}
  .lbl{{color:#555}}
  ul{{margin:6px 0;padding-left:20px}}
  .footnote{{font-size:10.5px;color:#555;margin-top:16px;border-top:1px solid #ddd;padding-top:10px}}
  .exec{{margin:10px 0 14px;color:#222}}
  .logo-header {{ position: absolute; top: 20px; right: 28px; height: 32px; opacity: 0.8; }}
</style></head><body>

<div class="hd" style="position: relative;">
  <img src="https://demo.towneye.ai/logo.png" alt="TownEye Logo" class="logo-header" />
  <h1>Investor Feasibility Report</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{address}</div>
  <div class="meta">Prepared on {prepared} &nbsp;·&nbsp; Parcel ID {snap.get('parcel_id', payload.get('parcel_id', '—'))}</div>
</div>

{exhibit_block}

<h2>1 · Investment Thesis</h2>
{_verdict_block(snap) if snap.get('verdict_text') else ''}
<p class="exec">{payload.get('executive_summary', payload.get('headline', ''))}</p>
<a class="btn" href="{csv_href}" download="proforma-{snap.get('parcel_id', 'parcel')}.csv">Download Scenario Math (CSV)</a>
{fallback_note}

<h2>2 · Site Snapshot</h2>
<table class="kv">
<tr><td>Address</td><td>{snap.get('address', address)}</td></tr>
<tr><td>Owner</td><td>{snap.get('owner') or '—'}</td></tr>
<tr><td>Year built / type</td><td>{snap.get('year_built') or '—'} {('(' + str(snap.get('building_type')) + ')') if snap.get('building_type') else ''}</td></tr>
<tr><td>Assessed value</td><td class="num">{_fmt_money(snap.get('assessed_value'))}</td></tr>
<tr><td>Last sale</td><td>{_fmt_money(snap.get('last_sale_price'))}{(' (' + str(snap.get('last_sale_date')) + ')') if snap.get('last_sale_date') else ''}</td></tr>
<tr><td>Lot size</td><td class="num">{lot_line} sf{gis_line}</td></tr>
<tr><td>Existing GFA</td><td class="num">{'—' if not snap.get('finished_area_sqft') else _fmt_int(snap.get('finished_area_sqft')) + ' sf'}</td></tr>
<tr><td>Zoning stack</td><td><strong>{snap.get('primary_zone') or '—'}</strong>{overlay_bit}</td></tr>
</table>

<h2>3 · Exit Pricing &amp; Market Context</h2>
<table class="kv">
<tr><td>Modeled exit $/sf</td><td class="num"><strong>{_fmt_money(exit_pricing.get('sale_psf_used') or market.get('indicative_sale_psf'))}/sf</strong></td></tr>
<tr><td>Exit pricing method</td><td>{exit_pricing.get('method', '—')}</td></tr>
<tr><td>CAMA comp median (resale)</td><td class="num">{_fmt_money(exit_pricing.get('comp_median_resale_psf'))}/sf</td></tr>
<tr><td>CAMA comp adjusted (new construction)</td><td class="num">{_fmt_money(exit_pricing.get('comp_adjusted_new_psf'))}/sf</td></tr>
<tr><td>Zip trend $/sf (Gold)</td><td class="num">{_fmt_money(exit_pricing.get('zip_price_per_sqft'))}/sf</td></tr>
<tr><td>Town median sale (Gold)</td><td class="num">{_fmt_money(market.get('median_sale_price'))}</td></tr>
<tr><td>Median days on market</td><td class="num">{market.get('median_dom') if market.get('median_dom') is not None else '—'}</td></tr>
<tr><td>Months of inventory</td><td class="num">{market.get('months_of_inventory') if market.get('months_of_inventory') is not None else market.get('months_supply') or '—'}</td></tr>
<tr><td>Pilot hard cost assumption</td><td class="num">{_fmt_money(market.get('indicative_hard_cost_psf'))}/sf</td></tr>
</table>
{f'<h3>Comparable sales (CAMA, {comps.get("radius_mi", "—")} mi)</h3><p class="small">{comps.get("note", "")}</p><table><tr><th>Address</th><th>Distance</th><th>Sale</th><th>Date</th><th>Size</th><th>$/sf</th></tr>{comp_rows}</table><p class="small">Median comp: <strong>{_fmt_money(comps.get("median_ppsf"))}/sf</strong></p>' if comp_rows else '<p class="small">No CAMA comparable sales in radius — exit pricing uses zip trend and town config.</p>'}

<h2>4 · Zoning Envelopes (from Buildability stack)</h2>
<table>
<tr><th>Regime</th><th>Max FAR</th><th>Max GFA</th><th>Qualifies</th></tr>
{env_rows or "<tr><td colspan='4'>No envelopes computed</td></tr>"}
</table>

<h2>5 · Development Scenarios — Full Cost Stack</h2>
<table>
<tr><th>Scenario</th><th>Units</th><th>GFA</th><th>Land</th><th>Hard</th><th>Soft</th><th>Permits</th><th>Carry</th><th>Total</th><th>Sale</th><th>Profit</th><th>ROI</th></tr>
{scenario_rows or "<tr><td colspan='12'>No scenarios computed</td></tr>"}
</table>

<h2>6 · Unit Economics</h2>
<table>
<tr><th>Scenario</th><th>Avg unit</th><th>Sale / unit</th><th>Cost / unit</th><th>Sale / sf</th><th>Cost / sf</th><th>Margin</th></tr>
{unit_rows or "<tr><td colspan='7'>No scenarios computed</td></tr>"}
</table>

<h2>7 · Constraints &amp; Risk</h2>
<table>
<tr><th>Layer</th><th>Status</th><th>Detail</th></tr>
{constraint_rows}
</table>

<h2>8 · Return Sensitivity — Primary Scenario ({primary_name or '—'})</h2>
<p class="small">3 land-basis × 2 hard-cost scenarios (project ROI %). Exit $/sf held at modeled value.</p>
<table>
<tr><th>Hard cost →</th>{irr_header or '<th>—</th>'}</tr>
{irr_body or "<tr><td colspan='4'>IRR matrix not computed</td></tr>"}
</table>

<h2>9 · Assumptions &amp; Sources</h2>
<ul>{''.join(f'<li>{a}</li>' for a in assumptions)}</ul>
<p class="small">Data sources: {', '.join(sources) if sources else 'TownEye Gold'}.</p>

<p class="footnote">
  Indicative screening model — not investment, tax, or lending advice. Ground-truth zoning
  math and development options are in the Buildability Brief. Sale pricing is not MLS-connected
  in the pilot; confirm with local comps and contractor bids before committing capital.
</p>
</body></html>"""


def generate_proforma_html(
    town_slug: str,
    parcel_id: str,
    prepared_for: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> str:
    data = collect_brief_data(town_slug, parcel_id, prepared_for)
    payload = generate_proforma(data, overrides)
    return render_proforma_html(payload, data.parcel.address)
