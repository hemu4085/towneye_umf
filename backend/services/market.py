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


def _assessed_value(data: BriefData) -> float | None:
    if data.property_info is not None and data.property_info.assessed_value is not None:
        return data.property_info.assessed_value
    return None


def _lot_sqft(data: BriefData) -> float | None:
    if data.parcel.area_sqft is not None:
        return float(data.parcel.area_sqft)
    if data.property_info is not None and data.property_info.lot_size_sqft is not None:
        return float(data.property_info.lot_size_sqft)
    return None


def _market_fallback(data: BriefData) -> dict:
    ctx = _town_market_context(data.inputs.town_slug)
    assessed = _assessed_value(data)
    lot = _lot_sqft(data)
    return {
        "summary": (
            f"Market snapshot for {data.parcel.address} from TownEye Gold assessor and town "
            f"layers. Zoning verdict: {data.headline_verdict_text}."
        ),
        "median_price": ctx.get("median_sale_price") or assessed,
        "days_on_market": ctx.get("median_dom"),
        "inventory_months": ctx.get("months_of_inventory"),
        "comps_radius_mi": 0.25,
        "comps": [
            {
                "address": "Comparable sales — pilot MLS integration pending",
                "price": assessed,
                "sf": lot,
            },
        ],
        "trends": [
            f"Lot size: {lot:,} sf" if lot else "Lot size: see assessor record",
            f"Base zoning stack: {', '.join(h.code for h in data.base_zoning_hits[:3]) or '—'}",
            "Live assessor + zoning data; comp radius 0.25 mi at full launch",
        ],
        "data_sources": ["TownEye Gold property.parquet", "market-trends.parquet"],
        "fallback": True,
    }


def generate_market_report(data: BriefData) -> dict:
    if not get_settings().anthropic_api_key.strip():
        return _market_fallback(data)
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


def _fmt_price(value) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def render_market_html(payload: dict, address: str) -> str:
    comps = payload.get("comps") or []
    comp_rows = "".join(
        f"<tr><td>{c.get('address','—')}</td><td>{_fmt_price(c.get('price'))}</td>"
        f"<td>{c.get('sf','—')} sf</td></tr>"
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
