"""Buyer Briefing Card — pre-showing parcel report for RE agents (v0)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.llm import generate_json_report
from backend.services.risk import generate_risk_json
from reports.buildability_brief import BriefData

_PILL = {"clear": "ok", "caution": "wn", "flagged": "fl"}


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _town_market_context(town_slug: str) -> dict[str, Any]:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.is_file():
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}
    row = df.iloc[-1].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in row.items()}


def _property_snapshot(data: BriefData) -> dict[str, Any]:
    info = data.property_info
    lot = data.parcel.area_sqft
    if lot is None and info is not None:
        lot = info.lot_size_sqft
    gfa = info.finished_area_sqft if info else None
    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "zone_code": data.primary_zone_code,
        "assessed_value": info.assessed_value if info else None,
        "year_built": info.year_built if info else None,
        "lot_sqft": lot,
        "gfa_sqft": gfa,
        "last_sale_date": info.last_sale_date if info else None,
        "last_sale_price": info.last_sale_price if info else None,
        "owner_name": info.owner_name if info else None,
    }


def _permit_talking_text(permits: dict[str, Any], address: str) -> str:
    total = permits.get("total_count") or 0
    open_count = permits.get("open_count") or 0
    if total == 0:
        return f"No building permits found related to {address}. Verify open jobs on site before showings."
    if open_count:
        return (
            f"Found {total} permit(s) on record including {open_count} open — "
            "confirm status with the building department before showings."
        )
    return f"Found {total} permit(s) on record; none currently open. Verify on site before showings."


def _flood_note(risk_payload: dict[str, Any]) -> str:
    for row in risk_payload.get("environmental") or []:
        if "flood" in str(row.get("label") or "").lower():
            if row.get("status") == "flagged":
                return str(row.get("detail") or "Flood overlay intersects parcel centroid.")
            return "No FEMA flood polygon intersects parcel centroid at assessor point."
    return "Flood status unavailable."


def _historic_note(data: BriefData, risk_payload: dict[str, Any]) -> tuple[str, bool]:
    for c in risk_payload.get("constraints") or []:
        label = str(c.get("label") or "").lower()
        if "historic" in label or "macris" in label:
            flagged = c.get("status") == "flagged"
            return str(c.get("detail") or c.get("label") or "Historic overlay"), flagged
    for w in data.wraparound:
        if "historic" in w.label.lower():
            flagged = w.status == "flagged"
            return w.detail or w.label, flagged
    return "No local or MACRIS historic flag at parcel centroid.", False


def _deterministic_talking_points(
    data: BriefData,
    snapshot: dict[str, Any],
    risk_payload: dict[str, Any],
    market_ctx: dict[str, Any],
) -> list[dict[str, str]]:
    flood = _flood_note(risk_payload)
    historic_detail, historic_flagged = _historic_note(data, risk_payload)
    median = market_ctx.get("median_sale_price")
    assessed = snapshot.get("assessed_value")

    points: list[dict[str, str]] = [
        {
            "keyword": "Pricing",
            "text": (
                f"This property is assessed at {_fmt_money(assessed)}"
                + (f"; town median sale price is {_fmt_money(median)}." if median else ".")
                + " Use assessor value as a starting anchor — pilot has no MLS comps wired."
            ),
        },
        {
            "keyword": "Property",
            "text": (
                f"Built {snapshot.get('year_built') or '—'}, "
                f"{snapshot.get('gfa_sqft') or '—'} sf finished area on a "
                f"{snapshot.get('lot_sqft') or '—'} sf lot."
                + (
                    f" Last sale {snapshot.get('last_sale_date')} at "
                    f"{_fmt_money(snapshot.get('last_sale_price'))}."
                    if snapshot.get("last_sale_date")
                    else ""
                )
            ),
        },
        {
            "keyword": "Zoning",
            "text": (
                f"Base zone {snapshot.get('zone_code') or '—'}. "
                f"{data.headline_verdict_text or 'Confirm permitted uses with town zoning.'}"
            ),
        },
        {
            "keyword": "Flood Risk",
            "text": flood,
        },
        {
            "keyword": "Historic Status",
            "text": (
                f"{historic_detail}"
                + (
                    " Exterior changes may require historic review — flag early for buyers."
                    if historic_flagged
                    else ""
                )
            ),
        },
        {
            "keyword": "Permits",
            "text": _permit_talking_text(risk_payload.get("permits") or {}, snapshot.get("address") or "this property"),
        },
    ]
    return points


def _llm_talking_points(
    data: BriefData,
    snapshot: dict[str, Any],
    risk_payload: dict[str, Any],
    market_ctx: dict[str, Any],
) -> list[dict[str, str]] | None:
    flood = _flood_note(risk_payload)
    historic_detail, historic_flagged = _historic_note(data, risk_payload)
    system = (
        "You are a senior Massachusetts real estate consultant writing a pre-showing briefing "
        "for a licensed agent. Return JSON with key talking_points: an array of exactly 6 objects, "
        "each with keyword (short label) and text (2-3 sentences). Cover: Pricing, Property, Zoning, "
        "Flood Risk, Historic Status, Permits. Use only provided data; do not invent MLS comps."
    )
    user = f"""Property briefing context:
