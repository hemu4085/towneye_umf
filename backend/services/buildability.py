"""Buildability Brief service — wraps existing generator."""

from __future__ import annotations

from datetime import date
from typing import Any

from reports.buildability_brief import BriefInputs, BriefData, BuildabilityBriefGenerator, ZoningRule

from backend.config import get_settings


def get_generator(town_slug: str) -> BuildabilityBriefGenerator:
    return BuildabilityBriefGenerator(
        town_slug=town_slug,
        data_dir=get_settings().gold_data_path,
        config_dir=get_settings().config_dir,
    )


def collect_brief_data(
    town_slug: str,
    parcel_id: str,
    prepared_for: str | None = None,
) -> BriefData:
    gen = get_generator(town_slug)
    return gen.collect_data(
        BriefInputs(
            town_slug=town_slug,
            parcel_id=parcel_id,
            prepared_for=prepared_for,
            prepared_on=date.today(),
        ),
    )


def generate_buildability_html(
    town_slug: str,
    parcel_id: str,
    prepared_for: str | None = None,
) -> str:
    gen = get_generator(town_slug)
    return gen.generate(
        BriefInputs(
            town_slug=town_slug,
            parcel_id=parcel_id,
            prepared_for=prepared_for,
            prepared_on=date.today(),
        ),
    )


def _fmt_rule(rule: ZoningRule | None) -> dict[str, Any] | None:
    if rule is None:
        return None
    return {
        "zone_code": rule.zone_code,
        "description": rule.zone_description,
        "allowed_uses": rule.allowed_uses,
        "max_far": rule.max_far,
        "min_lot_sqft": rule.min_lot_sqft,
        "min_frontage_ft": rule.min_frontage_ft,
        "max_height_ft": rule.max_height_ft,
        "setback_front_ft": rule.setback_front_ft,
        "setback_side_ft": rule.setback_side_ft,
        "setback_rear_ft": rule.setback_rear_ft,
        "is_overlay": rule.is_overlay,
    }


def _fmt_envelope(env) -> dict[str, Any]:
    return {
        "zone_code": env.zone_code,
        "label": env.label,
        "is_overlay": env.is_overlay,
        "rationale": env.rationale,
        "lot_sqft": env.lot_sqft,
        "max_far": env.max_far,
        "max_gfa_sqft": env.max_gfa_sqft,
        "existing_gfa_sqft": env.existing_gfa_sqft,
        "expansion_room_sqft": env.expansion_room_sqft,
        "pct_of_far_cap": env.pct_of_far_cap,
        "height_max_ft": env.height_max_ft,
        "height_max_stories": env.height_max_stories,
        "setback_front_ft": env.setback_front_ft,
        "setback_side_ft": env.setback_side_ft,
        "setback_rear_ft": env.setback_rear_ft,
        "qualifies": env.qualifies,
        "notes": env.notes,
    }


def _as_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        f = float(v)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default


def _fmt_num(v: Any, fmt: str = ",.0f", *, empty: str = "—") -> str:
    if v is None:
        return empty
    try:
        f = float(v)
        if f != f:
            return empty
        return format(f, fmt)
    except (TypeError, ValueError):
        return empty


def _opportunity_score(data: BriefData) -> float:
    score = 5.0
    expansion = max((e.expansion_room_sqft or 0) for e in data.envelopes) if data.envelopes else 0
    if expansion > 2000:
        score += 2.0
    elif expansion > 1000:
        score += 1.5
    elif expansion > 500:
        score += 1.0
    elif expansion > 0:
        score += 0.5

    if data.has_mbta_communities_overlay:
        score += 1.0

    flagged = sum(1 for w in data.wraparound if w.status == "flagged")
    caution = sum(1 for w in data.wraparound if w.status == "caution")
    score -= flagged * 1.5
    score -= caution * 0.5

    if data.headline_verdict_class == "v-green":
        score += 0.5
    elif data.headline_verdict_class == "v-red":
        score -= 1.5

    return round(min(10.0, max(1.0, score)), 1)


