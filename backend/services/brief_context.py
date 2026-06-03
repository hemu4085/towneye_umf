"""Serialize BriefData into text context for property Q&A."""

from __future__ import annotations

from reports.buildability_brief import BriefData


def brief_context_text(data: BriefData) -> str:
    """Compact facts for LLM or rule-based answers."""
    p = data.parcel
    prop = data.property_info
    lines = [
        f"Address: {p.address}",
        f"Parcel ID: {p.parcel_id}",
        f"Town: {data.inputs.town_slug}",
        f"Lot size (GIS): {p.area_sqft} sq ft" if p.area_sqft else "Lot size: unknown",
        f"Buildability verdict: {data.headline_verdict_text}",
    ]

    if prop:
        if prop.year_built:
            lines.append(f"Year built: {prop.year_built}")
        if prop.beds is not None:
            lines.append(f"Bedrooms: {prop.beds}")
        if prop.baths is not None:
            lines.append(f"Bathrooms: {prop.baths}")
        if prop.assessed_value is not None:
            lines.append(f"Assessed value: ${prop.assessed_value:,.0f}")
        if prop.lot_size_sqft:
            lines.append(f"Assessor lot size: {prop.lot_size_sqft} sq ft")
        if prop.finished_area_sqft:
            lines.append(f"Finished area: {prop.finished_area_sqft} sq ft")
        if prop.last_sale_price:
            lines.append(f"Last sale: ${prop.last_sale_price:,.0f} ({prop.last_sale_date or 'date n/a'})")
        if prop.luc_description or prop.luc:
            lines.append(f"Current use: {prop.luc_description or prop.luc}")

    lines.append("Base zoning: " + ", ".join(h.label for h in data.base_zoning_hits) or "—")
    lines.append("Overlay zoning: " + ", ".join(h.label for h in data.overlay_zoning_hits) or "—")

    for code, rule in data.zoning_rules.items():
        uses = rule.allowed_uses or []
        use_sample = ", ".join(uses[:12]) if uses else "see town bylaws"
        lines.append(
            f"Zone {code} ({'overlay' if rule.is_overlay else 'base'}): "
            f"FAR max {rule.max_far}, allowed uses include: {use_sample}",
        )

    for env in data.envelopes[:4]:
        lines.append(
            f"Envelope {env.label}: max GFA {env.max_gfa_sqft} sf, qualifies={env.qualifies}, "
            f"{env.rationale}",
        )

    for w in data.wraparound:
        lines.append(f"Constraint {w.label}: {w.status} — {w.detail}")

    return "\n".join(lines)
