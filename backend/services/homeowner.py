"""Homeowner Insights — Gold memo (value, taxes portal, permits, zoning).

No fabricated renovation ROI percentages. Renovation items are permit-path guidance only.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

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


@lru_cache(maxsize=8)
def _town_cfg(town_slug: str) -> dict[str, Any]:
    path = Path("configs") / town_slug / "config.yaml"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _tax_context(town_slug: str, parcel_id: str) -> dict[str, Any]:
    lender = (_town_cfg(town_slug).get("lender_report") or {}) if _town_cfg(town_slug) else {}
    portal = str(lender.get("property_tax_portal_url") or "").strip() or None
    fixtures = [
        r for r in (lender.get("property_tax_records") or [])
        if isinstance(r, dict) and str(r.get("parcel_id") or "") == str(parcel_id)
    ]
    if fixtures:
        return {
            "status": "fixture",
            "portal_url": portal,
            "records": fixtures,
            "note": (
                "Tax status from TownEye fixture / prior lookup for this parcel. "
                "Confirm the live balance on the town tax portal before paying."
            ),
        }
    return {
        "status": "portal_only",
        "portal_url": portal,
        "records": [],
        "note": (
            "No cached tax bill for this parcel in Gold. Use the town Invoice Cloud / tax portal "
            "with your parcel ID — TownEye does not invent annual tax amounts."
        ),
    }


def _renovation_ideas(data: BriefData, mkt: dict[str, Any]) -> list[dict[str, str]]:
    """Permit-path guidance — deliberately no fake ROI %."""
    ideas: list[dict[str, str]] = []
    overlay = data.primary_overlay_code
    zone = data.primary_zone_code
    assessor = mkt.get("assessor") or {}
    year = assessor.get("year_built")

    ideas.append({
        "project": "Kitchen / bath remodel",
        "path": "Typically plumbing + electrical permits via ISD / OpenGov",
        "note": "Confirm whether work is cosmetic-only or triggers inspection. Not an ROI estimate.",
    })
    ideas.append({
        "project": "Finished basement / attic",
        "path": "Building permit; check ceiling height, egress, and flood constraints",
        "note": "See Risk / Zoning reports before marketing extra living area.",
    })
    if overlay or data.has_mbta_communities_overlay:
        ideas.append({
            "project": "ADU / additional unit",
            "path": f"Overlay election / density path under {overlay or 'NMF'} — regimes do not stack",
            "note": "Use Zoning Intelligence for election memo; do not assume by-right ADU.",
        })
    else:
        ideas.append({
            "project": "ADU / additional unit",
            "path": f"Check {zone or 'base'} rules and ZBA special permit / variance needs",
            "note": "TownEye will not invent approval odds or renovation ROI.",
        })
    if year and int(year) < 1978:
        ideas.append({
            "project": "Lead paint / window replacement",
            "path": "EPA RRP rules may apply for pre-1978 homes",
            "note": f"Assessor year built {int(year)} — disclose and use certified contractors.",
        })
    ideas.append({
        "project": "Electrification / heat pump",
        "path": "Electrical permit; check Arlington fossil-fuel / stretch-code guidance",
        "note": "See ISD energy pages — incentives change; verify before bidding.",
    })
    return ideas


def _action_items(
    data: BriefData,
    *,
    mkt: dict[str, Any],
    permits: dict[str, Any],
    tax: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    if tax.get("portal_url"):
        items.append(f"Check live tax balance: {tax['portal_url']}")
    if permits.get("has_open"):
        items.append(
            f"Resolve {permits.get('open_count')} open ISD permit(s) before listing or refinancing."
        )
    for c in _zoning_constraints(data):
        if c.get("status") == "flagged":
            items.append(f"Review constraint: {c.get('label')} — {c.get('detail') or ''}".strip())
    gap = mkt.get("assessed_vs_zhvi_pct")
    if gap is not None and abs(float(gap)) >= 5:
        items.append(
            f"Pricing conversation: assessed is {_fmt_pct(gap)} vs ZIP ZHVI — get an MLS CMA before list price."
        )
    items.append("Pull Zoning Intelligence before any ADU / addition marketing claims.")
    items.append("Confirm flood / historic status on the Risk report if renovating or refinancing.")
    # Dedup
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out[:10]


def _value_story(assessor: dict[str, Any], mkt: dict[str, Any]) -> str:
    assessed = assessor.get("assessed_value")
    zhvi = mkt.get("zhvi_latest")
    gap = mkt.get("assessed_vs_zhvi_pct")
    yoy = mkt.get("change_12m_pct")
    zip_code = mkt.get("primary_zip") or "your ZIP"
    if assessed is None and zhvi is None:
        return (
            "Assessor and ZIP market series are not both available for this parcel yet. "
            "Keep this memo for permit and disclosure tracking while market coverage expands."
        )
    parts = [
        f"Town assessor lists this property at {_fmt_money(assessed)}. "
        f"ZIP {zip_code} Zillow Home Value Index sits at {_fmt_money(zhvi)}"
    ]
    if mkt.get("zhvi_as_of"):
        parts.append(f" (as of {mkt.get('zhvi_as_of')})")
    parts.append(".")
    if gap is not None:
        parts.append(
            f" That is {_fmt_pct(gap)} vs the ZIP index — useful for refinance, insurance, "
            "and listing conversations, not a sale price."
        )
    if yoy is not None:
        parts.append(f" ZIP values moved {_fmt_pct(yoy)} over the last 12 months.")
    parts.append(
        " TownEye refreshes Gold so you can watch this gap and open permits month to month "
        "without guessing from national renovation ROI charts."
    )
    return "".join(parts)


def generate_homeowner_report(data: BriefData) -> dict[str, Any]:
    mkt = market.generate_market_report(data)
    permits = summarize_parcel_permits(
        data.inputs.town_slug,
        data.parcel.parcel_id,
        data.parcel.address or "",
    )
    tax = _tax_context(data.inputs.town_slug, data.parcel.parcel_id)
    assessor = mkt.get("assessor") or {}
    prop = data.property_info
    renovations = _renovation_ideas(data, mkt)
    actions = _action_items(data, mkt=mkt, permits=permits, tax=tax)

    disclosures: list[str] = []
    for c in _zoning_constraints(data):
        if c.get("status") == "flagged":
            disclosures.append(f"{c.get('label')}: {c.get('detail') or 'Flagged in Gold'}")
        elif c.get("status") == "clear" and c.get("label"):
            disclosures.append(f"Clear on file: {c.get('label')}")
    if permits.get("has_open"):
        for p in (permits.get("permits") or []):
            if p.get("is_open"):
                disclosures.append(
                    f"Open permit {p.get('permit_number') or '—'} "
                    f"({p.get('permit_type') or '—'} · {p.get('status') or '—'})"
                )
    if not any("Flagged" in d or "Open permit" in d for d in disclosures):
        disclosures.insert(0, "No flood/historic/open-permit flags matched in TownEye Gold.")

    zone_bits = [x for x in (data.primary_zone_code, data.primary_overlay_code) if x]
    summary = (
        f"Homeowner insights for {data.parcel.address}. "
        f"Assessor value {_fmt_money(assessor.get('assessed_value'))}"
    )
    if mkt.get("zhvi_latest") is not None:
        summary += (
            f" vs ZIP {mkt.get('primary_zip')} ZHVI {_fmt_money(mkt.get('zhvi_latest'))} "
            f"({_fmt_pct(mkt.get('assessed_vs_zhvi_pct'))}). "
        )
    else:
        summary += ". "
    summary += (
        "Use this memo for maintenance, permit, and pricing conversations — "
        "not as an appraisal or renovation ROI calculator."
    )

    sources = list(mkt.get("data_sources") or [])
    sources.extend([
        "permits.parquet (ISD)",
        "zoning GIS / constraints",
        "lender_report.property_tax_records + tax portal link",
    ])

    return {
        "report_title": "Homeowner Insights",
        "prepared_on": date.today().isoformat(),
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "summary": summary,
        "headline_verdict": data.headline_verdict_text,
        "headline_verdict_class": data.headline_verdict_class,
        "zoning_stack": " · ".join(zone_bits) or "—",
        "owner_name": prop.owner_name if prop else None,
        "property_type": (
            (prop.building_type if prop and prop.building_type else None)
            or (prop.luc_description if prop and prop.luc_description else None)
            or "—"
        ),
        "beds": prop.beds if prop else None,
        "baths": prop.baths if prop else None,
        "year_built": int(prop.year_built) if prop and prop.year_built else None,
        "last_sale_date": prop.last_sale_date if prop else None,
        "last_sale_price": prop.last_sale_price if prop else None,
        "assessor": assessor,
        "market": {
            "primary_zip": mkt.get("primary_zip"),
            "zhvi_latest": mkt.get("zhvi_latest"),
            "zhvi_as_of": mkt.get("zhvi_as_of"),
            "change_12m_pct": mkt.get("change_12m_pct"),
            "assessed_vs_zhvi_pct": mkt.get("assessed_vs_zhvi_pct"),
            "sparkline_values": mkt.get("sparkline_values") or [],
        },
        "value_story": _value_story(assessor, mkt),
        "tax": tax,
        "permits": {
            "open_count": permits.get("open_count", 0),
            "total_count": permits.get("total_count", 0),
            "has_open": bool(permits.get("has_open")),
            "activity_url": permits.get("permits_activity_url") or "",
            "isd_url": permits.get("isd_portal_url") or "",
        },
        "renovation_ideas": renovations,
        "disclosures": disclosures[:12],
        "action_items": actions,
        "roi_status": "unavailable",
        "roi_note": (
            "TownEye does not publish renovation ROI percentages. National averages are often "
            "misleading locally — get contractor bids and an MLS CMA instead."
        ),
        "data_sources": sources,
        "disclaimer": (
            "TownEye Homeowner Insights is informational only. "
            "Not an appraisal, tax advice, legal opinion, or contractor estimate."
        ),
        "data_tier": "gold_homeowner",
    }


def _sparkline_svg(values: list[Any]) -> str:
    spark_vals = [float(v) for v in values if v is not None]
    if len(spark_vals) < 2:
        return ""
    lo, hi = min(spark_vals), max(spark_vals)
    span = (hi - lo) or 1.0
    width, height, gap = 200, 40, 2.0
    bar_w = max(2.0, (width - gap * (len(spark_vals) - 1)) / len(spark_vals))
    rects = []
    for i, v in enumerate(spark_vals):
        h = max(2.0, ((v - lo) / span) * (height - 4))
        x = i * (bar_w + gap)
        y = height - h
        rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="1" fill="#0b2545" opacity="{0.45 + 0.55 * (i / (len(spark_vals) - 1)):.2f}"/>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'aria-hidden="true">{"".join(rects)}</svg>'
    )


def render_homeowner_html(payload: dict[str, Any], address: str) -> str:
    assessor = payload.get("assessor") or {}
    mkt = payload.get("market") or {}
    tax = payload.get("tax") or {}
    permits = payload.get("permits") or {}
    ideas = payload.get("renovation_ideas") or []
    disclosures = payload.get("disclosures") or []
    actions = payload.get("action_items") or []

    idea_rows = "".join(
        f"<tr><td><strong>{i.get('project')}</strong><div class='small'>{i.get('note')}</div></td>"
        f"<td>{i.get('path')}</td></tr>"
        for i in ideas
    )
    disclosure_items = "".join(f"<li>{d}</li>" for d in disclosures)
    action_items = "".join(
        f"<li><span class='n'>{idx}</span><span>{a}</span></li>"
        for idx, a in enumerate(actions, start=1)
    )

    tax_rows = "".join(
        f"<tr><td>{r.get('fiscal_year') or '—'}</td>"
        f"<td>{r.get('bill_type') or 'Real estate'}</td>"
        f"<td>{r.get('status') or '—'}</td>"
        f"<td class='num'>{_fmt_money(r.get('balance_due'))}</td>"
        f"<td>{r.get('due_date') or '—'}</td></tr>"
        for r in (tax.get("records") or [])
    ) or "<tr><td colspan='5'>No cached tax bill for this parcel — use the portal link below.</td></tr>"

    portal = tax.get("portal_url") or ""
    portal_html = (
        f'<p><a class="btn" href="{portal}" target="_blank" rel="noopener">Open town tax portal</a></p>'
        if portal
        else ""
    )
    activity = permits.get("activity_url") or ""
    activity_html = (
        f'<a class="btn secondary" href="{activity}" target="_blank" rel="noopener">Town permit activity</a>'
        if activity
        else ""
    )
    isd = permits.get("isd_url") or ""
    isd_html = (
        f'<a class="btn secondary" href="{isd}" target="_blank" rel="noopener">ISD / OpenGov</a>'
        if isd
        else ""
    )
    spark = _sparkline_svg(list(mkt.get("sparkline_values") or []))
    spark_block = (
        f'<div class="spark"><div class="spark-lbl">ZIP ZHVI · last 12 months</div>{spark}</div>'
        if spark
        else ""
    )

    beds = payload.get("beds")
    baths = payload.get("baths")
    beds_baths = (
        f"{beds if beds is not None else '—'} / {baths if baths is not None else '—'}"
        if beds is not None or baths is not None
        else "—"
    )

    verdict_class = payload.get("headline_verdict_class") or ""
    verdict_css = {"v-green": "v-green", "v-yellow": "v-yellow", "v-red": "v-red"}.get(
        verdict_class, "v-yellow"
    )
    prepared = payload.get("prepared_on") or date.today().isoformat()
    sources = " · ".join(str(s) for s in (payload.get("data_sources") or []))
    disclaimer = payload.get("disclaimer") or ""
    value_story = payload.get("value_story") or payload.get("summary") or ""

    open_class = "hot" if permits.get("has_open") else "ok"
    gap = mkt.get("assessed_vs_zhvi_pct")
    gap_class = "ok"
    try:
        if gap is not None and abs(float(gap)) >= 8:
            gap_class = "hot"
        elif gap is not None and abs(float(gap)) >= 4:
            gap_class = "warn"
    except (TypeError, ValueError):
        pass

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Homeowner Insights — {address}</title>
<style>
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 13.5px; line-height: 1.55; color: #0b1f3a;
    max-width: 900px; margin: 28px auto; padding: 0 28px 40px; background: #fff;
  }}
  h1 {{ font-size: 24px; margin: 0 0 2px; color: #0b2545; letter-spacing: -0.02em; }}
  h2 {{
    font-size: 11.5px; letter-spacing: 1.5px; text-transform: uppercase;
    color: #0b2545; border-bottom: 2px solid #0b2545; padding: 18px 0 4px; margin: 22px 0 10px;
  }}
  .hd {{
    background: linear-gradient(135deg, #0b2545 0%, #163a66 55%, #1e4d7b 100%);
    color: #fff; border-radius: 10px; padding: 20px 22px 18px; margin-bottom: 14px;
  }}
  .hd h1 {{ color: #fff; }}
  .addr {{ font-size: 16px; font-weight: bold; margin-top: 6px; color: #e8eef7; }}
  .meta {{ font-size: 11px; color: #b8c7db; margin-top: 8px; }}
  .pill {{
    display: inline-block; font-size: 10px; letter-spacing: .6px; text-transform: uppercase;
    border: 1px solid rgba(255,255,255,.35); color: #e8eef7; padding: 2px 8px; border-radius: 999px; margin-right: 6px;
  }}
  .metrics {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0 4px;
  }}
  .metric {{
    border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; background: #f8fafc;
  }}
  .metric.hot {{ border-color: #f0c2c2; background: #fff5f5; }}
  .metric.warn {{ border-color: #f0d9a0; background: #fffbeb; }}
  .metric.ok {{ border-color: #c6e2c6; background: #f4faf4; }}
  .metric .lbl {{ display: block; font-size: 10px; letter-spacing: .8px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }}
  .metric .val {{ font-size: 17px; font-weight: bold; color: #0b2545; font-variant-numeric: tabular-nums; }}
  .metric .sub {{ display: block; font-size: 10.5px; color: #64748b; margin-top: 3px; }}
  .verdict {{ padding: 10px 14px; margin: 10px 0 12px; border-radius: 4px; }}
  .v-green {{ background: #dff1d6; color: #1a5b22; border-left: 6px solid #1a7a1a; }}
  .v-yellow {{ background: #fff3cf; color: #7a5a00; border-left: 6px solid #c89800; }}
  .v-red {{ background: #fadcdc; color: #7a1a1a; border-left: 6px solid #a02020; }}
  .story {{
    margin: 8px 0 4px; color: #1e293b; padding: 12px 14px; border-radius: 8px;
    background: #f8fafc; border: 1px solid #e2e8f0;
  }}
  .note {{
    font-size: 12px; color: #7a5a00; background: #fff8e8; border-left: 4px solid #c89800;
    padding: 8px 12px; margin: 10px 0;
  }}
  .honest {{
    font-size: 12px; color: #1a5b22; background: #f0faf0; border-left: 4px solid #1a7a1a;
    padding: 8px 12px; margin: 10px 0;
  }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 12.5px; }}
  th {{ background: #0b2545; color: #fff; text-align: left; padding: 7px 9px; font-size: 11px; }}
  td {{ padding: 6px 9px; border-bottom: 1px solid #e5e5e5; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #f7f9fc; }}
  .kv td:first-child {{ color: #555; width: 38%; }}
  .num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .small {{ font-size: 11px; color: #64748b; margin-top: 3px; }}
  .checklist {{ list-style: none; margin: 6px 0; padding: 0; }}
  .checklist li {{
    display: flex; gap: 10px; align-items: flex-start; margin: 0 0 8px;
    padding: 8px 10px; border: 1px solid #e2e8f0; border-radius: 6px; background: #fff;
  }}
  .checklist .n {{
    flex: 0 0 auto; width: 22px; height: 22px; border-radius: 50%;
    background: #0b2545; color: #fff; font-size: 11px; font-weight: bold;
    display: inline-flex; align-items: center; justify-content: center; margin-top: 1px;
  }}
  ul {{ margin: 6px 0; padding-left: 18px; }}
  li {{ margin: 4px 0; }}
  .btn {{
    display: inline-block; margin: 6px 8px 6px 0; padding: 8px 14px; background: #0b2545;
    color: #fff !important; text-decoration: none; border-radius: 4px; font-size: 12px;
  }}
  .btn.secondary {{ background: #fff; color: #0b2545 !important; border: 1px solid #0b2545; }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  .spark {{ margin: 8px 0 2px; }}
  .spark-lbl {{ font-size: 10px; letter-spacing: .8px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }}
  .footnote {{ font-size: 10.5px; color: #64748b; margin-top: 18px; border-top: 1px solid #dde3ee; padding-top: 10px; }}
  @media (max-width: 760px) {{
    .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .two {{ grid-template-columns: 1fr; }}
  }}
</style></head><body>
<div class="hd">
  <h1>Homeowner Insights</h1>
  <div class="addr">{address}</div>
  <div class="meta">
    <span class="pill">gold · live</span>
    Prepared {prepared} · Parcel {payload.get('parcel_id') or '—'} · {payload.get('zoning_stack') or '—'}
  </div>
</div>

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
  <div class="metric {gap_class}">
    <span class="lbl">Assessed vs ZHVI</span>
    <span class="val">{_fmt_pct(mkt.get('assessed_vs_zhvi_pct'))}</span>
    <span class="sub">12-mo ZIP {_fmt_pct(mkt.get('change_12m_pct'))}</span>
  </div>
  <div class="metric {open_class}">
    <span class="lbl">Open permits</span>
    <span class="val">{permits.get('open_count', 0)}</span>
    <span class="sub">{permits.get('total_count', 0)} on Gold</span>
  </div>
</div>

{spark_block}

<div class="verdict {verdict_css}">{payload.get('headline_verdict') or ''}</div>
<p class="story">{value_story}</p>

<div class="two">
  <div>
    <h2>1 · Your property</h2>
    <table class="kv">
      <tr><td>Owner of record</td><td>{payload.get('owner_name') or '—'}</td></tr>
      <tr><td>Property type</td><td>{payload.get('property_type') or '—'}</td></tr>
      <tr><td>Beds / baths</td><td>{beds_baths}</td></tr>
      <tr><td>Year built</td><td>{payload.get('year_built') or '—'}</td></tr>
      <tr><td>Finished area</td><td class="num">{_fmt_num(assessor.get('finished_sqft'), ' sf')}</td></tr>
      <tr><td>Lot size</td><td class="num">{_fmt_num(assessor.get('lot_sqft'), ' sf')}</td></tr>
      <tr><td>Assessed $/sf</td><td class="num">{_fmt_money(assessor.get('assessed_psf'))}</td></tr>
      <tr><td>Last sale</td><td>{_fmt_money(payload.get('last_sale_price'))} · {payload.get('last_sale_date') or 'n/a'}</td></tr>
    </table>
  </div>
  <div>
    <h2>2 · This month's checklist</h2>
    <ul class="checklist">{action_items}</ul>
    {activity_html}{isd_html}
  </div>
</div>

<h2>3 · Property tax</h2>
<p class="note">{tax.get('note') or ''}</p>
{portal_html}
<table>
  <tr><th>FY</th><th>Bill</th><th>Status</th><th>Balance</th><th>Due</th></tr>
  {tax_rows}
</table>

<h2>4 · Renovation paths (not ROI)</h2>
<p class="honest">{payload.get('roi_note') or ''}</p>
<table>
  <tr><th>Project</th><th>Typical permit path</th></tr>
  {idea_rows}
</table>

<h2>5 · Disclose / verify</h2>
<ul>{disclosure_items}</ul>

<p class="footnote">Sources: {sources}. {disclaimer}</p>
</body></html>"""