def _build_insights(data: BriefData) -> list[str]:
    insights: list[str] = []
    for env in data.envelopes:
        if env.expansion_room_sqft and env.expansion_room_sqft > 0:
            insights.append(
                f"Under {env.label}: {_fmt_num(env.expansion_room_sqft)} sf expansion room — {env.rationale}",
            )
        elif env.max_gfa_sqft and env.existing_gfa_sqft and env.max_gfa_sqft > 0:
            pct = env.existing_gfa_sqft / env.max_gfa_sqft * 100
            if pct >= 90:
                insights.append(
                    f"{env.label}: at {pct:.0f}% of FAR cap — limited by-right expansion room.",
                )
        if env.pct_of_far_cap is not None and env.pct_of_far_cap < 0.5:
            insights.append(
                f"Lot utilization under {env.label} is {env.pct_of_far_cap * 100:.0f}% of FAR cap — "
                f"significant upside before dimensional maximums.",
            )

    for w in data.wraparound:
        if w.status in ("flagged", "caution"):
            insights.append(f"{w.label}: {w.detail}")

    if data.has_mbta_communities_overlay:
        insights.append(
            "MBTA Communities Act (§3A) overlay applies — by-right multi-family path may supersede "
            "base district density limits.",
        )

    seen: set[str] = set()
    deduped: list[str] = []
    for item in insights:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:8]


def _allowable_uses(data: BriefData) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for hit in data.overlay_zoning_hits + data.base_zoning_hits:
        rule = data.zoning_rules.get(hit.code or "")
        if not rule:
            continue
        for use in rule.allowed_uses:
            key = use.lower()
            if key in seen:
                continue
            seen.add(key)
            status = "By Right (overlay)" if rule.is_overlay else "By Right"
            rows.append({"use": use, "status": status, "zone_code": rule.zone_code})
    return rows


def _dimensional_controls(data: BriefData) -> list[dict[str, str]]:
    """Map primary envelope + rules into metric/limit/current rows for the executive UI."""
    primary = next((e for e in data.envelopes if e.is_overlay), None)
    if primary is None and data.envelopes:
        primary = data.envelopes[0]
    if primary is None:
        return []

    rule = data.zoning_rules.get(primary.zone_code)
    prop = data.property_info
    rows: list[dict[str, str]] = []

    if rule and rule.max_height_ft is not None:
        rows.append({
            "metric": "Max Height",
            "limit": f"{_fmt_num(rule.max_height_ft, '.0f')} ft",
            "current": f"{prop.year_built} (existing)" if prop and prop.year_built else "existing",
        })
    if rule and rule.setback_front_ft is not None:
        rows.append({
            "metric": "Front Yard Setback",
            "limit": f"{_fmt_num(rule.setback_front_ft, '.0f')} ft",
            "current": "—",
        })
    if rule and rule.setback_side_ft is not None:
        rows.append({
            "metric": "Side Yard Setback",
            "limit": f"{_fmt_num(rule.setback_side_ft, '.0f')} ft",
            "current": "—",
        })
    if primary.max_far is not None:
        current = "—"
        if primary.existing_gfa_sqft is not None and primary.max_gfa_sqft:
            pct = primary.existing_gfa_sqft / primary.max_gfa_sqft * 100
            current = f"{_fmt_num(primary.existing_gfa_sqft)} sf ({pct:.0f}% of cap)"
        rows.append({
            "metric": "Max FAR",
            "limit": f"{_fmt_num(primary.max_far, '.2f')}",
            "current": current,
        })
    if primary.max_gfa_sqft is not None:
        current = f"{_fmt_num(primary.existing_gfa_sqft)} sf" if primary.existing_gfa_sqft is not None else "—"
        rows.append({
            "metric": "Max GFA",
            "limit": f"{_fmt_num(primary.max_gfa_sqft)} sf",
            "current": current,
        })
    if primary.expansion_room_sqft is not None and primary.expansion_room_sqft > 0:
        rows.append({
            "metric": "Expansion Room",
            "limit": f"+{_fmt_num(primary.expansion_room_sqft)} sf",
            "current": "available by-right",
        })
    return rows


def _overlay_narrative(data: BriefData) -> str:
    if data.has_overlay_election:
        mbta = (
            " It qualifies for by-right multi-family development under the "
            "MBTA Communities Act (§3A) overlay."
            if data.has_mbta_communities_overlay
            else ""
        )
        return (
            f"This parcel sits under {len(data.base_zoning_hits)} base district(s) "
            f"and {len(data.overlay_zoning_hits)} overlay district(s).{mbta} "
            "The buildable envelope under the overlay is materially larger than under the base "
            "zone — see §3 and §4 for the side-by-side analysis."
        )
    return (
        "This parcel sits under base zoning only — no §3A multi-family overlay applies. "
        "The buildable envelope is governed entirely by the base district's dimensional "
        "controls; see §3 and §4."
    )


