"""Realtor Listing Brief — Gold-backed listing memo (no fabricated comps/schools)."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.services import market
from backend.services.parcel_permits import summarize_parcel_permits
from backend.services.zoning import _zoning_constraints
from reports.buildability_brief import BriefData


def _fmt_money(value: Any) -> str:
    try:
        if value is None:
            return "—"
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(value: Any, suffix: str = "") -> str:
    try:
        if value is None:
            return "—"
        n = float(value)
        if abs(n - int(n)) < 1e-9:
            return f"{int(n):,}{suffix}"
        return f"{n:,.1f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: Any) -> str:
    try:
        if value is None:
            return "—"
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _selling_points(data: BriefData, mkt: dict[str, Any], permits: dict[str, Any]) -> list[str]:
    points: list[str] = []
    prop = data.property_info
    assessor = mkt.get("assessor") or {}

    zone = data.primary_zone_code
    overlay = data.primary_overlay_code
    if zone and overlay:
        points.append(
            f"Zoning stack {zone} + {overlay} — confirm buyer use path before marketing ADU / "
            f"multifamily upside (regimes do not stack under Arlington ZBL §5.8 / §3A)."
        )
    elif zone:
        points.append(f"Base zoning {zone} — lead with as-of-right use story, then optional relief.")

    if data.has_mbta_communities_overlay or (overlay and "NMF" in str(overlay).upper()):
        points.append(
            "Parcel intersects the MBTA Communities / NMF conversation — useful for investors "
            "and downsizers evaluating overlay election, not a guarantee of by-right density."
        )

    constraints = _zoning_constraints(data)
    clear = [c for c in constraints if c.get("status") == "clear"]
    flagged = [c for c in constraints if c.get("status") == "flagged"]
    for c in clear[:3]:
        label = c.get("label") or ""
        if label:
            points.append(f"Diligence clear on file: {label}.")
    for c in flagged[:2]:
        label = c.get("label") or "Constraint"
        points.append(f"Disclose early: {label} — {c.get('detail') or 'see Zoning report'}.")

    finished = assessor.get("finished_sqft")
    lot = assessor.get("lot_sqft")
    if finished and lot:
        points.append(
            f"Assessor context: {_fmt_num(finished, ' sf')} finished on a {_fmt_num(lot, ' sf')} lot."
        )
    elif lot:
        points.append(f"Lot size on assessor/GIS: {_fmt_num(lot, ' sf')}.")

    if prop and prop.year_built:
        points.append(f"Year built {int(prop.year_built)} — frame renovation / systems narrative for buyers.")

    gap = mkt.get("assessed_vs_zhvi_pct")
    if gap is not None and mkt.get("zhvi_latest") is not None:
        points.append(
            f"Pricing context: assessed {_fmt_money(assessor.get('assessed_value'))} is "
            f"{_fmt_pct(gap)} vs ZIP ZHVI {_fmt_money(mkt.get('zhvi_latest'))} "
            f"(ZIP {mkt.get('primary_zip')}) — use for list-price conversation, not as a CMA."
        )

    yoy = mkt.get("change_12m_pct")
    if yoy is not None:
        points.append(f"ZIP ZHVI ~12-month move: {_fmt_pct(yoy)}.")

    if permits.get("has_open"):
        points.append(
            f"Open ISD permit activity on parcel ({permits.get('open_count')} open) — "
            "pull status before listing photos / buyer Q&A."
        )
    elif permits.get("total_count"):
        points.append(
            f"{permits.get('total_count')} permit record(s) on Gold for this parcel — "
            "useful renovation history talking points."
        )

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in points:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:10]


def _disclosure_items(data: BriefData, permits: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for c in _zoning_constraints(data):
        if c.get("status") == "flagged":
            items.append(f"{c.get('label')}: {c.get('detail') or 'Flagged in TownEye Gold'}")
    if permits.get("has_open"):
        for p in (permits.get("permits") or [])[:5]:
            if not p.get("is_open"):
                continue
            items.append(
                f"Open permit {p.get('permit_number') or '—'} "
                f"({p.get('permit_type') or '—'} · {p.get('status') or '—'})"
            )
    if not items:
        items.append("No flood/historic/open-permit flags matched in TownEye Gold for this parcel.")
    return items


def generate_listing_brief(data: BriefData) -> dict[str, Any]:
    mkt = market.generate_market_report(data)
    permits = summarize_parcel_permits(
        data.inputs.town_slug,
        data.parcel.parcel_id,
        data.parcel.address or "",
    )
    assessor = mkt.get("assessor") or {}
    prop = data.property_info

    property_type = (
        (prop.building_type if prop and prop.building_type else None)
        or (prop.luc_description if prop and prop.luc_description else None)
        or "—"
    )

    selling_points = _selling_points(data, mkt, permits)
    disclosures = _disclosure_items(data, permits)

    zone_bits = [x for x in (data.primary_zone_code, data.primary_overlay_code) if x]
    headline = data.headline_verdict_text or (
        f"Listing brief for {data.parcel.address} from TownEye Gold assessor, zoning, and ZIP market layers."
    )

    sources = list(mkt.get("data_sources") or [])
    sources.append("permits.parquet (ISD Gold) when present")
    sources.append("Zoning GIS / constraints layers")

    return {
        "report_title": "Realtor Listing Brief",
        "prepared_on": date.today().isoformat(),
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "property_type": property_type,
        "beds": prop.beds if prop else None,
        "baths": prop.baths if prop else None,
        "year_built": int(prop.year_built) if prop and prop.year_built else None,
        "owner_name": prop.owner_name if prop else None,
        "zoning_stack": " · ".join(zone_bits) or "—",
        "headline_verdict": headline,
        "headline_verdict_class": data.headline_verdict_class,
        "assessor": assessor,
        "market": {
            "primary_zip": mkt.get("primary_zip"),
            "zhvi_latest": mkt.get("zhvi_latest"),
            "zhvi_as_of": mkt.get("zhvi_as_of"),
            "change_12m_pct": mkt.get("change_12m_pct"),
            "assessed_vs_zhvi_pct": mkt.get("assessed_vs_zhvi_pct"),
            "data_tier": mkt.get("data_tier"),
        },
        "permits": {
            "open_count": permits.get("open_count", 0),
            "total_count": permits.get("total_count", 0),
            "has_open": bool(permits.get("has_open")),
        },
        "selling_points": selling_points,
        "disclosures": disclosures,
        "schools_status": "unavailable",
        "schools_note": (
            "School ratings / district assignments are not in TownEye Gold for this pilot. "
            "Do not invent GreatSchools-style scores — pull from the district or MLS."
        ),
        "comps_status": "unavailable",
        "comps_note": (
            "MLS sold comps are not connected. Do not present assessor value or ZIP ZHVI as a comparable sale. "
            "Use your MLS CMA for list-price comps."
        ),
        "suggested_talk_track": (
            f"Lead with the physical facts ({_fmt_num(assessor.get('finished_sqft'), ' sf')} finished, "
            f"{_fmt_num(assessor.get('lot_sqft'), ' sf')} lot, year {assessor.get('year_built') or '—'}), "
            f"then zoning stack ({' · '.join(zone_bits) or 'see Zoning report'}), "
            f"then ZIP pricing context — and be explicit that list price still needs an MLS CMA."
        ),
        "data_sources": sources,
        "disclaimer": (
            "TownEye Listing Brief is a diligence aid for listing preparation. "
            "It is not a CMA, appraisal, or offering memorandum. Verify all marketing claims "
            "against MLS, the assessor, and town records before publishing."
        ),
        "data_tier": mkt.get("data_tier") or "assessor_only",
    }


def render_listing_brief_html(payload: dict[str, Any], address: str) -> str:
    assessor = payload.get("assessor") or {}
    mkt = payload.get("market") or {}
    permits = payload.get("permits") or {}
    points = payload.get("selling_points") or []
    disclosures = payload.get("disclosures") or []

    point_items = "".join(f"<li>{p}</li>" for p in points) or "<li>No derived selling points.</li>"
    disclosure_items = "".join(f"<li>{d}</li>" for d in disclosures)

    beds = payload.get("beds")
    baths = payload.get("baths")
    beds_baths = "—"
    if beds is not None or baths is not None:
        beds_baths = f"{beds if beds is not None else '—'} / {baths if baths is not None else '—'}"

    verdict_class = payload.get("headline_verdict_class") or ""
    verdict_css = {
        "v-green": "v-green",
        "v-yellow": "v-yellow",
        "v-red": "v-red",
    }.get(verdict_class, "v-yellow")

    prepared = payload.get("prepared_on") or date.today().isoformat()
    parcel_id = payload.get("parcel_id") or "—"
    tier = str(payload.get("data_tier") or "—").replace("_", " ")
    sources = " · ".join(str(s) for s in (payload.get("data_sources") or []))
    disclaimer = payload.get("disclaimer") or ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Realtor Listing Brief — {address}</title>
<style>
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 13.5px; line-height: 1.55; color: #0b1f3a;
    max-width: 860px; margin: 28px auto; padding: 0 28px 40px; background: #fff;
  }}
  h1 {{ font-size: 22px; margin: 0 0 2px; color: #0b2545; }}
  h2 {{
    font-size: 11.5px; letter-spacing: 1.5px; text-transform: uppercase;
    color: #0b2545; border-bottom: 2px solid #0b2545; padding: 18px 0 4px; margin: 20px 0 10px;
  }}
  .hd {{ border-bottom: 1px solid #d5dbe7; padding-bottom: 12px; margin-bottom: 8px; }}
  .addr {{ font-size: 15px; color: #0b2545; font-weight: bold; margin-top: 4px; }}
  .meta {{ font-size: 11px; color: #5b6575; margin-top: 6px; }}
  .pill {{
    display: inline-block; font-size: 10px; letter-spacing: .6px; text-transform: uppercase;
    border: 1px solid #c9d4e5; color: #334155; padding: 2px 8px; border-radius: 999px; margin-right: 6px;
  }}
  .metrics {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0 4px;
  }}
  .metric {{
    border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; background: #f8fafc;
  }}
  .metric .lbl {{ display: block; font-size: 10px; letter-spacing: .8px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }}
  .metric .val {{ font-size: 16px; font-weight: bold; color: #0b2545; font-variant-numeric: tabular-nums; }}
  .metric .sub {{ display: block; font-size: 10.5px; color: #64748b; margin-top: 3px; }}
  .verdict {{ padding: 10px 14px; margin: 10px 0 12px; border-radius: 4px; }}
  .v-green {{ background: #dff1d6; color: #1a5b22; border-left: 6px solid #1a7a1a; }}
  .v-yellow {{ background: #fff3cf; color: #7a5a00; border-left: 6px solid #c89800; }}
  .v-red {{ background: #fadcdc; color: #7a1a1a; border-left: 6px solid #a02020; }}
  .note {{
    font-size: 12px; color: #7a5a00; background: #fff8e8; border-left: 4px solid #c89800;
    padding: 8px 12px; margin: 10px 0;
  }}
  .talk {{
    font-size: 13px; color: #1e293b; background: #f1f5f9; border-left: 4px solid #0b2545;
    padding: 10px 14px; margin: 10px 0;
  }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 12.5px; }}
  th {{ background: #0b2545; color: #fff; text-align: left; padding: 7px 9px; font-size: 11px; }}
  td {{ padding: 6px 9px; border-bottom: 1px solid #e5e5e5; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #f7f9fc; }}
  .kv td:first-child {{ color: #555; width: 38%; }}
  .num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  ul {{ margin: 6px 0; padding-left: 18px; }}
  li {{ margin: 4px 0; }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  .footnote {{ font-size: 10.5px; color: #64748b; margin-top: 18px; border-top: 1px solid #dde3ee; padding-top: 10px; }}
  @media (max-width: 760px) {{
    .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .two {{ grid-template-columns: 1fr; }}
  }}
</style></head><body>
<div class="hd">
  <h1>Realtor Listing Brief</h1>
  <div class="addr">{address}</div>
  <div class="meta">
    <span class="pill">{tier}</span>
    Prepared {prepared} · Parcel {parcel_id} · {payload.get('zoning_stack') or '—'}
  </div>
</div>

<p class="note">{disclaimer}</p>

<div class="metrics">
  <div class="metric">
    <span class="lbl">Assessed value</span>
    <span class="val">{_fmt_money(assessor.get('assessed_value'))}</span>
    <span class="sub">Town assessor (Gold)</span>
  </div>
  <div class="metric">
    <span class="lbl">ZIP ZHVI</span>
    <span class="val">{_fmt_money(mkt.get('zhvi_latest'))}</span>
    <span class="sub">ZIP {mkt.get('primary_zip') or '—'} · {mkt.get('zhvi_as_of') or '—'}</span>
  </div>
  <div class="metric">
    <span class="lbl">Assessed vs ZHVI</span>
    <span class="val">{_fmt_pct(mkt.get('assessed_vs_zhvi_pct'))}</span>
    <span class="sub">12-mo ZIP {_fmt_pct(mkt.get('change_12m_pct'))}</span>
  </div>
  <div class="metric">
    <span class="lbl">ISD permits</span>
    <span class="val">{permits.get('open_count', 0)} open</span>
    <span class="sub">{permits.get('total_count', 0)} on Gold</span>
  </div>
</div>

<div class="verdict {verdict_css}">{payload.get('headline_verdict') or ''}</div>

<h2>1 · Property snapshot</h2>
<table class="kv">
  <tr><td>Property type</td><td>{payload.get('property_type') or '—'}</td></tr>
  <tr><td>Beds / baths</td><td>{beds_baths}</td></tr>
  <tr><td>Year built</td><td>{payload.get('year_built') or '—'}</td></tr>
  <tr><td>Finished area</td><td class="num">{_fmt_num(assessor.get('finished_sqft'), ' sf')}</td></tr>
  <tr><td>Lot size</td><td class="num">{_fmt_num(assessor.get('lot_sqft'), ' sf')}</td></tr>
  <tr><td>Assessed $/sf</td><td class="num">{_fmt_money(assessor.get('assessed_psf'))}</td></tr>
  <tr><td>Land / building</td><td class="num">{_fmt_money(assessor.get('land_val'))} / {_fmt_money(assessor.get('bldg_val'))}</td></tr>
  <tr><td>Zoning stack</td><td>{payload.get('zoning_stack') or '—'}</td></tr>
  <tr><td>Owner (assessor)</td><td>{payload.get('owner_name') or '—'}</td></tr>
</table>

<h2>2 · Suggested talk track</h2>
<p class="talk">{payload.get('suggested_talk_track') or ''}</p>

<div class="two">
  <div>
    <h2>3 · Listing angles (from Gold)</h2>
    <ul>{point_items}</ul>
  </div>
  <div>
    <h2>4 · Disclose / verify</h2>
    <ul>{disclosure_items}</ul>
  </div>
</div>

<h2>5 · Schools</h2>
<p class="note">{payload.get('schools_note') or ''}</p>

<h2>6 · Comparable sales</h2>
<p class="note">{payload.get('comps_note') or ''}</p>

<p class="footnote">Sources: {sources}. {disclaimer}</p>
</body></html>"""
