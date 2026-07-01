"""Zoning Intelligence Report — parcel-level zoning analysis, no LLM."""

from __future__ import annotations

from typing import Any

from reports.buildability_brief import BriefData

from backend.services.buildability import (
    _allowable_uses,
    _build_detailed_wraparound,
    _development_options,
    _development_options_footnote,
    _dimensional_comparison,
    _dimensional_controls,
    _fmt_envelope,
    _fmt_num,
    _fmt_rule,
    _open_items,
    _overlay_narrative,
    _process_pathway,
)

# Constraints that can trigger extra hearings beyond standard zoning review.
_ZONING_CONSTRAINT_LABELS = frozenset({
    "FEMA flood zone",
    "Arlington flood overlay",
    "2023 FEMA flood remap",
    "Wetlands / conservation buffer",
    "MACRIS — historic district polygon",
    "MACRIS — inventoried building (30m buffer)",
    "Local Historic District",
    "National Historic District",
    "Historic Overlay District",
    "AHC Inventory",
    "Open zoning violations",
})


def _hit_gis_metadata(hit) -> dict[str, Any]:
    attrs = hit.attributes or {}
    raw = attrs.get("raw_attributes") if isinstance(attrs.get("raw_attributes"), dict) else attrs
    district_name = (
        raw.get("OverlayDistrict")
        or raw.get("ZoneName")
        or raw.get("ZoneDesc")
        or hit.label
    )
    adoption = raw.get("TMA") or raw.get("DateMod") or raw.get("DateEst")
    notes = raw.get("Notes")
    return {
        "district_name": str(district_name) if district_name else None,
        "adoption_reference": str(adoption) if adoption else None,
        "gis_notes": str(notes) if notes else None,
    }


def _zone_hits(data: BriefData) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base_zones = [
        {
            "code": h.code,
            "label": h.label,
            "layer": h.layer,
            "rule": _fmt_rule(data.zoning_rules.get(h.code or "")),
            "gis": _hit_gis_metadata(h),
        }
        for h in data.base_zoning_hits
    ]
    overlay_zones = [
        {
            "code": h.code,
            "label": h.label,
            "layer": h.layer,
            "rule": _fmt_rule(data.zoning_rules.get(h.code or "")),
            "gis": _hit_gis_metadata(h),
        }
        for h in data.overlay_zoning_hits
    ]
    return base_zones, overlay_zones


def _regulatory_signals(data: BriefData) -> list[dict[str, str]]:
    """Parcel-specific zoning friction signals competitors rarely combine."""
    signals: list[dict[str, str]] = []
    prop = data.property_info
    assessor_lot = prop.lot_size_sqft if prop else None
    gis_lot = data.parcel.area_sqft
    if assessor_lot and gis_lot and abs(assessor_lot - gis_lot) > 50:
        signals.append({
            "signal": "Assessor vs GIS lot size",
            "severity": "info",
            "detail": (
                f"Regulatory lot {_fmt_num(assessor_lot)} sf (assessor) vs "
                f"{_fmt_num(gis_lot)} sf (GIS polygon). Envelope math uses the "
                f"assessor figure; GIS area may include ROW slivers."
            ),
        })

    base_env = next((e for e in data.envelopes if not e.is_overlay), None)
    if base_env and base_env.qualifies is False:
        signals.append({
            "signal": "Base district lot non-conformance",
            "severity": "warning",
            "detail": (
                f"Lot does not meet {base_env.zone_code} minimum lot size for "
                f"new construction — tear-down/rebuild under base zoning likely "
                f"requires a ZBA variance."
            ),
        })

    if base_env and base_env.pct_of_far_cap is not None and base_env.pct_of_far_cap >= 0.9:
        signals.append({
            "signal": "Base FAR nearly exhausted",
            "severity": "warning",
            "detail": (
                f"Existing GFA is {base_env.pct_of_far_cap * 100:.0f}% of the "
                f"{base_env.zone_code} FAR cap — limited by-right expansion under base zoning."
            ),
        })

    if prop and prop.luc_description:
        luc = prop.luc_description.lower()
        base_codes = [h.code for h in data.base_zoning_hits if h.code]
        if "R2" in base_codes and "one family" in luc:
            signals.append({
                "signal": "Assessor use vs zoning district",
                "severity": "info",
                "detail": (
                    f"Assessor land-use code is '{prop.luc_description}' in an "
                    f"R2 two-family district — verify current occupancy vs permitted uses."
                ),
            })
        elif "one family" in luc and any(c in base_codes for c in ("R2", "R3")):
            signals.append({
                "signal": "Assessor use vs zoning district",
                "severity": "info",
                "detail": (
                    f"Assessor records '{prop.luc_description}' while base zoning "
                    f"permits denser residential — potential conversion upside or "
                    f"non-conforming use to confirm."
                ),
            })

    noncomp = data.raw_stack.noncompliance if data.raw_stack else []
    if noncomp:
        labels = sorted({(h.label or h.code or "non-compliance") for h in noncomp})
        signals.append({
            "signal": "Land-use / zoning non-compliance layer",
            "severity": "warning",
            "detail": (
                f"Parcel appears on the town's LandUse_NonCompliance GIS layer "
                f"({', '.join(labels)}). May indicate pre-existing non-conforming "
                f"use — confirm with DPCD before redevelopment."
            ),
        })

    if data.has_overlay_election:
        overlay_env = next((e for e in data.envelopes if e.is_overlay), None)
        if overlay_env and base_env:
            base_room = base_env.expansion_room_sqft or 0
            overlay_room = overlay_env.expansion_room_sqft
            overlay_gfa = overlay_env.max_gfa_sqft
            if overlay_gfa and (overlay_room is None or overlay_room > base_room + 500):
                signals.append({
                    "signal": "Overlay election materially expands capacity",
                    "severity": "opportunity",
                    "detail": (
                        f"Electing {overlay_env.zone_code} unlocks up to "
                        f"{_fmt_num(overlay_gfa)} sf GFA vs "
                        f"{_fmt_num(base_env.max_gfa_sqft)} sf under base "
                        f"{base_env.zone_code} — project-by-project election required."
                    ),
                })

    return signals