def _dimensional_comparison(data: BriefData) -> dict[str, Any]:
    columns = [e.label for e in data.envelopes] + ["This parcel"]
    rows: list[dict[str, Any]] = []

    def _zone_cell(env, field: str) -> str:
        rule = data.zoning_rules.get(env.zone_code)
        if field == "min_lot_sqft":
            if env.is_overlay and env.zone_code not in data.zoning_rules:
                return "None required"
            if rule and rule.min_lot_sqft is not None:
                return f"{_fmt_num(rule.min_lot_sqft)} sf"
            return "—"
        if field == "min_frontage_ft":
            if env.is_overlay and env.zone_code not in data.zoning_rules:
                return "None required"
            if rule and rule.min_frontage_ft:
                return f"{rule.min_frontage_ft} ft"
            return "—"
        if field == "max_height":
            if env.height_max_ft is not None:
                return f"{_fmt_num(env.height_max_ft, '.0f')} ft"
            return "see overlay text"
        if field == "max_far":
            if env.is_overlay and env.max_far is None:
                return "None required"
            if env.max_far is not None:
                return f"{_fmt_num(env.max_far, '.2f')}"
            return "—"
        if field == "setback_front":
            if env.setback_front_ft is not None:
                return f"{_fmt_num(env.setback_front_ft, '.0f')} ft"
            return "—"
        if field == "qualifies":
            if env.qualifies is True:
                return "qualifies"
            if env.qualifies is False:
                return "non-conforming"
            return "not specified"
        return "—"

    lot_sqft = data.envelopes[0].lot_sqft if data.envelopes else None
    longest = data.parcel.longest_edge_ft

    for standard, field, parcel_val in [
        ("Min. lot size", "min_lot_sqft", f"{_fmt_num(lot_sqft)} sf" if lot_sqft is not None else "—"),
        (
            "Min. frontage",
            "min_frontage_ft",
            f"~{_fmt_num(longest, '.0f')} ft (longest edge)" if longest is not None else "—",
        ),
        ("Max. height", "max_height", "existing"),
        ("Max. FAR", "max_far", "—"),
        ("Front setback", "setback_front", "existing"),
        ("Lot qualifies?", "qualifies", "—"),
    ]:
        values = [_zone_cell(env, field) for env in data.envelopes]
        values.append(parcel_val)
        rows.append({"standard": standard, "values": values})

    return {"columns": columns, "rows": rows}


def _envelope_calcs(data: BriefData) -> list[dict[str, Any]]:
    calcs: list[dict[str, Any]] = []
    for env in data.envelopes:
        lines = [
            f"Lot size: {_fmt_num(env.lot_sqft)} sf",
            f"Max FAR: {_fmt_num(env.max_far, '.2f')}" if env.max_far is not None else "Max FAR: none required",
            (
                f"Max GFA permitted: {_fmt_num(env.max_gfa_sqft)} sf"
                if env.max_gfa_sqft is not None
                else "Max GFA permitted: unbounded by FAR"
            ),
        ]
        if env.existing_gfa_sqft is not None:
            lines.append(f"Existing GFA (assessor): {_fmt_num(env.existing_gfa_sqft)} sf")
            if env.expansion_room_sqft is not None:
                lines.append(f"By-right expansion room: {_fmt_num(env.expansion_room_sqft)} sf")
            if env.pct_of_far_cap is not None:
                lines.append(f"Pct of FAR cap: {env.pct_of_far_cap * 100:.1f} %")
        if env.height_max_ft is not None:
            stories = env.height_max_stories or "—"
            lines.append(
                f"Max height: {_fmt_num(env.height_max_ft, '.0f')} ft (~{stories} stories)"
            )
        if env.setback_front_ft is not None:
            lines.append(f"Front setback: {_fmt_num(env.setback_front_ft, '.0f')} ft")
        if env.qualifies is False:
            lines.append("Lot qualifies: NO — does not meet min-lot-size for this regime")
        elif env.qualifies is True:
            lines.append("Lot qualifies: YES")
        calcs.append({
            "label": env.label,
            "rationale": env.rationale,
            "lines": lines,
            "notes": env.notes,
        })
    return calcs


