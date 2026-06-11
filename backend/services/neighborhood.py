"""Neighborhood Intel Card — Claude synthesis."""

from __future__ import annotations

from backend.services.llm import generate_json_report
from reports.buildability_brief import BriefData


def generate_neighborhood(data: BriefData) -> dict:
    prompt = f"""Neighborhood Intel JSON for MA property:
Address: {data.parcel.address}
Lat/Lon: {data.parcel.centroid_lat}, {data.parcel.centroid_lon}
Town: {data.inputs.town_slug}

Return JSON: walk_score (int|null), transit_summary (string), schools (array of name/rating),
commute_times (array of destination/minutes), recent_permits (array), highlights (array of bullets).
Note data limitations clearly in data_sources array."""
    return generate_json_report("You are TownEye neighborhood intelligence.", prompt)


def render_neighborhood_html(payload: dict, address: str) -> str:
    bullets = "".join(f"<li>{h}</li>" for h in (payload.get("highlights") or []))
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body{{font-family:'DM Sans',sans-serif;max-width:780px;margin:24px auto}}
  .logo-header {{ position: absolute; top: 24px; right: 20px; height: 32px; opacity: 0.8; }}
</style></head><body>
<div style="position: relative;">
  <img src="https://demo.towneye.ai/logo.png" alt="TownEye Logo" class="logo-header" />
  <h1>Neighborhood Intel</h1><p><strong>{address}</strong></p>
</div>
<p>Walk score: {payload.get('walk_score','N/A')} · {payload.get('transit_summary','')}</p>
<ul>{bullets}</ul></body></html>"""
