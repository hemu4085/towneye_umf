"""Homeowner Full Property Report — all sections in one document."""

from __future__ import annotations

import re

from backend.services import buildability, market, risk, zoning
from backend.services.buildability import collect_brief_data
from backend.services.demo_reports import get_demo_report_html
from backend.services.market import _assessed_value, _lot_sqft, generate_market_report, render_market_html
from reports.buildability_brief import BriefData


def _extract_body(html: str) -> str:
    match = re.search(r"<body[^>]*>(.*)</body>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else html


def _fmt_money(value) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _property_facts_html(data: BriefData) -> str:
    p = data.parcel
    prop = data.property_info
    rows = [
        ("Address", p.address or "—"),
        ("Parcel ID", p.parcel_id),
        ("Lot size (GIS)", f"{p.area_sqft:,.0f} sq ft" if p.area_sqft else "—"),
    ]
    if prop:
        rows.extend(
            [
                ("Year built", str(prop.year_built) if prop.year_built else "—"),
                ("Beds / baths", f"{prop.beds or '—'} / {prop.baths or '—'}"),
                ("Finished area", f"{prop.finished_area_sqft:,.0f} sf" if prop.finished_area_sqft else "—"),
                ("Assessed value", _fmt_money(prop.assessed_value)),
                ("Last sale", f"{_fmt_money(prop.last_sale_price)} ({prop.last_sale_date or 'n/a'})"),
                ("Owner of record", prop.owner_name or "— (see registry)"),
                ("Use code", prop.luc_description or prop.luc or "—"),
            ],
        )
    trs = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    return f"""
    <section class="te-section" id="facts">
      <h2>Property snapshot</h2>
      <p class="te-lead">Assessor &amp; GIS facts from TownEye Gold data (not a live MLS listing).</p>
      <table class="te-facts">{trs}</table>
    </section>
    """


def _buildability_section_html(town_slug: str, parcel_id: str, data: BriefData, prepared_for: str | None) -> str:
    html = get_demo_report_html(town_slug, parcel_id, "buildability")
    if html is None:
        html = buildability.generate_buildability_html(town_slug, parcel_id, prepared_for)
    inner = _extract_body(html)
    return f"""
    <section class="te-section page-break" id="buildability">
      <h2>Buildability &amp; zoning development</h2>
      {inner}
    </section>
    """


def generate_homeowner_full_html(
    town_slug: str,
    parcel_id: str,
    prepared_for: str | None = None,
) -> str:
    data = collect_brief_data(town_slug, parcel_id, prepared_for)
    market_payload = generate_market_report(data)
    market_body = _extract_body(render_market_html(market_payload, data.parcel.address or ""))
    risk_body = _extract_body(risk.render_risk_html(data))
    zoning_body = _extract_body(zoning.render_zoning_html(data))
    assessed = _assessed_value(data)
    lot = _lot_sqft(data)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Full Property Report — {data.parcel.address}</title>
<style>
  body {{ font-family: 'DM Sans', Arial, sans-serif; color: #0B1F3A; max-width: 820px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-family: Georgia, serif; border-bottom: 3px solid #C9A84C; padding-bottom: 8px; }}
  h2 {{ font-family: Georgia, serif; color: #0B1F3A; margin-top: 0; }}
  .te-hero {{ background: #0B1F3A; color: #F5F0E8; padding: 20px 24px; border-radius: 8px; margin-bottom: 24px; }}
  .te-hero h1 {{ color: #C9A84C; border: none; margin: 0 0 8px; }}
  .te-verdict {{ font-size: 1.1rem; color: #C9A84C; font-weight: 600; }}
  .te-section {{ margin: 32px 0; }}
  .te-lead {{ color: #555; font-size: 14px; }}
  .te-facts {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  .te-facts th {{ text-align: left; background: #0B1F3A; color: #fff; padding: 8px; width: 36%; }}
  .te-facts td {{ padding: 8px; border-bottom: 1px solid #e5e5e5; }}
  .page-break {{ page-break-before: always; }}
  .te-disclaimer {{ font-size: 11px; color: #666; margin-top: 40px; border-top: 1px solid #ccc; padding-top: 12px; }}
</style></head><body>
  <div class="te-hero">
    <h1>Full Property Report</h1>
    <p><strong>{data.parcel.address}</strong></p>
    <p class="te-verdict">{data.headline_verdict_text}</p>
    <p style="font-size:13px;margin-top:12px;opacity:0.9">
      Assessed { _fmt_money(assessed) } · Lot {f"{lot:,.0f} sq ft" if lot else "—"}
    </p>
  </div>
  {_property_facts_html(data)}
  <section class="te-section" id="zoning">
    <h2>Zoning summary</h2>
    {zoning_body}
  </section>
  {_buildability_section_html(town_slug, parcel_id, data, prepared_for)}
  <section class="te-section page-break" id="risk">
    <h2>Risk &amp; constraints</h2>
    {risk_body}
  </section>
  <section class="te-section page-break" id="market">
    <h2>Market context</h2>
    {market_body}
  </section>
  <p class="te-disclaimer">
    TownEye Full Property Report — informational only, not an appraisal, legal opinion, or listing.
    Verify all permits and zoning with the municipality. © towneye.ai
  </p>
</body></html>"""