def _layer_match(hit, *patterns: str) -> bool:
    attrs = hit.attributes or {}
    hay = " ".join(
        str(x or "")
        for x in (hit.layer, hit.code, hit.label, attrs.get("category"), attrs.get("layer"))
    ).lower()
    return any(p.lower() in hay for p in patterns)


def _filter_hits(hits: list, *patterns: str) -> list:
    return [h for h in hits if _layer_match(h, *patterns)]


def _fema_detail(hits: list) -> str:
    if not hits:
        return "Zone X — minimal hazard, no flood ins. required"
    h = hits[0]
    zone = h.code or (h.attributes or {}).get("zone_code") or "—"
    subtype = h.label or (h.attributes or {}).get("zone_subtype") or ""
    parts = [f"Zone {zone}"]
    if subtype and str(subtype).upper() != str(zone).upper():
        parts.append(str(subtype))
    return " — ".join(parts)


def _build_detailed_wraparound(data: BriefData) -> list[dict[str, Any]]:
    """Layer-by-layer wraparound rows matching the investor-grade 29 Walnut brief."""
    stack = data.raw_stack
    prop = data.property_info
    env = stack.environmental_overlay
    local = stack.local_historic
    macris = stack.macris
    noncomp = stack.noncompliance

    rows: list[dict[str, Any]] = []

    def _gis_row(label: str, hits: list, source: str, clear_detail: str) -> dict[str, Any]:
        if hits:
            labels = sorted({(h.label or h.code or h.layer or "feature") for h in hits})
            return {
                "label": label,
                "status": "flagged",
                "detail": f"{len(hits)} hit(s): {', '.join(labels)}",
                "source": source,
            }
        return {"label": label, "status": "clear", "detail": clear_detail, "source": source}

    fema_hits = _filter_hits(env, "flood-effective", "nfhl", "fema")
    rows.append({
        "label": "FEMA flood zone",
        "status": "flagged" if fema_hits else "clear",
        "detail": _fema_detail(fema_hits),
        "source": "FEMA NFHL MapServer layer 28, point-in-polygon at centroid",
    })

    rows.append(_gis_row(
        "Arlington flood overlay",
        [
            h for h in env
            if _layer_match(h, "arlington_flood", "flood_zones")
            and not _layer_match(h, "preliminary", "2023")
        ],
        "Arlington GIS — Arlington_Flood_Zones",
        "No overlap",
    ))

    rows.append(_gis_row(
        "2023 FEMA flood remap",
        _filter_hits(env, "flood-preliminary", "preliminary", "2023"),
        "Arlington GIS — Flood_Zones_Preliminary_Changes_2023",
        "Not affected",
    ))

    rows.append(_gis_row(
        "Wetlands / conservation buffer",
        _filter_hits(env, "wetland", "wetlands", "conservation"),
        "Arlington GIS — ArlingtonMA_Wetlands",
        "No overlap",
    ))

    macris_poly = [h for h in macris if (h.geometry_type or "").lower() in ("polygon", "multipolygon")]
    rows.append(_gis_row(
        "MACRIS — historic district polygon",
        macris_poly,
        "MA Historical Commission MACRIS polygon layer",
        "Not in district",
    ))

    macris_pts = [h for h in macris if h not in macris_poly]
    rows.append(_gis_row(
        "MACRIS — inventoried building (30m buffer)",
        macris_pts,
        "MA Historical Commission MACRIS point layer",
        "Not inventoried",
    ))

    rows.append(_gis_row(
        "Local Historic District",
        _filter_hits(local, "local_historic_district", "local historic"),
        "Arlington GIS — Local_Historic_District",
        "Not in any of Arlington's 7 LHDs",
    ))
    rows.append(_gis_row(
        "National Historic District",
        _filter_hits(local, "national_historic"),
        "Arlington GIS — National_Historic_District",
        "Not in any NHD",
    ))
    rows.append(_gis_row(
        "Historic Overlay District",
        _filter_hits(local, "historic_overlay", "historicoverlay"),
        "Arlington GIS — Historic_Overlay_Districts",
        "Not subject",
    ))
    rows.append(_gis_row(
        "AHC Inventory",
        _filter_hits(local, "historic_commission_inventory", "commission inventory"),
        "Arlington GIS — Historic_Commission_Inventory_view",
        "Not on inventory",
    ))
    rows.append(_gis_row(
        "Open zoning violations",
        noncomp,
        "Arlington GIS — LandUse_NonCompliance",
        "None on parcel",
    ))

    if prop and prop.year_built and prop.year_built < 1978:
        rows.append({
            "label": "Lead paint disclosure",
            "status": "caution",
            "detail": f"Pre-1978 (built {prop.year_built}) — mandatory disclosure on sale",
            "source": "MA Lead Law (M.G.L. c. 111 §§189A–199B)",
        })
    else:
        rows.append({
            "label": "Lead paint disclosure",
            "status": "clear",
            "detail": "N/A — post-1978 construction or year unknown",
            "source": "MA Lead Law (M.G.L. c. 111 §§189A–199B)",
        })

    return rows


