"""Zoning Summary Card — data-driven, no LLM."""

from __future__ import annotations

from reports.buildability_brief import BriefData


def _fmt_rule(rule) -> dict:
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


def generate_zoning_json(data: BriefData) -> dict:
    base = [_fmt_rule(data.zoning_rules[h.code]) for h in data.base_zoning_hits if h.code in data.zoning_rules]
    overlay = [
        _fmt_rule(data.zoning_rules[h.code]) for h in data.overlay_zoning_hits if h.code in data.zoning_rules
    ]
    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "base_zones": base,
        "overlay_zones": overlay,
        "base_labels": [h.label for h in data.base_zoning_hits],
        "overlay_labels": [h.label for h in data.overlay_zoning_hits],
    }


def render_zoning_html(data: BriefData) -> str:
    payload = generate_zoning_json(data)
    base_rows = payload["base_zones"] + payload["overlay_zones"]
    rows_html = ""
    for z in base_rows:
        uses = ", ".join(z["allowed_uses"][:6]) if z["allowed_uses"] else "—"
        rows_html += f"""
        <tr>
          <td><strong>{z['zone_code']}</strong> {'(overlay)' if z['is_overlay'] else ''}</td>
          <td>{z['description'] or '—'}</td>
          <td>{uses}</td>
          <td>{z['max_far'] if z['max_far'] is not None else '—'}</td>
          <td>{z['min_lot_sqft'] or 'None req.'}</td>
          <td>{z['setback_front_ft'] or '—'}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  body{{font-family:'DM Sans',Arial,sans-serif;color:#0B1F3A;max-width:780px;margin:24px auto;padding:0 20px}}
  h1{{font-family:Georgia,serif;color:#0B1F3A;border-bottom:3px solid #C9A84C;padding-bottom:8px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}}
  th{{background:#0B1F3A;color:#F5F0E8;text-align:left;padding:8px}}
  td{{padding:8px;border-bottom:1px solid #e5e5e5}}
</style></head><body>
<h1>Zoning Summary Card</h1>
<p><strong>{payload['address']}</strong> · Parcel {payload['parcel_id']}</p>
<table>
<tr><th>Zone</th><th>Description</th><th>Permitted uses</th><th>Max FAR</th><th>Min lot</th><th>Front setback</th></tr>
{rows_html}
</table>
</body></html>"""
