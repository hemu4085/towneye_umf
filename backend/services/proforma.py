"""Development Pro Forma — envelope-grounded economics + optional Claude synthesis."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.buildability import collect_brief_data
from backend.services.llm import generate_json_report
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


def _town_market_context(town_slug: str) -> dict[str, Any]:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.is_file():
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}
    row = df.iloc[-1].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in row.items()}


def _assessed_value(data: BriefData) -> float | None:
    if data.property_info is not None and data.property_info.assessed_value is not None:
        return float(data.property_info.assessed_value)
    return None


def _land_basis(data: BriefData) -> float:
    assessed = _assessed_value(data)
    if assessed is not None and assessed > 0:
        return assessed
    lot = data.parcel.area_sqft or 0.0
    return lot * 55.0


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
    for k in ["hard_cost_psf", "soft_cost_pct", "sale_psf", "avg_unit_sf"]:
        if k in overrides and overrides[k] is not None:
            merged[k] = overrides[k]
            
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
) -> dict[str, Any]:
    hard_psf = float(pf_cfg["hard_cost_psf"])
    soft_pct = float(pf_cfg["soft_cost_pct"])
    sale_psf = float(pf_cfg["sale_psf"])
    avg_unit_sf = float(pf_cfg["avg_unit_sf"])

    gfa = _indicative_gfa(envelope, data)
    units = _units_from_gfa(gfa, avg_unit_sf)
    hard = gfa * hard_psf
    soft = hard * soft_pct
    land = _land_basis(data)
    permit_total, permit_lines = compute_permit_fees(gfa, pf_cfg.get("permit_fees") or [])
    subtotal = hard + soft + land + permit_total
    carry = _carry_cost(subtotal, pf_cfg)
    total_cost = subtotal + carry
    sale = gfa * sale_psf
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
        "carry_cost": int(round(carry)),
        "total_cost": int(round(total_cost)),
        "sale_price": int(round(sale)),
        "profit": int(round(profit)),
        "margin_pct": round((profit / sale * 100.0) if sale > 0 else 0.0, 1),
        "cost_per_sf": int(round(total_cost / gfa)) if gfa > 0 else None,
        "sale_per_sf": int(round(sale / gfa)) if gfa > 0 else None,
        "sale_per_unit": int(round(sale / units)) if units else None,
        "cost_per_unit": int(round(total_cost / units)) if units else None,
        "roi_pct": round(max(-15.0, min(35.0, roi)), 1),
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


def _market_section(data: BriefData, pf_cfg: dict[str, Any]) -> dict[str, Any]:
    ctx = _town_market_context(data.inputs.town_slug)
    assessed = _assessed_value(data)
    return {
        "median_sale_price": ctx.get("median_sale_price"),
        "median_dom": ctx.get("median_dom"),
        "months_of_inventory": ctx.get("months_of_inventory"),
        "assessed_value": assessed,
        "indicative_sale_psf": float(pf_cfg["sale_psf"]),
        "indicative_hard_cost_psf": float(pf_cfg["hard_cost_psf"]),
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
    """3 land × 2 hard ROI matrix for the primary scenario (PDF Report 03)."""
    gfa = float(scenario.get("total_gfa") or 0)
    base_land = float(scenario.get("land_basis") or 0)
    if gfa <= 0:
        return {"columns": [], "rows": []}

    hard_psf = float(pf_cfg["hard_cost_psf"])
    sale_psf = float(pf_cfg["sale_psf"])
    soft_pct = float(pf_cfg["soft_cost_pct"])
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
            subtotal = hard + soft + land + permit_total
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
    return max(pool, key=lambda s: float(s.get("roi_pct") or -999))


def _executive_summary(
    data: BriefData,
    primary: dict[str, Any] | None,
    pf_cfg: dict[str, Any],
) -> str:
    if primary is None:
        return "Indicative economics could not be anchored to a buildable envelope."
    units = primary.get("units", "—")
    gfa = _fmt_int(primary.get("total_gfa"))
    roi = primary.get("roi_pct", "—")
    name = primary.get("name", "Primary scenario")
    profit = _fmt_money(primary.get("profit"))
    hard_psf = float(pf_cfg["hard_cost_psf"])
    sale_psf = float(pf_cfg["sale_psf"])
    return (
        f"Recommended path: {name}. Indicative yield ~{units} units / {gfa} sf GFA, "
        f"{profit} profit at pilot assumptions (${hard_psf:,.0f}/sf hard, "
        f"${sale_psf:,.0f}/sf sale), ~{roi}% ROI. "
        f"Entitlement and envelope math are in the Buildability Brief."
    )


def _enrich_payload(data: BriefData, payload: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    pf_cfg = _pf_cfg(data, overrides)
    o = overrides or {}
    scenarios = payload.get("scenarios") or []
    primary = _pick_primary_scenario(scenarios)
    ctx = _town_market_context(data.inputs.town_slug)
    assessed = _assessed_value(data)
    fin = pf_cfg.get("financing") or {}
    permit_lines = primary.get("permit_fee_lines") if primary else []
    return {
        **payload,
        "prepared_on": (data.inputs.prepared_on or date.today()).isoformat(),
        "site_snapshot": _site_snapshot(data),
        "market": _market_section(data, pf_cfg),
        "constraints": _constraints_summary(data),
        "envelopes": _envelope_rows(data),
        "primary_scenario": primary.get("name") if primary else None,
        "executive_summary": _executive_summary(data, primary, pf_cfg),
        "irr_grid": _irr_grid(primary, pf_cfg) if primary else {"columns": [], "rows": []},
        "sensitivity_detail": _sensitivity_rows(primary, pf_cfg) if primary else [],
        "assumptions": payload.get("assumptions") or [
            f"Hard cost ${float(pf_cfg['hard_cost_psf']):,.0f}/sf" + (' <strong style="color:#0b2545">(User override)</strong>' if "hard_cost_psf" in o else " (RSMeans MA indicative, from town config)"),
            f"Soft costs {int(float(pf_cfg['soft_cost_pct']) * 100)}% of hard construction" + (' <strong style="color:#0b2545">(User override)</strong>' if "soft_cost_pct" in o else ""),
            f"Land basis {_fmt_money(assessed) if assessed else 'lot × $55/sf assessor proxy'}",
            f"Indicative new-construction sale ${float(pf_cfg['sale_psf']):,.0f}/sf GFA" + (' <strong style="color:#0b2545">(User override)</strong>' if "sale_psf" in o else " — not MLS-calibrated"),
            f"Unit count derived from GFA ÷ {int(pf_cfg['avg_unit_sf'])} sf average unit size" + (' <strong style="color:#0b2545">(User override)</strong>' if "avg_unit_sf" in o else ""),
            *([f"Permit fees (town schedule): {', '.join(l['label'] for l in permit_lines)}"]
              if permit_lines else []),
            f"Financing carry {float(fin.get('annual_carry_pct', 0)) * 100:.1f}% × "
            f"{fin.get('construction_months', 14)} mo construction" + (' <strong style="color:#0b2545">(User override)</strong>' if "financing" in o else " (indicative)"),
            "Zoning envelopes sourced from same stack as Buildability Brief",
            *(
                [f"Town median sale (Gold): {_fmt_money(ctx.get('median_sale_price'))}"]
                if ctx.get("median_sale_price")
                else []
            ),
        ],
    }


def _proforma_fallback(data: BriefData, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    pf_cfg = _pf_cfg(data, overrides)
    envelopes = data.envelopes[:3] if data.envelopes else []
    scenarios = [_scenario_from_envelope(e, data, pf_cfg) for e in envelopes]
    if not scenarios:
        lot = data.parcel.area_sqft or 0.0
        gfa = lot * 0.5
        fake = BuildableEnvelope(
            zone_code=data.primary_zone_code or "—",
            is_overlay=False,
            label="Base (parcel area)",
            rationale="Derived from parcel area — refine with full envelope",
            lot_sqft=lot,
        )
        scenarios.append(_scenario_from_envelope(fake, data, pf_cfg))

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
            "low": round(max(-15.0, mid - 6.0), 1),
            "mid": round(mid, 1),
            "high": round(min(35.0, mid + 8.0), 1),
        },
        "data_sources": [
            "TownEye Gold parcel + property.parquet",
            "Buildability envelope math (Buildability Brief stack)",
            "market-trends.parquet (town context)",
        ],
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
    ctx = _town_market_context(data.inputs.town_slug)
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

    envelopes = data.envelopes or []
    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(raw[:3]):
        if not isinstance(item, dict):
            continue
        anchor = envelopes[i] if i < len(envelopes) else (envelopes[0] if envelopes else None)
        if anchor is not None:
            cap_gfa = _indicative_gfa(anchor, data)
            pf_cfg = _pf_cfg(data, overrides)
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
            rebuilt = _scenario_from_envelope(anchor, data, pf_cfg)
            item = {
                **rebuilt,
                **item,
                "total_gfa": int(round(gfa)),
                "units": units,
                "name": item.get("name") or rebuilt["name"],
            }
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
  <h1>Development Pro Forma</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{address}</div>
  <div class="meta">Prepared on {prepared} &nbsp;·&nbsp; Parcel ID {snap.get('parcel_id', payload.get('parcel_id', '—'))}</div>
</div>

<h2>1 · Executive Summary</h2>
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

<h2>3 · Market Context</h2>
<table class="kv">
<tr><td>Town median sale (Gold)</td><td class="num">{_fmt_money(market.get('median_sale_price'))}</td></tr>
<tr><td>Median days on market</td><td class="num">{market.get('median_dom') if market.get('median_dom') is not None else '—'}</td></tr>
<tr><td>Months of inventory</td><td class="num">{market.get('months_of_inventory') if market.get('months_of_inventory') is not None else '—'}</td></tr>
<tr><td>Pilot hard cost assumption</td><td class="num">{_fmt_money(market.get('indicative_hard_cost_psf'))}/sf</td></tr>
<tr><td>Pilot sale assumption</td><td class="num">{_fmt_money(market.get('indicative_sale_psf'))}/sf GFA</td></tr>
</table>

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

<h2>8 · IRR Matrix — Primary Scenario ({primary_name or '—'})</h2>
<p class="small">3 land-basis × 2 hard-cost scenarios (ROI %). Sale held at config sale $/sf.</p>
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