def _wraparound_section_title(rows: list[dict[str, Any]]) -> str:
    if any(r["status"] == "flagged" for r in rows):
        return "Wraparound Constraints"
    return "Wraparound Constraints — ALL CLEAR"


def _wraparound_summary_detailed(data: BriefData, rows: list[dict[str, Any]]) -> str:
    addr = data.parcel.address or "this parcel"
    flagged = [r for r in rows if r["status"] == "flagged"]
    lead_caution = any(r["label"] == "Lead paint disclosure" and r["status"] == "caution" for r in rows)
    if not flagged:
        if lead_caution:
            return (
                f"There is no historic, environmental, flood, or open-violation friction on {addr}. "
                f"The only wraparound consideration is the standard pre-1978 lead-paint disclosure "
                f"obligation that applies to any {data.property_info.year_built}-built dwelling."
                if data.property_info and data.property_info.year_built
                else f"There is no historic, environmental, flood, or open-violation friction on {addr}."
            )
        return (
            f"There is no historic, environmental, flood, or open-violation friction on {addr}. "
            f"Standard pre-1978 lead-paint disclosure may still apply for any dwelling built before 1978."
        )
    return (
        f"{addr} intersects {len(flagged)} wraparound layer(s). Each flagged item may require "
        f"additional permits, hearings, or consultations beyond the standard zoning approvals in §5."
    )