def _overlay_election_recommendation(data: BriefData) -> dict[str, Any] | None:
    if not data.has_overlay_election:
        return None
    base_env = next((e for e in data.envelopes if not e.is_overlay), None)
    overlay_env = next((e for e in data.envelopes if e.is_overlay), None)
    if not overlay_env:
        return None

    recommended = overlay_env.zone_code
    rationale_parts: list[str] = []
    if overlay_env.max_gfa_sqft and base_env and base_env.max_gfa_sqft:
        delta = overlay_env.max_gfa_sqft - base_env.max_gfa_sqft
        if delta > 0:
            rationale_parts.append(
                f"+{_fmt_num(delta)} sf GFA vs base {base_env.zone_code}"
            )
    if base_env and base_env.qualifies is False:
        rationale_parts.append(
            f"base lot is non-conforming for new construction under {base_env.zone_code}"
        )
    if data.has_mbta_communities_overlay:
        rationale_parts.append("MBTA §3A by-right multi-family path available")

    return {
        "recommended_regime": recommended,
        "alternative_regime": base_env.zone_code if base_env else None,
        "election_type": "project-by-project (regimes do not stack)",
        "rationale": "; ".join(rationale_parts) if rationale_parts else (
            f"{recommended} overlay provides additional development paths vs base zoning."
        ),
    }


def _zoning_development_paths(data: BriefData) -> list[dict[str, Any]]:
    """Top actionable development paths — condensed from the full brief matrix."""
    paths: list[dict[str, Any]] = []
    for opt in _development_options(data):
        if opt.get("status") == "denied":
            continue
        if str(opt.get("option", "")).startswith("Status quo"):
            continue
        paths.append({
            "option": opt["option"],
            "path": opt["path"],
            "process": opt["process"],
            "scale": opt.get("scale") or "—",
            "time_to_permit": opt.get("time_to_permit") or "—",
            "available": opt.get("available") or "—",
            "lot_qualifies": opt.get("lot_qualifies") or "—",
            "status": opt.get("status") or "ok",
        })
        if len(paths) >= 8:
            break
    return paths


def _zoning_constraints(data: BriefData) -> list[dict[str, Any]]:
    rows = _build_detailed_wraparound(data)
    return [r for r in rows if r.get("label") in _ZONING_CONSTRAINT_LABELS]


def _zoning_insights(data: BriefData) -> list[str]:
    insights: list[str] = []
    rec = _overlay_election_recommendation(data)
    if rec:
        insights.append(
            f"Recommended overlay election: {rec['recommended_regime']} — {rec['rationale']}"
        )
    for env in data.envelopes:
        if env.expansion_room_sqft and env.expansion_room_sqft > 0:
            insights.append(
                f"Under {env.label}: {_fmt_num(env.expansion_room_sqft)} sf by-right "
                f"expansion room ({env.rationale})"
            )
        elif env.max_gfa_sqft and env.existing_gfa_sqft and env.pct_of_far_cap and env.pct_of_far_cap >= 0.95:
            insights.append(
                f"{env.label}: at {env.pct_of_far_cap * 100:.0f}% of FAR cap — "
                f"limited upside without overlay election or variance."
            )
    for sig in _regulatory_signals(data):
        if sig["severity"] in ("warning", "opportunity"):
            insights.append(f"{sig['signal']}: {sig['detail']}")
    if data.has_mbta_communities_overlay:
        insights.append(
            "MBTA Communities Act (§3A) overlay applies — by-right multi-family "
            "development may supersede base district density limits when elected."
        )
    seen: set[str] = set()
    deduped: list[str] = []
    for item in insights:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:6]


