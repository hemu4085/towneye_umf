"""Development Pro Forma — envelope + Claude."""

from __future__ import annotations

from backend.config import get_settings
from backend.services.llm import generate_json_report
from reports.buildability_brief import BriefData


def _proforma_fallback(data: BriefData) -> dict:
    scenarios = []
    for e in data.envelopes[:3]:
        hard = (e.max_gfa_sqft or 0) * 475
        scenarios.append({
            "name": e.label,
            "units": max(1, int((e.max_gfa_sqft or 0) // 900)),
            "total_gfa": e.max_gfa_sqft,
            "hard_cost": hard,
            "roi_pct": round(min(28.0, max(8.0, (e.max_far or 0.4) * 40)), 1),
            "notes": e.rationale or "Envelope from live zoning stack",
        })
    if not scenarios:
        scenarios.append({
            "name": "Base",
            "units": 1,
            "total_gfa": data.parcel.area_sqft,
            "hard_cost": (data.parcel.area_sqft or 0) * 475,
            "roi_pct": 12.0,
            "notes": "Derived from parcel area — refine with full envelope",
        })
    return {
        "scenarios": scenarios,
        "assumptions": [
            "Hard cost $475/sf (RSMeans MA indicative, pilot)",
            "Live zoning envelopes from TownEye Gold",
            "Sale pricing not connected to MLS in pilot",
        ],
        "sensitivity": {"low": 8.0, "mid": 14.0, "high": 22.0},
        "fallback": True,
    }


def generate_proforma(data: BriefData) -> dict:
    if not get_settings().anthropic_api_key.strip():
        return _proforma_fallback(data)
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