def _development_options(data: BriefData) -> list[dict[str, Any]]:
    """Full development-options matrix (13 rows for typical R2+NMF Arlington parcels)."""
    prop = data.property_info
    base_codes = [h.code for h in data.base_zoning_hits if h.code]
    has_r2 = "R2" in base_codes
    has_r1 = "R1" in base_codes
    has_nmf = any(h.code == "NMF" for h in data.overlay_zoning_hits)
    is_multi = bool(prop and prop.building_type and "Multi" in prop.building_type)

    lot_sqft = (
        (prop.lot_size_sqft if prop and prop.lot_size_sqft else None)
        or data.parcel.area_sqft
        or 0
    )
    existing_gfa = prop.finished_area_sqft if prop else None
    r2_rule = data.zoning_rules.get("R2")
    min_lot_r2 = r2_rule.min_lot_sqft if r2_rule and r2_rule.min_lot_sqft else 6000
    lot_meets_r2_new = lot_sqft >= min_lot_r2 if lot_sqft else False

    adu_hi = int(min(900, _as_float(existing_gfa, 1400) * 0.5))
    adu_lo = max(700, adu_hi - 45) if adu_hi > 700 else adu_hi
    adu_range = f"{adu_lo}–{adu_hi} sf" if adu_lo != adu_hi else f"{adu_hi} sf"
    gfa_txt = (
        f"{_fmt_num(existing_gfa)} sf existing"
        if existing_gfa is not None
        else "existing envelope"
    )

    nmf_env = next((e for e in data.envelopes if e.zone_code == "NMF"), None)
    nmf_gfa = int(nmf_env.max_gfa_sqft) if nmf_env and nmf_env.max_gfa_sqft else 2800

    def opt(
        num: int | str,
        option: str,
        path: str,
        process: str,
        lot_qualifies: str,
        scale: str,
        time_to_permit: str,
        status: str = "ok",
    ) -> dict[str, Any]:
        available = {
            "ok": "Yes",
            "caution": "See notes",
            "denied": "No",
        }.get(status, "—")
        if status == "ok" and num == 1:
            available = "Always"
        return {
            "num": num,
            "option": option,
            "path": path,
            "process": process,
            "lot_qualifies": lot_qualifies,
            "scale": scale,
            "time_to_permit": time_to_permit,
            "available": available,
            "status": status,
        }

    options: list[dict[str, Any]] = [
        opt(1, "Status quo — no change", "—", "—", "—", f"1 unit, {gfa_txt}", "—", "ok"),
        opt(
            2,
            "Interior renovation",
            "Building permit only",
            "By-right (no zoning trigger)",
            "Yes",
            "same envelope; quality / efficiency upside",
            "1–2 mo",
        ),
    ]

    if has_r2 or has_r1:
        zone_ref = "R2" if has_r2 else "R1"
        options.append(opt(
            3,
            "Add detached ADU",
            f"Arlington ZBL §5.4 {zone_ref} use table; AHA c. 150/2024 dimensional floor",
            "Building permit; rear-yard placement subject to setbacks",
            "Tight — lot may not accommodate detached",
            f"+1 unit, ≤ {adu_range}",
            "3–4 mo",
            "caution" if is_multi else "ok",
        ))
        options.append(opt(
            4,
            "Add attached ADU / in-law suite",
            f"Arlington ZBL §5.4 {zone_ref} use table",
            "By-right (interior conversion or addition within envelope)",
            "Yes if existing footprint absorbs it",
            f"+1 unit, ≤ {adu_range}",
            "2–3 mo",
            "caution" if is_multi else "ok",
        ))
        options.append(opt(
            5,
            "Convert existing structure to two-family",
            f"{zone_ref} use table (Two-Family Dwelling permitted)",
            "By-right; relies on pre-existing non-conforming lot status",
            "Yes — structure-only conversion",
            f"2 units within existing {_fmt_num(existing_gfa)} sf" if existing_gfa is not None else "2 units within existing envelope",
            "4–6 mo",
            "caution" if is_multi else "ok",
        ))
        options.append(opt(
            6,
            "Two-family conversion + ADU",
            f"{zone_ref} use table — Two-Family and ADU permitted uses",
            "By-right; verify ISD interpretation for ADU + two-family pairing",
            "Likely yes — verify with ISD before commitment",
            f"3 units, ~{_fmt_num(_as_float(existing_gfa, 1490) * 1.4)}–{_fmt_num(_as_float(existing_gfa, 1490) * 1.5)} sf total",
            "4–6 mo",
            "caution",
        ))
        options.append(opt(
            7,
            f"Demolish + rebuild as 2-family under {zone_ref}",
            zone_ref,
            "Variance required — lot may not meet min lot size for new construction",
            "No, without ZBA variance" if not lot_meets_r2_new else "Yes",
            f"2 units within {zone_ref} envelope",
            "9–12 mo if granted",
            "caution" if not lot_meets_r2_new else "ok",
        ))

    if has_nmf:
        per2 = nmf_gfa // 2
        per3 = nmf_gfa // 3
        per4 = nmf_gfa // 4
        options.extend([
            opt(
                8,
                "Demolish + rebuild as 2-unit multi-family under NMF",
                "NMF §5.8",
                "By-right with Site Plan Review by ARB",
                "Yes",
                f"2 units, ~{_fmt_num(nmf_gfa)} sf total, 3 stories",
                "10–14 mo",
            ),
            opt(
                9,
                "Demolish + rebuild as 3-unit multi-family under NMF",
                "NMF §5.8",
                "By-right with Site Plan Review",
                "Yes",
                f"3 units of ~{_fmt_num(per3)} sf each, 3 stories",
                "10–14 mo",
            ),
            opt(
                10,
                "Demolish + rebuild as 4-unit multi-family under NMF",
                "NMF §5.8",
                "By-right with Site Plan Review",
                "Yes — tight per-unit GFA",
                f"4 units of ~{_fmt_num(per4)} sf each, 3 stories",
                "10–14 mo",
            ),
        ])
    # Rows 8–10 apply only when NMF overlay is present; options 11–13 always follow.

    options.append(opt(
        11,
        "Mixed-use (ground retail + residential)",
        "—",
        "NOT permitted — NMF §5.8.B excludes non-residential uses" if has_nmf else "Not permitted in base zone",
        "No",
        "—",
        "—",
        "denied",
    ))
    options.append(opt(
        12,
        "Subdivide lot",
        "—",
        "Not feasible — lot too small for two conforming sub-lots" if lot_sqft and lot_sqft < min_lot_r2 * 2 else "Special permit / subdivision approval",
        "No" if lot_sqft and lot_sqft < min_lot_r2 * 2 else "Unlikely",
        "—",
        "—",
        "denied" if lot_sqft and lot_sqft < min_lot_r2 * 2 else "caution",
    ))
    options.append(opt(
        13,
        "Sell to developer (no build)",
        "—",
        "—",
        "—",
        "Land + entitlement value",
        "0 mo",
    ))

    # Re-number sequentially
    for i, row in enumerate(options, start=1):
        row["num"] = i

    return options