def _zoning_opportunity_score(data: BriefData) -> float:
    score = 5.0
    overlay_env = next((e for e in data.envelopes if e.is_overlay), None)
    base_env = next((e for e in data.envelopes if not e.is_overlay), None)

    if overlay_env and overlay_env.max_gfa_sqft:
        if base_env and base_env.max_gfa_sqft:
            uplift = overlay_env.max_gfa_sqft - base_env.max_gfa_sqft
            if uplift > 2000:
                score += 2.5
            elif uplift > 1000:
                score += 1.5
            elif uplift > 500:
                score += 1.0
        else:
            score += 1.5

    if data.has_mbta_communities_overlay:
        score += 1.0

    constraints = _zoning_constraints(data)
    flagged = sum(1 for c in constraints if c.get("status") == "flagged")
    score -= flagged * 1.25

    if base_env and base_env.qualifies is False and overlay_env:
        score += 0.75  # overlay path exists despite base non-conformance

    return round(min(10.0, max(1.0, score)), 1)


def _zoning_sources(data: BriefData) -> str:
    town = data.inputs.town_slug
    layers = sorted({
        z.get("layer") or ""
        for z in (
            [{"layer": h.layer} for h in data.base_zoning_hits]
            + [{"layer": h.layer} for h in data.overlay_zoning_hits]
        )
        if z.get("layer")
    })
    layer_txt = ", ".join(layers) if layers else "town zoning GIS"
    return (
        f"Sources: {town} zoning GIS ({layer_txt}); zoning.parquet bylaw rules; "
        f"property.parquet assessor; parcel.parquet GIS polygon — resolved via "
        f"OverlayResolver point-in-polygon at parcel centroid."
    )


def _open_items_zoning(data: BriefData) -> list[str]:
    keywords = ("overlay", "election", "bylaw", "setback", "survey", "non-conform", "docket", "Site Plan")
    items = []
    for item in _open_items(data):
        lower = item.lower()
        if any(k in lower for k in keywords):
            items.append(item)
    return items[:6]


def generate_zoning_json(data: BriefData) -> dict[str, Any]:
    base_zones, overlay_zones = _zone_hits(data)
    zone_label = data.primary_zone_code or "—"
    if data.primary_overlay_code:
        zone_label = f"{zone_label} + {data.primary_overlay_code}"

    prop = data.property_info
    lot_sqft = prop.lot_size_sqft if prop and prop.lot_size_sqft else data.parcel.area_sqft

    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "report_date": data.report_date_text,
        "primary_zone_code": data.primary_zone_code,
        "primary_overlay_code": data.primary_overlay_code,
        "zoning_district": zone_label,
        "has_overlay_election": data.has_overlay_election,
        "has_mbta_communities_overlay": data.has_mbta_communities_overlay,
        "headline_verdict_class": data.headline_verdict_class,
        "headline_verdict_text": data.headline_verdict_text,
        "zoning_opportunity_score": _zoning_opportunity_score(data),
        "overlay_narrative": _overlay_narrative(data),
        "overlay_election": _overlay_election_recommendation(data),
        "regulatory_signals": _regulatory_signals(data),
        "zoning_insights": _zoning_insights(data),
        "base_zones": base_zones,
        "overlay_zones": overlay_zones,
        "base_labels": [h.label for h in data.base_zoning_hits],
        "overlay_labels": [h.label for h in data.overlay_zoning_hits],
        "allowable_uses": _allowable_uses(data),
        "dimensional_controls": _dimensional_controls(data),
        "dimensional_comparison": _dimensional_comparison(data),
        "envelopes": [_fmt_envelope(e) for e in data.envelopes],
        "development_paths": _zoning_development_paths(data),
        "development_paths_footnote": _development_options_footnote(data),
        "zoning_constraints": _zoning_constraints(data),
        "process_pathway": _process_pathway(data),
        "open_items": _open_items_zoning(data),
        "sources": _zoning_sources(data),
        "lot_size_sqft": lot_sqft,
        "existing_gfa_sqft": prop.finished_area_sqft if prop else None,
        "assessor_use_code": (
            f"{prop.luc} — {prop.luc_description}"
            if prop and prop.luc_description
            else None
        ),
    }


