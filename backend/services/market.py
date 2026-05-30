"""Market Snapshot — Claude + Gold market-trends when available."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.config import get_settings
from backend.services.llm import generate_json_report
from reports.buildability_brief import BriefData


def _town_market_context(town_slug: str) -> dict:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}
    row = df.iloc[-1].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in row.items()}


def generate_market_report(data: BriefData) -> dict:
    ctx = _town_market_context(data.inputs.town_slug)
    prompt = f"""Generate a Massachusetts real estate Market Snapshot JSON for:
Address: {data.parcel.address}
Town: {data.inputs.town_slug}
Parcel: {data.parcel.parcel_id}
Town market data: {ctx}

Return JSON keys:
summary (string), median_price (number|null), days_on_market (number|null),
inventory_months (number|null), comps_radius_mi (0.25), comps (array of 3 objects with address, price, sf),
trends (array of 3 bullet strings), data_sources (array of strings).
Use conservative estimates if exact comps unavailable."""
    return generate_json_report(
        "You are TownEye, a MA real estate intelligence analyst.",
        prompt,
    )


def render_market_html(payload: dict, address: str) -> str:
    comps = payload.get("comps") or []
    comp_rows = "".join(
        f"<tr><td>{c.get('address','—')}</td><td>${c.get('price',0):,}</td><td>{c.get('sf','—')} sf</td></tr>"
        for c in comps
    ) or "<tr><td colspan='3'>No comps in response</td></tr>"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{{font-family:'DM Sans',sans-serif;max-width:780px;margin:24px auto;color:#0B1F3A}}
h1{{border-bottom:3px solid #C9A84C;font-family:Georgia,serif}}
table{{width:100%;border-collapse:collapse}} th{{background:#0B1F3A;color:#fff;padding:8px}}
td{{padding:8px;border-bottom:1px solid #eee}}</style></head><body>
<h1>Market Snapshot</h1><p><strong>{address}</strong></p>
<p>{payload.get('summary','')}</p>
<ul>{''.join(f'<li>{t}</li>' for t in (payload.get('trends') or []))}</ul>
<table><tr><th>Comp</th><th>Price</th><th>Size</th></tr>{comp_rows}</table>
</body></html>"""