def _development_options_footnote(data: BriefData) -> str | None:
    base_codes = [h.code for h in data.base_zoning_hits if h.code]
    if "R2" not in base_codes and "R1" not in base_codes:
        return None
    prop = data.property_info
    gfa = _as_float(prop.finished_area_sqft if prop else None, 1400)
    zone_ref = "R2" if "R2" in base_codes else "R1"
    adu_hi = int(min(900, gfa * 0.5))
    adu_lo = max(700, adu_hi - 45) if adu_hi > 700 else adu_hi
    return (
        f"ADU is permitted under Arlington Zoning Bylaw §5.4 ({zone_ref} use table). "
        f"The MA Affordable Homes Act (c. 150/2024) preemption applies in single-family districts; "
        f"in {zone_ref}, local rules govern with a state dimensional floor: ADU size capped at "
        f"900 sf or 50% of principal GFA, whichever is less ({adu_lo:,}–{adu_hi:,} sf at "
        f"{_fmt_num(gfa)} sf principal GFA)."
    )


def _process_pathway(data: BriefData) -> list[dict[str, str]]:
    stages = [
        {"stage": "1. DPCD pre-application meeting", "body": "Planning & Community Development", "duration": "2–3 weeks"},
        {"stage": "2. Civil + architect schematic design", "body": "(consultant team)", "duration": "4–6 weeks"},
    ]
    n = 3
    if data.has_overlay_election:
        stages.extend([
            {"stage": "3. Site Plan Review submission", "body": "Town review board (e.g. ARB)", "duration": "file day"},
            {"stage": "4. Public hearing(s)", "body": "Review board", "duration": "8–12 weeks"},
            {"stage": "5. Decision + appeal period", "body": "Review board", "duration": "4 weeks"},
        ])
        n = 6
    stages.extend([
        {"stage": f"{n}. Building permit application", "body": "ISD", "duration": "4–8 weeks"},
        {"stage": f"{n + 1}. Construction", "body": "contractor", "duration": "10–14 months"},
        {"stage": f"{n + 2}. Certificate of Occupancy", "body": "ISD", "duration": "2 weeks"},
    ])
    return stages


def _open_items(data: BriefData) -> list[str]:
    items: list[str] = []
    for env in data.envelopes:
        if env.is_overlay and env.zone_code not in data.zoning_rules:
            items.append(
                f"{env.zone_code} dimensional rules — confirm bylaw text. Overlay rule was not "
                f"found in zoning.parquet. Confirm height, stories, setbacks, parking, and "
                f"inclusionary thresholds at the Town Clerk's office or DPCD's published bylaw.",
            )
    prop = data.property_info
    if prop and prop.year_built and prop.year_built < 1978:
        items.append(
            f"Lead paint disclosure (M.G.L. c. 111 §§189A–199B). Building was constructed in "
            f"{prop.year_built} (pre-1978) — mandatory lead-paint disclosure on sale.",
        )
    items.extend([
        "Existing structure setbacks. Computed from GIS parcel polygon edges, not from a stamped "
        "survey. A Class I survey is recommended before architectural SD.",
        "Title / easements / open MLC. Run a current Municipal Lien Certificate and a title rundown "
        "before any LOI. Out of scope for this brief.",
    ])
    if data.has_overlay_election:
        items.append(
            "Base vs. overlay election. The property owner must elect either base zoning or the "
            "overlay for any given project; the regimes do not stack. Election is project-by-project, "
            "not parcel-perpetual.",
        )
    items.append(
        "Active Board Dockets & Entitlements. TownEye tracks finalized building permits but does "
        "not currently track in-flight Planning Board or ZBA dockets. Verify with the Town Clerk "
        "if this parcel has recent or active Site Plan Review, Variances, or Special Permits.",
    )
    return items


def _wraparound_summary(data: BriefData) -> str:
    rows = _build_detailed_wraparound(data)
    return _wraparound_summary_detailed(data, rows)


