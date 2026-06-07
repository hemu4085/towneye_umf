"""Risk & Constraints report — wraparound layers, permits, environmental detail."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pyarrow.parquet as pq

from backend.config import get_settings
from backend.services.parcel_permits import summarize_parcel_permits
from reports.buildability_brief import BriefData

_STATUS_LABEL = {"clear": "Clear", "caution": "Caution", "flagged": "Flagged"}
_PILL = {"clear": "ok", "caution": "wn", "flagged": "fl"}

_ENV_LAYER_CHECKS: tuple[tuple[str, str], ...] = (
    ("flood-effective", "FEMA NFHL flood zone (effective)"),
    ("flood-preliminary", "FEMA flood zone (preliminary 2023)"),
    ("wetland", "Town wetlands inventory"),
)


@lru_cache(maxsize=8)
def _env_polygon_count(town_slug: str) -> int:
    path = get_settings().gold_data_path / town_slug / "environmental-overlay.parquet"
    if not path.is_file():
        return 0
    try:
        return pq.read_metadata(path).num_rows
    except (OSError, ValueError):
        return 0


def _hit_matches_layer(hit, layer_key: str) -> bool:
    layer = str(hit.layer or "").lower()
    category = str((hit.attributes or {}).get("category") or "").lower()
    return layer_key in layer or layer_key in category


def _environmental_scan(data: BriefData) -> list[dict[str, Any]]:
    hits = data.raw_stack.environmental_overlay
    lat = data.raw_stack.point_lat
    lon = data.raw_stack.point_lon
    coord = f"({lat:.5f}, {lon:.5f})" if lat is not None and lon is not None else "(centroid)"

    rows: list[dict[str, Any]] = []
    for layer_key, label in _ENV_LAYER_CHECKS:
        matched = [h for h in hits if _hit_matches_layer(h, layer_key)]
        if matched:
            h = matched[0]
            attrs = h.attributes or {}
            zone = h.code or attrs.get("zone_code") or "—"
            subtype = h.label or attrs.get("zone_subtype") or ""
            bfe = attrs.get("static_bfe")
            sfha = attrs.get("sfha_flag")
            parts = [f"Zone {zone}"]
            if subtype and subtype != zone:
                parts.append(str(subtype))
            if bfe is not None:
                parts.append(f"BFE {bfe} ft")
            if sfha is not None:
                parts.append(f"SFHA={'yes' if sfha else 'no'}")
            rows.append({
                "label": label,
                "status": "flagged",
                "status_label": "Flagged",
                "detail": "; ".join(parts),
                "source": h.layer or "environmental-overlay",
            })
        else:
            rows.append({
                "label": label,
                "status": "clear",
                "status_label": "Clear",
                "detail": f"No polygon intersects parcel centroid {coord}.",
                "source": "environmental-overlay.parquet",
            })
    return rows


def generate_risk_json(data: BriefData) -> dict[str, Any]:
    constraints = []
    for c in data.wraparound:
        constraints.append({
            "label": c.label,
            "status": c.status,
            "status_label": _STATUS_LABEL.get(c.status, c.status),
            "detail": c.detail,
            "source": c.source,
            "hit_count": c.hit_count,
        })

    permits = summarize_parcel_permits(
        data.inputs.town_slug,
        data.parcel.parcel_id,
        data.parcel.address or "",
    )
    environmental = _environmental_scan(data)

    flagged = sum(1 for i in constraints if i["status"] == "flagged")
    caution = sum(1 for i in constraints if i["status"] == "caution")
    env_flagged = sum(1 for e in environmental if e["status"] == "flagged")
    if permits["has_open"] or permits["has_expired"]:
        flagged += 1
    if env_flagged:
        flagged += 1

    overall = "flagged" if flagged else ("caution" if caution else "clear")

    open_items = [
        "Registry of Deeds restrictions and easements — not connected in pilot.",
        "MassDEP BWSC / 21E contamination sites — not connected in pilot.",
    ]

    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "overall_status": overall,
        "headline": data.headline_verdict_text,
        "constraints": constraints,
        "environmental": environmental,
        "environmental_flagged": env_flagged,
        "permits": permits,
        "open_items": open_items,
        "centroid": {
            "lat": data.raw_stack.point_lat,
            "lon": data.raw_stack.point_lon,
        },
    }


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def render_risk_html(data: BriefData) -> str:
    payload = generate_risk_json(data)
    overall = payload["overall_status"]
    overall_pill = _PILL.get(overall, "")
    verdict_cls = {"clear": "v-green", "caution": "v-yellow", "flagged": "v-red"}.get(overall, "v-yellow")

    constraint_rows = ""
    for c in payload["constraints"]:
        pill = _PILL.get(c["status"], "")
        constraint_rows += f"""<tr>
          <td>{c['label']}</td>
          <td><span class="{pill}">{c['status_label']}</span></td>
          <td>{c['detail']}</td>
          <td class="small">{c['source']}</td>
        </tr>"""

    env_rows = ""
    for e in payload["environmental"]:
        pill = _PILL.get(e["status"], "")
        env_rows += f"""<tr>
          <td>{e['label']}</td>
          <td><span class="{pill}">{e['status_label']}</span></td>
          <td>{e['detail']}</td>
          <td class="small">{e['source']}</td>
        </tr>"""

    permit_block = payload["permits"]
    permit_n = permit_block.get("total_count", 0) or 0
    address = payload.get("address") or "this property"
    if permit_n == 0:
        permit_summary = f"No building permits found related to {address}."
    elif permit_n == 1:
        permit_summary = f"Found 1 building permit related to {address}."
    else:
        permit_summary = f"Found {permit_n} building permits related to {address}."

    permit_rows = ""
    for p in permit_block.get("permits") or []:
        status = p.get("status", "—")
        pill = "wn" if p.get("is_open") else ("fl" if status == "EXPIRED" else "ok")
        label = "Open" if p.get("is_open") else ("Expired" if status == "EXPIRED" else status.title())
        est = _fmt_money(p.get("estimated_value"))
        permit_rows += f"""<tr>
          <td>{p.get('permit_number', '—')}</td>
          <td>{p.get('permit_type', '—')}</td>
          <td><span class="{pill}">{label}</span></td>
          <td>{p.get('application_date', '—')}</td>
          <td class="num">{est}</td>
          <td>{p.get('description') or '—'}</td>
        </tr>"""
    if not permit_rows:
        permit_rows = f"""<tr><td colspan="6">No building permits found related to {address}.</td></tr>"""

    open_items = "".join(f"<li>{item}</li>" for item in payload.get("open_items") or [])
    env_note = (
        "All three environmental layers are clear at the parcel centroid — supportive for collateral screening."
        if payload.get("environmental_flagged", 0) == 0
        else f"{payload['environmental_flagged']} environmental layer(s) require review."
    )
    env_polygons = _env_polygon_count(data.inputs.town_slug)
    env_scan_note = (
        f"Point-in-polygon test at assessor parcel centroid against "
        f"{env_polygons:,} environmental polygons in Gold."
        if env_polygons
        else "Point-in-polygon test at assessor parcel centroid (environmental overlay not loaded)."
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Risk &amp; Constraints — {payload['address']}</title>
<style>
  body{{font-family:Georgia,'Times New Roman',serif;font-size:13px;line-height:1.55;color:#1a1a1a;max-width:780px;margin:36px auto;padding:0 28px;background:#fff}}
  h1{{font-size:22px;margin:0 0 4px;color:#0b2545;letter-spacing:.5px}}
  h2{{font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#0b2545;border-bottom:2px solid #0b2545;padding:18px 0 4px;margin:18px 0 10px}}
  .hd{{border-bottom:1px solid #ccc;padding-bottom:10px;margin-bottom:8px}}
  .meta{{font-size:11px;color:#555;margin-top:6px}}
  table{{width:100%;border-collapse:collapse;margin:6px 0 10px;font-size:12.5px}}
  th{{background:#0b2545;color:#fff;text-align:left;padding:6px 9px;font-size:11.5px;letter-spacing:.5px}}
  td{{padding:5px 9px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#f7f9fc}}
  .ok{{color:#1a7a1a;font-weight:bold}}
  .wn{{color:#a06b00;font-weight:bold}}
  .fl{{color:#a02020;font-weight:bold}}
  .small{{font-size:11px;color:#555}}
  .note{{font-size:12px;color:#444;margin:6px 0 10px}}
  .num{{font-variant-numeric:tabular-nums}}
  .verdict{{padding:10px 14px;margin:10px 0 12px;border-radius:4px;font-weight:bold}}
  .v-green{{background:#dff1d6;color:#1a5b22;border-left:6px solid #1a7a1a}}
  .v-yellow{{background:#fff3cf;color:#7a5a00;border-left:6px solid #c89800}}
  .v-red{{background:#fadcdc;color:#7a1a1a;border-left:6px solid #a02020}}
  ul{{margin:6px 0;padding-left:20px}}
  .footnote{{font-size:10.5px;color:#555;margin-top:16px;border-top:1px solid #ddd;padding-top:10px}}
</style></head><body>

<div class="hd">
  <h1>Risk &amp; Constraints Report</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{payload['address']}</div>
  <div class="meta">Parcel ID {payload['parcel_id']} · Overall: <span class="{overall_pill}">{overall.upper()}</span></div>
</div>

<h2>1 · Executive Summary</h2>
<div class="verdict {verdict_cls}">{payload.get('headline', '')}</div>
<p>Open permits on parcel: <strong>{permit_block.get('open_count', 0)}</strong> ·
   Closed / CO: <strong>{permit_block.get('total_count', 0) - permit_block.get('open_count', 0)}</strong> ·
   Environmental flags: <strong>{payload.get('environmental_flagged', 0)}</strong></p>

<h2>2 · Constraint Layers</h2>
<table>
<tr><th>Layer</th><th>Status</th><th>Detail</th><th>Source</th></tr>
{constraint_rows}
</table>

<h2>3 · Flood &amp; Wetlands Scan</h2>
<p class="note">{env_note} {env_scan_note}</p>
<table>
<tr><th>Layer checked</th><th>Status</th><th>Detail</th><th>Source</th></tr>
{env_rows}
</table>

<h2>4 · Building Permits (ISD Ledger)</h2>
<p class="note">{permit_summary}</p>
<table>
<tr><th>Permit #</th><th>Type</th><th>Status</th><th>Applied</th><th>Value</th><th>Description</th></tr>
{permit_rows}
</table>

<h2>5 · Not Yet Connected (Pilot)</h2>
<ul>{open_items}</ul>

<p class="footnote">
  Screening report — not a substitute for title, environmental Phase I, or lender legal review.
  Pair with the Buildability Brief for entitlement path and the Pro Forma for economics.
</p>
</body></html>"""