def _html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _comparison_status_cell(val: str) -> str:
    if val == "qualifies":
        return '<span style="color:#16a34a">✓ qualifies</span>'
    if val == "non-conforming":
        return '<span style="color:#dc2626">⚠ non-conforming</span>'
    if val == "not specified":
        return '<span style="color:#d97706">⚠ not specified</span>'
    return _html_escape(val)


def render_zoning_html(data: BriefData) -> str:
    payload = generate_zoning_json(data)
    district = payload.get("zoning_district") or "—"
    score = payload.get("zoning_opportunity_score")

    verdict_html = ""
    if payload.get("headline_verdict_text"):
        verdict_html = f'<p class="verdict">{_html_escape(payload["headline_verdict_text"])}</p>'

    election = payload.get("overlay_election") or {}
    election_html = ""
    if election:
        election_html = (
            f'<p class="narrative"><strong>Recommended election:</strong> '
            f'{_html_escape(election.get("recommended_regime") or "")} — '
            f'{_html_escape(election.get("rationale") or "")}</p>'
        )

    signals_html = ""
    for sig in payload.get("regulatory_signals") or []:
        signals_html += f'<li>{_html_escape(sig.get("detail") or "")}</li>'

    uses_rows = "".join(
        f"<tr><td>{_html_escape(r['use'])}</td>"
        f"<td>{_html_escape(r['status'])}</td>"
        f"<td>{_html_escape(r['zone_code'])}</td></tr>"
        for r in payload.get("allowable_uses") or []
    )

    path_rows = "".join(
        f"<tr><td>{_html_escape(r['option'])}</td>"
        f"<td>{_html_escape(r['process'])}</td>"
        f"<td>{_html_escape(r['scale'])}</td>"
        f"<td>{_html_escape(r['time_to_permit'])}</td></tr>"
        for r in payload.get("development_paths") or []
    )

    comp = payload.get("dimensional_comparison") or {}
    comp_header = "".join(f"<th>{_html_escape(c)}</th>" for c in comp.get("columns") or [])
    comp_rows = "".join(
        f"<tr><td><strong>{_html_escape(row['standard'])}</strong></td>"
        + "".join(f"<td>{_comparison_status_cell(v)}</td>" for v in row.get("values") or [])
        + "</tr>"
        for row in comp.get("rows") or []
    )

    env_rows = "".join(
        f"<tr><td>{_html_escape(e.get('label') or '')}</td>"
        f"<td>{_html_escape(str(e.get('max_gfa_sqft') or '—'))}</td>"
        f"<td>{_html_escape(str(e.get('expansion_room_sqft') or '—'))}</td>"
        f"<td>{_html_escape(e.get('rationale') or '')}</td></tr>"
        for e in payload.get("envelopes") or []
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  body{{font-family:'DM Sans',Arial,sans-serif;color:#0B1F3A;max-width:860px;margin:24px auto;padding:0 20px}}
  h1{{font-family:Georgia,serif;color:#0B1F3A;border-bottom:3px solid #C9A84C;padding-bottom:8px}}
  h2{{font-size:15px;margin-top:28px;border-bottom:1px solid #e5e5e5;padding-bottom:6px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}}
  th{{background:#0B1F3A;color:#F5F0E8;text-align:left;padding:8px}}
  td{{padding:8px;border-bottom:1px solid #e5e5e5}}
  .meta,.narrative,.verdict{{font-size:13px;line-height:1.5}}
  .score{{font-size:22px;font-weight:bold;color:#6d28d9}}
</style></head><body>
<h1>Zoning Intelligence Report</h1>
<p class="meta"><strong>{_html_escape(payload.get('address') or '')}</strong> · Parcel {_html_escape(payload.get('parcel_id') or '')}<br>
District: <strong>{_html_escape(district)}</strong> · Opportunity score: <span class="score">{score}</span>/10</p>
{verdict_html}
{election_html}
<h2>Regulatory signals</h2><ul>{signals_html or '<li>None flagged</li>'}</ul>
<h2>Development paths</h2>
<table><tr><th>Option</th><th>Process</th><th>Scale</th><th>Timeline</th></tr>{path_rows}</table>
<h2>Dimensional comparison</h2>
<table><tr><th>Standard</th>{comp_header}</tr>{comp_rows}</table>
<h2>Envelope analysis</h2>
<table><tr><th>Regime</th><th>Max GFA</th><th>Expansion</th><th>Rationale</th></tr>{env_rows}</table>
<h2>Permitted uses</h2>
<table><tr><th>Use</th><th>Status</th><th>Zone</th></tr>{uses_rows}</table>
<p class="meta">{_html_escape(payload.get('sources') or '')}</p>
</body></html>"""