Address: {snapshot.get('address')}
Parcel: {snapshot.get('parcel_id')}
Zone: {snapshot.get('zone_code')}
Assessed: {snapshot.get('assessed_value')}
Year built: {snapshot.get('year_built')}
GFA sqft: {snapshot.get('gfa_sqft')}
Lot sqft: {snapshot.get('lot_sqft')}
Last sale: {snapshot.get('last_sale_date')} @ {snapshot.get('last_sale_price')}
Zoning headline: {data.headline_verdict_text}
Town market: {market_ctx}
Flood note: {flood}
Historic note: {historic_detail} (flagged={historic_flagged})
Permits: {risk_payload.get('permits')}
Overall risk: {risk_payload.get('overall_status')}
"""
    result = generate_json_report(system, user)
    if result.get("fallback") or result.get("error"):
        return None
    raw = result.get("talking_points")
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    out: list[dict[str, str]] = []
    for item in raw[:6]:
        if isinstance(item, dict) and item.get("text"):
            out.append({
                "keyword": str(item.get("keyword") or "Note"),
                "text": str(item.get("text")),
            })
    return out or None


def generate_buyer_briefing(data: BriefData) -> dict[str, Any]:
    risk_payload = generate_risk_json(data)
    snapshot = _property_snapshot(data)
    market_ctx = _town_market_context(data.inputs.town_slug)

    talking = _llm_talking_points(data, snapshot, risk_payload, market_ctx)
    llm_used = talking is not None
    if not talking:
        talking = _deterministic_talking_points(data, snapshot, risk_payload, market_ctx)

    flagged_constraints = [
        c for c in (risk_payload.get("constraints") or []) if c.get("status") == "flagged"
    ]
    env_flagged = [e for e in (risk_payload.get("environmental") or []) if e.get("status") == "flagged"]

    return {
        "report_type": "buyer-briefing",
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "prepared_on": data.report_date_text,
        "snapshot": snapshot,
        "zoning_headline": data.headline_verdict_text,
        "zoning_verdict_class": data.headline_verdict_class,
        "overall_status": risk_payload.get("overall_status"),
        "flagged_constraints": flagged_constraints,
        "environmental_flags": env_flagged,
        "permits": risk_payload.get("permits"),
        "talking_points": talking,
        "llm_synthesized": llm_used,
        "market_context": market_ctx,
        "pilot_gaps": [
            "MLS comparable sales and DOM — not connected in pilot.",
            "Registry chain of title and easements — not connected in pilot.",
            "Not legal or engineering advice — verify with primary sources.",
        ],
        "data_sources": [
            "property.parquet + parcel.parquet",
            "environmental-overlay.parquet",
            "permits.parquet",
            "zoning config + overlays",
            "market-trends.parquet (town medians)",
        ],
    }


def render_buyer_briefing_html(data: BriefData) -> str:
    payload = generate_buyer_briefing(data)
    overall = payload.get("overall_status") or "clear"
    verdict_cls = {"clear": "v-green", "caution": "v-yellow", "flagged": "v-red"}.get(overall, "v-yellow")
    snapshot = payload.get("snapshot") or {}

    flag_rows = ""
    for c in payload.get("flagged_constraints") or []:
        pill = _PILL.get(c.get("status"), "")
        flag_rows += f"""<tr>
          <td>{c.get('label', '—')}</td>
          <td><span class="{pill}">{c.get('status_label', '—')}</span></td>
          <td>{c.get('detail', '—')}</td>
        </tr>"""
    for e in payload.get("environmental_flags") or []:
        pill = _PILL.get(e.get("status"), "")
        flag_rows += f"""<tr>
          <td>{e.get('label', '—')}</td>
          <td><span class="{pill}">{e.get('status_label', '—')}</span></td>
          <td>{e.get('detail', '—')}</td>
        </tr>"""
    if not flag_rows:
        flag_rows = "<tr><td colspan='3'>No material constraint flags at parcel centroid.</td></tr>"

    tp_items = ""
    for tp in payload.get("talking_points") or []:
        tp_items += f"""<li><strong>{tp.get('keyword', 'Note')}:</strong> {tp.get('text', '')}</li>"""

    synth_note = (
        "AI-synthesized talking points (Anthropic) from Gold assessor + overlay data."
        if payload.get("llm_synthesized")
        else "Data-backed talking points from Gold assessor + overlay layers (no LLM key configured)."
    )

    gaps = "".join(f"<li>{g}</li>" for g in payload.get("pilot_gaps") or [])

    permits = payload.get("permits") or {}
    permit_line = _permit_talking_text(permits, payload.get("address") or "this property")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Buyer Briefing — {payload.get('address')}</title>
<style>
  body{{font-family:Georgia,'Times New Roman',serif;font-size:13px;line-height:1.55;color:#1a1a1a;max-width:780px;margin:36px auto;padding:0 28px;background:#fff}}
  h1{{font-size:22px;margin:0 0 4px;color:#0b2545;letter-spacing:.5px}}
  h2{{font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#0b2545;border-bottom:2px solid #0b2545;padding:18px 0 4px;margin:18px 0 10px}}
  .hd{{border-bottom:1px solid #ccc;padding-bottom:10px;margin-bottom:8px}}
  .meta{{font-size:11px;color:#555;margin-top:6px}}
  table{{width:100%;border-collapse:collapse;margin:6px 0 10px;font-size:12.5px}}
  th{{background:#0b2545;color:#fff;text-align:left;padding:6px 9px;font-size:11.5px}}
  td{{padding:5px 9px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#f7f9fc}}
  .ok{{color:#1a7a1a;font-weight:bold}}
  .wn{{color:#a06b00;font-weight:bold}}
  .fl{{color:#a02020;font-weight:bold}}
  .verdict{{padding:10px 14px;margin:10px 0 12px;border-radius:4px;font-weight:bold}}
  .v-green{{background:#dff1d6;color:#1a5b22;border-left:6px solid #1a7a1a}}
  .v-yellow{{background:#fff3cf;color:#7a5a00;border-left:6px solid #c89800}}
  .v-red{{background:#fadcdc;color:#7a1a1a;border-left:6px solid #a02020}}
  ul{{margin:6px 0;padding-left:20px}}
  .note{{font-size:12px;color:#555;margin:8px 0}}
  .footnote{{font-size:10.5px;color:#555;margin-top:16px;border-top:1px solid #ddd;padding-top:10px}}
</style></head><body>

<div class="hd">
  <h1>Buyer Briefing Card</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{payload.get('address')}</div>
  <div class="meta">Parcel {payload.get('parcel_id')} · Prepared {payload.get('prepared_on')}</div>
</div>

<h2>1 · At a Glance</h2>
<div class="verdict {verdict_cls}">
  {payload.get('zoning_headline') or 'Review zoning and constraints before showings.'}
</div>
<table>
<tr><th>Field</th><th>Value</th></tr>
<tr><td>Zone</td><td>{snapshot.get('zone_code') or '—'}</td></tr>
<tr><td>Assessed value</td><td>{_fmt_money(snapshot.get('assessed_value'))}</td></tr>
<tr><td>Year built</td><td>{snapshot.get('year_built') or '—'}</td></tr>
<tr><td>Lot / GFA</td><td>{snapshot.get('lot_sqft') or '—'} sf lot · {snapshot.get('gfa_sqft') or '—'} sf GFA</td></tr>
<tr><td>Last sale</td><td>{snapshot.get('last_sale_date') or '—'} · {_fmt_money(snapshot.get('last_sale_price'))}</td></tr>
</table>

<h2>2 · Show-Stoppers &amp; Flags</h2>
<table>
<tr><th>Item</th><th>Status</th><th>Detail</th></tr>
{flag_rows}
</table>
<p class="note">{permit_line}</p>

<h2>3 · Agent Talking Points</h2>
<p class="note">{synth_note}</p>
<ol>
{tp_items}
</ol>

<h2>4 · Pilot Gaps</h2>
<ul>{gaps}</ul>

<p class="footnote">
  Pre-showing intelligence from TownEye Gold layers — not a CMA, appraisal, or legal opinion.
  Confirm flood, historic, and permit findings with primary sources and listing disclosures.
</p>
</body></html>"""
