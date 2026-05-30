"""Lender Due Diligence Pack — bundles risk + zoning + buildability summary."""

from __future__ import annotations

from backend.services.risk import generate_risk_json
from backend.services.zoning import generate_zoning_json
from reports.buildability_brief import BriefData


def generate_lender_html(data: BriefData, prepared_for: str | None) -> str:
    risk = generate_risk_json(data)
    zoning = generate_zoning_json(data)
    verdict = data.headline_verdict_text
    risk_rows = "".join(
        f"<li><strong>{c['label']}</strong>: {c['status_label']} — {c['detail']}</li>"
        for c in risk["constraints"]
    )
    zone_list = ", ".join(
        [z["zone_code"] for z in zoning.get("base_zones", []) + zoning.get("overlay_zones", [])],
    )
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{{font-family:'DM Sans',sans-serif;max-width:780px;margin:24px auto;color:#0B1F3A}}
h1,h2{{font-family:Georgia,serif}} h2{{border-bottom:2px solid #C9A84C;padding-bottom:4px}}
.section{{margin:20px 0}}
</style></head><body>
<h1>Lender Due Diligence Pack</h1>
<p><strong>{data.parcel.address}</strong> · Parcel {data.parcel.parcel_id}</p>
<div class="section"><h2>Buildability Verdict</h2><p>{verdict}</p></div>
<div class="section"><h2>Zoning Stack</h2><p>{zone_list or 'See full zoning card'}</p></div>
<div class="section"><h2>Risk &amp; Constraints</h2><ul>{risk_rows}</ul></div>
<p style="font-size:11px;color:#666">Bundled from TownEye Gold data lake. Not a loan approval or legal opinion.</p>
</body></html>"""
