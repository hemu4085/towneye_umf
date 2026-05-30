"""Development Pro Forma — envelope + Claude."""

from __future__ import annotations

from backend.services.llm import generate_json_report
from reports.buildability_brief import BriefData


def generate_proforma(data: BriefData) -> dict:
    env_lines = []
    for e in data.envelopes:
        env_lines.append(
            f"{e.label}: max_gfa={e.max_gfa_sqft}, qualifies={e.qualifies}, rationale={e.rationale}",
        )
    prompt = f"""Build a development pro forma JSON for a MA parcel.
Address: {data.parcel.address}
Lot: {data.parcel.area_sqft} sf
Zoning verdict: {data.headline_verdict_text}
Envelopes:
{chr(10).join(env_lines)}

Use RSMeans MA 2026 hard cost $425–$525/sf. Return JSON:
scenarios (array of 3: name, units, total_gfa, hard_cost, sale_price, roi_pct, notes),
assumptions (array), sensitivity (object with low/mid/high roi_pct).
"""
    return generate_json_report("You are a MA development analyst for TownEye.", prompt)


def render_proforma_html(payload: dict, address: str) -> str:
    rows = ""
    for s in payload.get("scenarios") or []:
        rows += f"""<tr>
          <td>{s.get('name','—')}</td><td>{s.get('units','—')}</td>
          <td>{s.get('total_gfa','—')}</td><td>{s.get('hard_cost','—')}</td>
          <td>{s.get('roi_pct','—')}%</td></tr>"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{{font-family:'DM Sans',sans-serif;max-width:780px;margin:24px auto}}
table{{width:100%;border-collapse:collapse}} th{{background:#0B1F3A;color:#fff;padding:8px}}
td{{padding:8px;border-bottom:1px solid #eee}}</style></head><body>
<h1>Development Pro Forma</h1><p><strong>{address}</strong></p>
<table><tr><th>Scenario</th><th>Units</th><th>GFA</th><th>Hard cost</th><th>ROI</th></tr>{rows}</table>
</body></html>"""