def generate_buildability_json(data: BriefData) -> dict[str, Any]:
    prop = data.property_info
    base_zones = [
        {
            "code": h.code,
            "label": h.label,
            "layer": h.layer,
            "rule": _fmt_rule(data.zoning_rules.get(h.code or "")),
        }
        for h in data.base_zoning_hits
    ]
    overlay_zones = [
        {
            "code": h.code,
            "label": h.label,
            "layer": h.layer,
            "rule": _fmt_rule(data.zoning_rules.get(h.code or "")),
        }
        for h in data.overlay_zoning_hits
    ]

    lot_sqft = prop.lot_size_sqft if prop and prop.lot_size_sqft else data.parcel.area_sqft
    zone_label = data.primary_zone_code or "—"
    if data.primary_overlay_code:
        zone_label = f"{zone_label} + {data.primary_overlay_code}"

    raw_attrs = (data.parcel_metadata_extras or {}).get("raw_attributes") or {}
    map_block_lot = raw_attrs.get("Short_id")

    edges = [round(e, 1) for e in (data.parcel.edges_ft or [])]
    lot_shape = (
        f"Edges {' / '.join(str(e) for e in edges)} ft "
        f"(perimeter {_fmt_num(data.parcel.perimeter_ft, '.1f')} ft)"
        if edges and data.parcel.perimeter_ft
        else None
    )

    detailed_wrap = _build_detailed_wraparound(data)

    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "report_date": data.report_date_text,
        "map_block_lot": map_block_lot,
        "headline_verdict_class": data.headline_verdict_class,
        "headline_verdict_text": data.headline_verdict_text,
        "overlay_narrative": _overlay_narrative(data),
        "adu_law_note": (
            "Statewide ADU law (MA AHA c. 150/2024): By-right Accessory Dwelling Units (ADUs) "
            "≤ 900 sqft are permitted in single-family zones across the Commonwealth. This right "
            "supersedes local bans, subject to dimensional setbacks."
        ),
        "executive_sources": (
            f"Sources: {data.inputs.town_slug} Tax Assessor (property.parquet); Town zoning GIS "
            "(zoning.parquet, zoning-overlay.parquet); MA MACRIS, FEMA NFHL, Town hydrology & "
            "historic FeatureServers — all resolved via OverlayResolver."
        ),
        "primary_zone_code": data.primary_zone_code,
        "primary_overlay_code": data.primary_overlay_code,
        "zoning_district": zone_label,
        "has_overlay_election": data.has_overlay_election,
        "has_mbta_communities_overlay": data.has_mbta_communities_overlay,
        "has_property_record": prop is not None,
        "property": {
            "owner_name": prop.owner_name if prop else None,
            "year_built": prop.year_built if prop else None,
            "building_type": prop.building_type if prop else None,
            "luc": prop.luc if prop else None,
            "luc_description": prop.luc_description if prop else None,
            "beds": prop.beds if prop else None,
            "baths": prop.baths if prop else None,
            "book_page": prop.book_page if prop else None,
            "assessed_value": prop.assessed_value if prop else None,
            "lot_size_sqft": lot_sqft,
            "finished_area_sqft": prop.finished_area_sqft if prop else None,
            "last_sale_date": prop.last_sale_date if prop else None,
            "last_sale_price": prop.last_sale_price if prop else None,
        },
        "parcel": {
            "area_sqft": data.parcel.area_sqft,
            "longest_edge_ft": data.parcel.longest_edge_ft,
            "perimeter_ft": data.parcel.perimeter_ft,
            "edges_ft": edges,
            "lot_shape": lot_shape,
            "centroid_lat": data.parcel.centroid_lat,
            "centroid_lon": data.parcel.centroid_lon,
        },
        "base_zones": base_zones,
        "overlay_zones": overlay_zones,
        "dimensional_comparison": _dimensional_comparison(data),
        "envelopes": [_fmt_envelope(e) for e in data.envelopes],
        "envelope_calcs": _envelope_calcs(data),
        "development_options": _development_options(data),
        "development_options_footnote": _development_options_footnote(data),
        "wraparound": detailed_wrap,
        "wraparound_section_title": _wraparound_section_title(detailed_wrap),
        "wraparound_summary": _wraparound_summary_detailed(data, detailed_wrap),
        "process_pathway": _process_pathway(data),
        "open_items": _open_items(data),
        "allowable_uses": _allowable_uses(data),
        "dimensional_controls": _dimensional_controls(data),
        "opportunity_score": _opportunity_score(data),
        "insights": _build_insights(data),
    }
