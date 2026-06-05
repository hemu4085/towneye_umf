"""Lender Due Diligence Pack — comprehensive collateral regulatory dossier."""

from __future__ import annotations

import html
import re
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.risk import generate_risk_json
from backend.services.zoning import generate_zoning_json
from backend.utils.parcel_lookup import _load_town_config, _town_display_name
from core.spatial import OverlayHit
from reports.buildability_brief import BriefData, BuildableEnvelope

_STATUS_PILL = {
    "clear": ("#1a7a1a", "Clear"),
    "caution": ("#a06b00", "Caution"),
    "flagged": ("#a02020", "Flagged"),
    "pass": ("#1a7a1a", "Pass"),
    "review": ("#a06b00", "Review"),
    "escalate": ("#a02020", "Escalate"),
}


def _esc(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _pill(status: str, label: str | None = None) -> str:
    color, default = _STATUS_PILL.get(status, ("#555", status.title()))
    text = label or default
    return (
        f'<span style="color:{color};font-weight:bold;text-transform:uppercase">'
        f"{_esc(text)}</span>"
    )


def _zip_from_address(address: str | None) -> str | None:
    if not address:
        return None
    match = re.search(r"\b(\d{5})\b", address)
    return match.group(1) if match else None


def _attr(hit: OverlayHit, *keys: str) -> Any:
    attrs = hit.attributes or {}
    for key in keys:
        if key in attrs and attrs[key] not in (None, ""):
            return attrs[key]
    return None


def _truthy_sfha(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().upper() in {"T", "TRUE", "1", "YES", "Y"}


def _owner_entity_type(owner_name: str | None, keywords: list[str]) -> str:
    if not owner_name:
        return "Unknown"
    upper = owner_name.upper()
    for kw in keywords:
        token = kw.upper()
        if re.search(rf"\b{re.escape(token)}\b", upper):
            return "Organization / Trust"
    return "Individual"


def _cama_values(data: BriefData) -> dict[str, Any]:
    raw = (data.parcel_metadata_extras or {}).get("raw_attributes") or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _env_hits_by_category(hits: list[OverlayHit]) -> dict[str, list[OverlayHit]]:
    buckets: dict[str, list[OverlayHit]] = {
        "flood_effective": [],
        "flood_preliminary": [],
        "wetland": [],
        "other": [],
    }
    for hit in hits:
        category = str(_attr(hit, "category", "source_layer_name") or hit.layer or "").lower()
        if "prelim" in category or "preliminary" in category:
            buckets["flood_preliminary"].append(hit)
        elif "flood" in category or _attr(hit, "sfha_flag", "SFHA_TF") is not None:
            buckets["flood_effective"].append(hit)
        elif "wetland" in category or "wet" in category:
            buckets["wetland"].append(hit)
        else:
            code = str(hit.code or "").upper()
            if code in {"AE", "AH", "AO", "A", "VE", "X", "D"} or _truthy_sfha(_attr(hit, "sfha_flag")):
                buckets["flood_effective"].append(hit)
            elif code:
                buckets["wetland"].append(hit)
            else:
                buckets["other"].append(hit)
    return buckets


def _source_slugs(town_cfg: dict[str, Any], *keys: str) -> list[str]:
    mappings = town_cfg.get("source_mappings") or {}
    return [str(mappings[k]) for k in keys if mappings.get(k)]


def _analyze_flood(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    hits = data.raw_stack.environmental_overlay
    buckets = _env_hits_by_category(hits)
    effective = buckets["flood_effective"]
    preliminary = buckets["flood_preliminary"]
    wetlands = buckets["wetland"]

    primary_zone = None
    primary_subtype = None
    sfha = False
    static_bfe = None
    for hit in effective:
        zone = _attr(hit, "zone_code", "FLD_ZONE", "fld_zone") or hit.code
        if zone:
            primary_zone = str(zone).strip().upper()
        subtype = _attr(hit, "zone_subtype", "ZONE_SUBTY", "zone_subty")
        if subtype:
            primary_subtype = str(subtype)
        if _truthy_sfha(_attr(hit, "sfha_flag", "SFHA_TF", "sfha_tf")):
            sfha = True
        bfe = _attr(hit, "static_bfe", "STATIC_BFE", "static_bfe")
        if bfe is not None:
            try:
                static_bfe = float(bfe)
            except (TypeError, ValueError):
                pass

    if not effective and not wetlands:
        status = "clear"
        risk_level = "NONE"
        insurance_required = False
        note = (
            "No effective flood-zone or wetland polygon overlaps this parcel centroid. "
            "FEMA NFHL point query would typically classify this as Zone X (minimal hazard). "
            "Flood insurance is NOT required by federally-backed lenders."
        )
    elif sfha or (primary_zone and primary_zone not in {"X", "C", "D"} and primary_zone[0] in {"A", "V"}):
        status = "flagged"
        risk_level = "HIGH"
        insurance_required = True
        note = (
            f"This parcel overlaps a Special Flood Hazard Area (Zone {primary_zone or 'SFHA'}). "
            "Flood insurance IS required for federally-backed mortgages. "
            "Obtain an elevation certificate if BFE is disputed."
        )
    elif primary_zone and primary_zone.startswith("X"):
        status = "caution"
        risk_level = "MODERATE"
        insurance_required = False
        note = (
            f"Parcel is in FEMA Zone {primary_zone} (0.2% annual chance / moderate risk). "
            "Flood insurance is recommended but not required for federally-backed lenders."
        )
    elif wetlands:
        status = "caution"
        risk_level = "MODERATE"
        insurance_required = False
        note = (
            "Wetland overlay intersects this parcel. Flood insurance may not be required, "
            "but wetland permitting can restrict improvements and delay collateral repairs."
        )
    else:
        status = "caution"
        risk_level = "MODERATE"
        insurance_required = False
        note = "Environmental overlay hit detected — review flood/wetland detail rows below."

    prelim_zone = None
    map_change = False
    if preliminary:
        prelim_zone = _attr(preliminary[0], "zone_code", "fld_zone", "FLD_ZONE") or preliminary[0].code
        if primary_zone and prelim_zone and str(prelim_zone).upper() != str(primary_zone).upper():
            map_change = True

    rows: list[dict[str, str]] = []
    for hit in effective + preliminary + wetlands:
        rows.append({
            "layer": hit.layer or _attr(hit, "category", "source_layer_name") or "environmental",
            "zone": str(_attr(hit, "zone_code", "FLD_ZONE", "fld_zone") or hit.code or "—"),
            "subtype": str(_attr(hit, "zone_subtype", "ZONE_SUBTY", "zone_subty") or "—"),
            "sfha": "Yes" if _truthy_sfha(_attr(hit, "sfha_flag", "SFHA_TF")) else "No",
            "bfe": str(_attr(hit, "static_bfe", "STATIC_BFE") or "—"),
            "label": str(hit.label or "—"),
        })

    return {
        "status": status,
        "risk_level": risk_level,
        "insurance_required": insurance_required,
        "note": note,
        "primary_zone": primary_zone,
        "primary_subtype": primary_subtype,
        "static_bfe": static_bfe,
        "map_change_warning": map_change,
        "preliminary_zone": str(prelim_zone) if prelim_zone else None,
        "wetland_count": len(wetlands),
        "rows": rows,
        "sources": _source_slugs(
            town_cfg, "environmental_overlay", "climate_resilience",
        ) or ["environmental-overlay", "fema-flood-maps"],
    }


def _analyze_historic(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    macris_hits = data.raw_stack.macris
    local_hits = data.raw_stack.local_historic
    hist_cfg = town_cfg.get("historic_resources") or {}

    designations: list[str] = []
    names: list[str] = []
    rows: list[dict[str, str]] = []

    for hit in macris_hits + local_hits:
        desig = _attr(hit, "designation", "DESIGNATIO", "legend", "Designated") or hit.layer
        name = hit.label or _attr(hit, "historic_name", "HISTORIC_N", "Hist_Name", "district", "Name")
        if desig:
            designations.append(str(desig))
        if name:
            names.append(str(name))
        rows.append({
            "source": "MACRIS (state)" if hit in macris_hits else "Local historic GIS",
            "designation": str(desig or "—"),
            "name": str(name or "—"),
            "constructed": str(_attr(hit, "construction_date", "CONSTRUCTI", "Cnstr_Date") or "—"),
            "style": str(_attr(hit, "architectural_style", "ARCHITECTU", "Architect") or "—"),
            "id": str(_attr(hit, "mhcn", "MHCN", "MHC_id") or hit.code or "—"),
        })

    in_lhd = any(
        "LHD" in d.upper() or "LOCAL HISTORIC" in d.upper() or "LOCAL_HISTORIC" in d.upper()
        for d in designations
    ) or any("local_historic" in (h.layer or "").lower() for h in local_hits)

    if not rows:
        status = "clear"
        note = (
            "No MACRIS inventory point/area overlap and no local historic district boundary "
            "intersects this parcel. No Certificate of Appropriateness workflow expected."
        )
    elif in_lhd:
        status = "flagged"
        note = (
            "This property IS in a Local Historic District. Exterior alterations visible from "
            "a public way require a Certificate of Appropriateness BEFORE any building permit "
            "is issued. Budget additional time and design review for renovation loans."
        )
    else:
        status = "caution"
        note = (
            "Historic resource overlap detected (MACRIS inventory or town historic layer). "
            "Demolition or substantial exterior work may trigger demolition-delay review even "
            "if not in a binding Local Historic District."
        )

    return {
        "status": status,
        "in_lhd": in_lhd,
        "hit_count": len(rows),
        "designations": sorted(set(designations)),
        "names": names[:6],
        "note": note,
        "macris_search_url": hist_cfg.get("macris_search_url", ""),
        "ahc_url": hist_cfg.get("ahc_inventory_url", ""),
        "rows": rows,
        "sources": _source_slugs(town_cfg, "historic_resources", "local_historic")
        or ["ma-mhc-macris", "local-historic"],
    }


def _analyze_conformity(data: BriefData) -> dict[str, Any]:
    noncomp_hits = data.raw_stack.noncompliance
    prop = data.property_info
    rows: list[dict[str, str]] = []
    for hit in noncomp_hits:
        rows.append({
            "land_use_code": str(_attr(hit, "land_use_code", "LandUseCod") or "—"),
            "zone_diff": str(_attr(hit, "land_use_zone_diff", "luzndiff") or "—"),
            "status": str(hit.label or hit.layer or _attr(hit, "status") or "Non-conforming"),
        })

    nonconforming_lot = any(
        env.qualifies is False for env in data.envelopes if env.qualifies is not None
    )
    over_far = any(
        env.pct_of_far_cap is not None and env.pct_of_far_cap > 1.0 for env in data.envelopes
    )

    if rows or nonconforming_lot or over_far:
        status = "flagged" if rows else "caution"
        parts = []
        if rows:
            parts.append(f"{len(rows)} land-use / zoning non-compliance polygon(s)")
        if nonconforming_lot:
            parts.append("lot below base-zone minimum size")
        if over_far:
            parts.append("existing GFA exceeds FAR cap (legal non-conforming envelope)")
        note = (
            "Collateral legal-use review required: " + "; ".join(parts) + ". "
            "Pre-existing non-conforming uses may continue but expansion or tear-down rebuild "
            "typically must conform to current zoning."
        )
    else:
        status = "clear"
        note = (
            "No land-use non-compliance polygon overlap and dimensional minimums appear satisfied "
            "under resolved zoning rules."
        )

    return {
        "status": status,
        "note": note,
        "noncomp_rows": rows,
        "assessor_use": (
            f"{prop.luc or ''} — {prop.luc_description}".strip(" —")
            if prop and (prop.luc or prop.luc_description)
            else None
        ),
        "nonconforming_lot": nonconforming_lot,
        "over_far": over_far,
    }


def _load_market_metrics(town_slug: str, zipcode: str | None) -> dict[str, Any]:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.is_file():
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}

    def _latest(metric: str) -> float | None:
        sub = df[df["metric_name"] == metric].copy()
        if sub.empty:
            return None
        if zipcode and "geo_value" in sub.columns:
            z = sub[sub["geo_value"] == zipcode]
            if not z.empty:
                sub = z
        sub["observation_date"] = pd.to_datetime(sub["observation_date"], utc=True, errors="coerce")
        sub = sub.dropna(subset=["observation_date"]).sort_values("observation_date")
        if sub.empty:
            return None
        val = sub.iloc[-1]["metric_value"]
        return None if pd.isna(val) else float(val)

    return {
        "median_sale_price": _latest("MEDIAN_SALE_PRICE"),
        "median_dom": _latest("AVG_DAYS_ON_MARKET"),
        "months_supply": _latest("MONTHS_OF_SUPPLY"),
        "price_per_sqft": _latest("PRICE_PER_SQFT"),
        "zip": zipcode,
    }


def _estimate_market_value(assessed: float, town_slug: str, zipcode: str | None) -> dict[str, Any] | None:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.is_file() or assessed <= 0:
        return None
    df = pd.read_parquet(path)
    if df.empty or "metric_name" not in df.columns:
        return None

    sp = df[df["metric_name"] == "MEDIAN_SALE_PRICE"].copy()
    if sp.empty:
        return None
    if zipcode and "geo_value" in sp.columns:
        z = sp[sp["geo_value"] == zipcode]
        if not z.empty:
            sp = z
    sp["observation_date"] = pd.to_datetime(sp["observation_date"], utc=True, errors="coerce")
    sp = sp.dropna(subset=["observation_date"]).sort_values("observation_date")
    if len(sp) < 2:
        return None

    latest = sp.iloc[-1]
    latest_val = float(latest["metric_value"])
    latest_date = latest["observation_date"]
    target = latest_date - pd.DateOffset(months=12)
    sp["_delta"] = (sp["observation_date"] - target).abs()
    yr_ago = sp.loc[sp["_delta"].idxmin()]
    yr_ago_val = float(yr_ago["metric_value"])
    if yr_ago_val <= 0:
        return None

    factor = latest_val / yr_ago_val
    return {
        "estimated_value": round(assessed * factor, -2),
        "appreciation_1yr_pct": round((factor - 1) * 100, 1),
        "as_of": str(latest_date.date()),
        "method": "Assessed value × zip median sale price YoY trend (market-trends.parquet)",
    }


def _overall_grade(flood: dict, historic: dict, conformity: dict, risk: dict) -> tuple[str, str]:
    statuses = [flood["status"], historic["status"], conformity["status"], risk["overall_status"]]
    if "flagged" in statuses:
        return "escalate", "One or more material collateral flags require senior review."
    if "caution" in statuses:
        return "review", "Mixed collateral signals — standard underwriting with documented exceptions."
    return "pass", "No material regulatory overlays flagged at parcel resolution."


def _facts_rows(data: BriefData, town_cfg: dict[str, Any]) -> list[tuple[str, str]]:
    p = data.parcel
    prop = data.property_info
    cama = _cama_values(data)
    org_keywords = town_cfg.get("party_type_org_keywords") or []
    rows: list[tuple[str, str]] = [
        ("Street address", p.address or "—"),
        ("Parcel ID", p.parcel_id),
        ("Town", _town_display_name(data.inputs.town_slug)),
    ]

    short_id = cama.get("Short_id") or cama.get("MAP_PAR_ID")
    if short_id:
        rows.append(("Map–block–lot", str(short_id)))

    if prop and prop.owner_name:
        entity = _owner_entity_type(prop.owner_name, org_keywords)
        rows.append(("Owner of record", f"{prop.owner_name} ({entity})"))

    if prop and prop.book_page:
        rows.append(("Deed reference (book/page)", prop.book_page))
    elif cama.get("LS_BOOK") or cama.get("LS_PAGE"):
        rows.append((
            "Deed reference (book/page)",
            f"{cama.get('LS_BOOK', '—')} / {cama.get('LS_PAGE', '—')}",
        ))

    if prop and prop.year_built:
        style = f" ({prop.building_type})" if prop.building_type else ""
        rows.append(("Year built", f"{prop.year_built}{style}"))

    if prop and (prop.beds or prop.baths):
        rows.append(("Bedrooms / bathrooms", f"{prop.beds or '—'} / {prop.baths or '—'}"))

    if prop and prop.finished_area_sqft:
        rows.append(("Finished living area", f"{_fmt_int(prop.finished_area_sqft)} sf (assessor)"))

    lot_parts = []
    if prop and prop.lot_size_sqft:
        lot_parts.append(f"{_fmt_int(prop.lot_size_sqft)} sf assessor (regulatory)")
    if p.area_sqft:
        lot_parts.append(f"{_fmt_int(p.area_sqft)} sf GIS polygon")
    if lot_parts:
        rows.append(("Lot size", " · ".join(lot_parts)))

    if p.longest_edge_ft:
        rows.append(("Longest parcel edge (frontage proxy)", f"{_fmt_int(p.longest_edge_ft)} ft"))

    if prop and prop.last_sale_date:
        rows.append((
            "Last arm's-length sale",
            f"{_fmt_money(prop.last_sale_price)} on {prop.last_sale_date}",
        ))
    elif cama.get("LS_DATE") or cama.get("LS_PRICE"):
        rows.append((
            "Last sale (CAMA)",
            f"{_fmt_money(cama.get('LS_PRICE'))} on {cama.get('LS_DATE', '—')}",
        ))

    land_val = cama.get("LAND_VAL")
    bldg_val = cama.get("BLDG_VAL")
    total_val = (prop.assessed_value if prop else None) or cama.get("TOTAL_VAL")
    if land_val or bldg_val:
        rows.append((
            "Assessed value (land / building / total)",
            f"{_fmt_money(land_val)} / {_fmt_money(bldg_val)} / {_fmt_money(total_val)}",
        ))
    elif total_val:
        rows.append(("Total assessed value", _fmt_money(total_val)))

    if prop and (prop.luc_description or prop.luc):
        rows.append(("Assessor use code", f"{prop.luc or ''} — {prop.luc_description or ''}".strip(" —")))

    rows.append(("GIS centroid", f"{p.centroid_lat:.6f}, {p.centroid_lon:.6f}"))
    return rows


def _envelope_rows(envelopes: list[BuildableEnvelope]) -> str:
    if not envelopes:
        return "<tr><td colspan='7'>No envelope math — zoning rules missing for resolved hits.</td></tr>"
    rows = ""
    for e in envelopes:
        pct = _fmt_pct(e.pct_of_far_cap * 100) if e.pct_of_far_cap is not None else "—"
        qual = (
            "Yes" if e.qualifies else ("No — NON-CONFORMING" if e.qualifies is False else "—")
        )
        rows += f"""<tr>
          <td><strong>{_esc(e.label)}</strong></td>
          <td>{_fmt_int(e.lot_sqft)} sf</td>
          <td>{e.max_far if e.max_far is not None else "—"}</td>
          <td>{_fmt_int(e.max_gfa_sqft)} sf</td>
          <td>{_fmt_int(e.existing_gfa_sqft)} sf</td>
          <td>{_fmt_int(e.expansion_room_sqft)} sf</td>
          <td>{pct}</td>
          <td>{_esc(qual)}</td>
        </tr>
        <tr><td colspan="8" class="small">{_esc(e.rationale)}</td></tr>"""
    return rows


def _zoning_detail_rows(zoning: dict) -> str:
    zones = (zoning.get("base_zones") or []) + (zoning.get("overlay_zones") or [])
    if not zones:
        return "<tr><td colspan='8'>No machine-readable zoning rules for resolved zone codes.</td></tr>"
    rows = ""
    for z in zones:
        uses = ", ".join((z.get("allowed_uses") or [])[:8]) or "—"
        rows += f"""<tr>
          <td><strong>{_esc(z.get('zone_code'))}</strong>{' (overlay)' if z.get('is_overlay') else ''}</td>
          <td>{_esc(z.get('description') or '—')}</td>
          <td class="small">{_esc(uses)}</td>
          <td>{z.get('max_far') if z.get('max_far') is not None else '—'}</td>
          <td>{_fmt_int(z.get('min_lot_sqft'))}</td>
          <td>{z.get('max_height_ft') if z.get('max_height_ft') is not None else '—'}</td>
          <td>{z.get('setback_front_ft') if z.get('setback_front_ft') is not None else '—'}</td>
          <td>{z.get('setback_side_ft') if z.get('setback_side_ft') is not None else '—'} / {z.get('setback_rear_ft') if z.get('setback_rear_ft') is not None else '—'}</td>
        </tr>"""
    return rows


def generate_lender_html(data: BriefData, prepared_for: str | None) -> str:
    town_slug = data.inputs.town_slug
    town_cfg = _load_town_config(town_slug)
    risk = generate_risk_json(data)
    zoning = generate_zoning_json(data)
    flood = _analyze_flood(data, town_cfg)
    historic = _analyze_historic(data, town_cfg)
    conformity = _analyze_conformity(data)
    grade, grade_note = _overall_grade(flood, historic, conformity, risk)

    address = data.parcel.address or data.inputs.parcel_id
    zipcode = _zip_from_address(address)
    assessed = None
    if data.property_info and data.property_info.assessed_value:
        assessed = float(data.property_info.assessed_value)
    if assessed is None:
        cama = _cama_values(data)
        if cama.get("TOTAL_VAL"):
            try:
                assessed = float(cama["TOTAL_VAL"])
            except (TypeError, ValueError):
                pass

    market = _load_market_metrics(town_slug, zipcode)
    avm = _estimate_market_value(assessed, town_slug, zipcode) if assessed else None

    report_date = data.report_date_text
    recipient = prepared_for or data.inputs.prepared_for

    facts_html = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in _facts_rows(data, town_cfg)
    )

    risk_rows = "".join(
        f"""<tr>
          <td>{_esc(c['label'])}</td>
          <td>{_pill(c['status'], c['status_label'])}</td>
          <td>{_esc(c['detail'])}</td>
          <td class="small">{_esc(c['source'])}</td>
        </tr>"""
        for c in risk["constraints"]
    )

    flood_rows = "".join(
        f"""<tr>
          <td>{_esc(r['layer'])}</td>
          <td><strong>{_esc(r['zone'])}</strong></td>
          <td>{_esc(r['subtype'])}</td>
          <td>{_esc(r['sfha'])}</td>
          <td>{_esc(r['bfe'])}</td>
          <td>{_esc(r['label'])}</td>
        </tr>"""
        for r in flood["rows"]
    ) or "<tr><td colspan='6'>No environmental overlay intersections.</td></tr>"

    historic_rows = "".join(
        f"""<tr>
          <td>{_esc(r['source'])}</td>
          <td>{_esc(r['designation'])}</td>
          <td>{_esc(r['name'])}</td>
          <td>{_esc(r['constructed'])}</td>
          <td>{_esc(r['style'])}</td>
          <td>{_esc(r['id'])}</td>
        </tr>"""
        for r in historic["rows"]
    ) or "<tr><td colspan='6'>No historic resource intersections.</td></tr>"

    noncomp_rows = "".join(
        f"""<tr>
          <td>{_esc(r['land_use_code'])}</td>
          <td>{_esc(r['zone_diff'])}</td>
          <td>{_esc(r['status'])}</td>
        </tr>"""
        for r in conformity["noncomp_rows"]
    )

    map_warning = ""
    if flood["map_change_warning"]:
        map_warning = (
            f"<p class='callout warn'><strong>Preliminary map change:</strong> effective zone "
            f"{_esc(flood['primary_zone'])} vs preliminary {_esc(flood['preliminary_zone'])} — "
            "future flood insurance requirements may change.</p>"
        )

    avm_block = ""
    if avm:
        ratio = (assessed / avm["estimated_value"]) if assessed and avm["estimated_value"] else None
        avm_block = f"""
        <tr><th>Indicative market value (trend-adjusted)</th>
            <td>{_fmt_money(avm['estimated_value'])} as of { _esc(avm['as_of']) }
            ({_fmt_pct(avm['appreciation_1yr_pct'])} zip YoY)</td></tr>"""
        if ratio:
            avm_block += f"""
        <tr><th>Assessed / indicative market</th><td>{_fmt_pct(ratio * 100)}</td></tr>"""

    market_rows = ""
    if market:
        market_rows = f"""
        <tr><th>Zip median sale price</th><td>{_fmt_money(market.get('median_sale_price'))} ({_esc(zipcode or 'town')})</td></tr>
        <tr><th>Avg days on market</th><td>{_fmt_int(market.get('median_dom'))} days</td></tr>
        <tr><th>Months of supply</th><td>{market.get('months_supply') if market.get('months_supply') is not None else '—'}</td></tr>
        <tr><th>Median price / sqft (zip)</th><td>{_fmt_money(market.get('price_per_sqft'))}</td></tr>"""

    hist_links = ""
    if historic["macris_search_url"]:
        hist_links += f'<a href="{_esc(historic["macris_search_url"])}">MACRIS map</a>'
    if historic["ahc_url"]:
        if hist_links:
            hist_links += " · "
        hist_links += f'<a href="{_esc(historic["ahc_url"])}">Town Historical Commission</a>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lender Due Diligence Pack — {_esc(address)}</title>
<style>
  html,body{{box-sizing:border-box;margin:0;padding:0}}
  *,*::before,*::after{{box-sizing:inherit}}
  body{{font-family:'DM Sans',Arial,sans-serif;color:#0B1F3A;width:100%;max-width:none;
        padding:28px 40px;font-size:14px;line-height:1.5}}
  h1{{font-family:Georgia,serif;color:#0B1F3A;border-bottom:3px solid #C9A84C;padding-bottom:8px;margin:0 0 8px}}
  h2{{font-family:Georgia,serif;font-size:15px;letter-spacing:.5px;text-transform:uppercase;color:#0B1F3A;
      border-bottom:2px solid #C9A84C;padding-bottom:4px;margin:28px 0 12px}}
  h3{{font-size:14px;color:#0B1F3A;margin:16px 0 8px}}
  .hero{{background:#0B1F3A;color:#F5F0E8;padding:20px 24px;border-radius:8px;margin-bottom:24px}}
  .hero h1{{color:#C9A84C;border:none;margin:0 0 6px}}
  .hero .meta{{font-size:12px;opacity:.9}}
  .grade{{font-size:1.05rem;font-weight:600;color:#C9A84C;margin-top:8px}}
  table{{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:13px;table-layout:auto}}
  th{{background:#0B1F3A;color:#F5F0E8;text-align:left;padding:8px;vertical-align:top}}
  td{{padding:8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#faf9f6}}
  .facts th{{width:38%}}
  .summary-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0}}
  .summary-card{{border:1px solid #ddd;border-radius:6px;padding:12px;background:#fff}}
  .summary-card h3{{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.4px}}
  .callout{{padding:10px 14px;border-radius:4px;margin:10px 0}}
  .callout.ok{{background:#edf7ed;border-left:4px solid #1a7a1a}}
  .callout.warn{{background:#fff8e6;border-left:4px solid #c89800}}
  .callout.bad{{background:#fdecec;border-left:4px solid #a02020}}
  .small{{font-size:11.5px;color:#555}}
  .page-break{{page-break-before:always}}
  .disclaimer{{font-size:11px;color:#666;margin-top:36px;border-top:1px solid #ccc;padding-top:12px}}
  .verdict{{padding:10px 14px;border-radius:4px;background:#f4f6fb;border-left:4px solid #0B1F3A;margin:10px 0}}
</style></head><body>

<div class="hero">
  <h1>Lender Due Diligence Pack</h1>
  <p><strong>{_esc(address)}</strong></p>
  <p class="meta">
    {f'Prepared for {_esc(recipient)} · ' if recipient else ''}
    Prepared on {_esc(report_date)} · Parcel {_esc(data.inputs.parcel_id)}
  </p>
  <p class="grade">Overall collateral grade: {_pill(grade)} — {_esc(grade_note)}</p>
</div>

<h2>1 · Executive collateral memo</h2>
<div class="summary-grid">
  <div class="summary-card">
    <h3>Flood &amp; insurability</h3>
    <p>{_pill(flood['status'])} · Zone {_esc(flood['primary_zone'] or 'X / none')}</p>
    <p class="small">{'Insurance required' if flood['insurance_required'] else 'Insurance not required (GSE)'}</p>
  </div>
  <div class="summary-card">
    <h3>Historic &amp; preservation</h3>
    <p>{_pill(historic['status'])} · {historic['hit_count']} hit(s)</p>
    <p class="small">{'LHD — COA required' if historic['in_lhd'] else 'Review historic rows'}</p>
  </div>
  <div class="summary-card">
    <h3>Legal use &amp; conformity</h3>
    <p>{_pill(conformity['status'])}</p>
    <p class="small">{_esc(conformity['assessor_use'] or 'See zoning section')}</p>
  </div>
</div>
<div class="verdict">{_esc(data.headline_verdict_text)}</div>

<h2>2 · Collateral identification</h2>
<p class="small">Assessor &amp; MassGIS CAMA fields from TownEye Gold — not a title report or MLS listing.</p>
<table class="facts">{facts_html}</table>

<h2>3 · Flood, wetland &amp; hazard insurability</h2>
<div class="callout {'bad' if flood['insurance_required'] else 'ok'}">{_esc(flood['note'])}</div>
{map_warning}
<table>
  <tr><th>Layer</th><th>Zone</th><th>Subtype</th><th>SFHA</th><th>Static BFE</th><th>Label</th></tr>
  {flood_rows}
</table>
<p class="small">Sources: {', '.join(_esc(s) for s in flood['sources'])}</p>

<h2>4 · Historic &amp; preservation overlays</h2>
<div class="callout {'bad' if historic['in_lhd'] else ('warn' if historic['rows'] else 'ok')}">{_esc(historic['note'])}</div>
{f'<p class="small">{hist_links}</p>' if hist_links else ''}
<table>
  <tr><th>Source</th><th>Designation</th><th>Name</th><th>Built</th><th>Style</th><th>ID</th></tr>
  {historic_rows}
</table>

<h2>5 · Zoning stack &amp; permitted envelope</h2>
<p><strong>Base:</strong> {_esc(', '.join(zoning.get('base_labels') or []) or '—')}
 &nbsp;·&nbsp; <strong>Overlays:</strong> {_esc(', '.join(zoning.get('overlay_labels') or []) or '—')}</p>
<table>
  <tr><th>Zone</th><th>Description</th><th>Permitted uses</th><th>Max FAR</th><th>Min lot</th><th>Max ht</th><th>Front sb</th><th>Side/rear sb</th></tr>
  {_zoning_detail_rows(zoning)}
</table>

<h3>Buildable envelope (regulatory math)</h3>
<table>
  <tr><th>Regime</th><th>Lot</th><th>FAR</th><th>Max GFA</th><th>Existing GFA</th><th>Expansion room</th><th>% of FAR cap</th><th>Qualifies</th></tr>
  {_envelope_rows(data.envelopes)}
</table>

<h2>6 · Legal use &amp; non-conformance</h2>
<div class="callout {'bad' if conformity['status'] == 'flagged' else ('warn' if conformity['status'] == 'caution' else 'ok')}">{_esc(conformity['note'])}</div>
{f'''<table><tr><th>Land use code</th><th>Zone diff</th><th>Status</th></tr>{noncomp_rows}</table>''' if noncomp_rows else '<p class="small">No land-use non-compliance polygon overlap.</p>'}

<h2>7 · Risk &amp; constraints scorecard</h2>
<p>Overall: {_pill(risk['overall_status'], risk['overall_status'].upper())}</p>
<table>
  <tr><th>Constraint</th><th>Status</th><th>Detail</th><th>Source</th></tr>
  {risk_rows}
</table>

<h2 class="page-break">8 · Collateral value &amp; market context</h2>
<p class="small">Indicative only — not an appraisal. Grounded in assessor record and town market-trends Gold data.</p>
<table class="facts">
  <tr><th>Total assessed value</th><td>{_fmt_money(assessed)}</td></tr>
  {avm_block}
  {market_rows}
</table>
{f'<p class="small">AVM method: {_esc(avm["method"])}</p>' if avm else ''}

<h2>9 · Data provenance &amp; limitations</h2>
<ul class="small">
  <li>Parcel geometry &amp; overlays: OverlayResolver on Gold parquets (parcel, zoning-overlay, environmental-overlay, macris, local-historic, noncompliance).</li>
  <li>Assessor fields: property.parquet / MassGIS L3 CAMA join (tax-assessor source).</li>
  <li>Zoning rules: zoning.parquet from town zoning bylaw JSON.</li>
  <li>Market trends: market-trends.parquet (MLS aggregates where licensed).</li>
  <li>Not included in Phase 1: tax payment status, registry liens, ISD violation orders, parcel-level MLS comps.</li>
</ul>

<p class="disclaimer">
  TownEye Lender Due Diligence Pack — informational collateral memo only. Not a loan approval,
  flood certification, appraisal, or legal opinion. Verify all flags with the municipality,
  FEMA, and title company before closing. © towneye.ai
</p>
</body></html>"""
