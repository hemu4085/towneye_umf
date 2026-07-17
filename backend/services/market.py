"""Market Trend Report — Gold ZHVI / assessor memo (not an appraisal)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import get_settings
from reports.buildability_brief import BriefData

_ZIP_RE = re.compile(r"\b(0\d{4})\b")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(n):
        return None
    return n


def _fmt_money(value: Any) -> str:
    n = _safe_float(value)
    if n is None:
        return "—"
    return f"${n:,.0f}"


def _fmt_pct(value: Any, signed: bool = True) -> str:
    n = _safe_float(value)
    if n is None:
        return "—"
    if signed:
        return f"{n:+.1f}%"
    return f"{n:.1f}%"


def _fmt_num(value: Any, suffix: str = "") -> str:
    n = _safe_float(value)
    if n is None:
        return "—"
    if abs(n - int(n)) < 1e-9:
        return f"{int(n):,}{suffix}"
    return f"{n:,.1f}{suffix}"


def _pct_change(newer: float | None, older: float | None) -> float | None:
    if newer is None or older is None or older == 0:
        return None
    return (newer / older - 1.0) * 100.0


def _load_trends_frame(town_slug: str) -> pd.DataFrame:
    path = Path(get_settings().gold_data_path) / town_slug / "market-trends.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    if df.empty:
        return df
    out = df.copy()
    out["observation_date"] = pd.to_datetime(out["observation_date"], utc=True, errors="coerce")
    out["metric_value"] = pd.to_numeric(out["metric_value"], errors="coerce")
    out["geo_value"] = out["geo_value"].astype(str)
    out["metric_name"] = out["metric_name"].astype(str).str.upper()
    return out.dropna(subset=["observation_date", "metric_value"])


def _zip_from_address(address: str | None) -> str | None:
    if not address:
        return None
    m = _ZIP_RE.search(address)
    return m.group(1) if m else None


def _series_for_zip(df: pd.DataFrame, zip_code: str, metric: str = "MEDIAN_SALE_PRICE") -> pd.DataFrame:
    if df.empty:
        return df
    sub = df[
        (df["metric_name"] == metric)
        & (df["geo_value"] == str(zip_code))
    ].sort_values("observation_date")
    return sub


def _pick_primary_zip(
    df: pd.DataFrame,
    *,
    address: str | None,
    assessed: float | None,
) -> tuple[str | None, list[str]]:
    """Return (primary_zip, available_zips)."""
    if df.empty:
        return None, []
    zips = sorted(df["geo_value"].dropna().astype(str).unique().tolist())
    hinted = _zip_from_address(address)
    if hinted and hinted in zips:
        return hinted, zips
    if not zips:
        return None, []
    if assessed is not None and len(zips) > 1:
        latest_by_zip: dict[str, float] = {}
        for z in zips:
            series = _series_for_zip(df, z)
            if series.empty:
                continue
            latest_by_zip[z] = float(series.iloc[-1]["metric_value"])
        if latest_by_zip:
            best = min(latest_by_zip.items(), key=lambda kv: abs(kv[1] - assessed))
            return best[0], zips
    return zips[0], zips


def _sparkline_bars(values: list[float], width: int = 180, height: int = 42) -> str:
    """Tiny inline SVG sparkline for the last N monthly medians."""
    if len(values) < 2:
        return ""
    lo = min(values)
    hi = max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    gap = 2.0
    bar_w = max(2.0, (width - gap * (n - 1)) / n)
    parts: list[str] = []
    for i, v in enumerate(values):
        h = max(2.0, ((v - lo) / span) * (height - 4))
        x = i * (bar_w + gap)
        y = height - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="1" fill="#0b2545" opacity="{0.45 + 0.55 * (i / (n - 1)):.2f}"/>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'aria-hidden="true" role="img">{"".join(parts)}</svg>'
    )


def _assessor_context(data: BriefData) -> dict[str, Any]:
    prop = data.property_info
    assessed = _safe_float(prop.assessed_value) if prop else None
    lot = None
    if data.parcel.area_sqft is not None:
        lot = float(data.parcel.area_sqft)
    elif prop and prop.lot_size_sqft is not None:
        lot = float(prop.lot_size_sqft)
    finished = _safe_float(prop.finished_area_sqft) if prop else None
    year_built = int(prop.year_built) if prop and prop.year_built else None
    building_type = prop.building_type if prop else None
    zone = data.primary_zone_code or (prop.zone_code if prop else None)

    land_val = None
    bldg_val = None
    # Enrich from property.parquet metadata when BriefData finished area is missing.
    try:
        gold = Path(get_settings().gold_data_path) / data.inputs.town_slug / "property.parquet"
        if gold.exists():
            pdf = pd.read_parquet(gold, columns=["parcel_id", "assessed_value", "metadata"])
            hit = pdf[pdf["parcel_id"].astype(str) == str(data.parcel.parcel_id)]
            if not hit.empty:
                import json as _json

                raw = hit.iloc[0].get("metadata")
                md: dict[str, Any] = {}
                if isinstance(raw, dict):
                    md = raw
                elif isinstance(raw, str) and raw.strip():
                    try:
                        parsed = _json.loads(raw)
                        if isinstance(parsed, dict):
                            md = parsed
                    except Exception:  # noqa: BLE001
                        md = {}
                if finished is None:
                    finished = _safe_float(
                        md.get("finished_area_sqft")
                        or md.get("finished_area_sqft_l3")
                    )
                land_val = _safe_float(md.get("land_val"))
                bldg_val = _safe_float(md.get("bldg_val"))
    except Exception:  # noqa: BLE001
        pass

    psf = None
    if assessed is not None and finished and finished > 0:
        psf = assessed / finished

    return {
        "assessed_value": assessed,
        "lot_sqft": lot,
        "finished_sqft": finished,
        "year_built": year_built,
        "building_type": building_type,
        "zone_code": zone,
        "assessed_psf": psf,
        "land_val": land_val,
        "bldg_val": bldg_val,
        "overlay": data.primary_overlay_code,
    }


def generate_market_report(data: BriefData) -> dict[str, Any]:
    """Build a deterministic Gold-backed market memo (no LLM required)."""
    assessor = _assessor_context(data)
    assessed = assessor["assessed_value"]
    df = _load_trends_frame(data.inputs.town_slug)

    primary_zip, available_zips = _pick_primary_zip(
        df,
        address=data.parcel.address,
        assessed=assessed,
    )

    series_rows: list[dict[str, Any]] = []
    latest = None
    as_of = None
    source = None
    mom = None
    qoq = None
    yoy = None
    spark_values: list[float] = []

    if primary_zip:
        series = _series_for_zip(df, primary_zip)
        if not series.empty:
            source = str(series.iloc[-1].get("te_source") or "zillow-zhvi")
            tail = series.tail(12)
            for _, row in tail.iterrows():
                val = float(row["metric_value"])
                spark_values.append(val)
                series_rows.append({
                    "date": row["observation_date"].strftime("%Y-%m"),
                    "value": val,
                })
            latest = float(series.iloc[-1]["metric_value"])
            as_of = series.iloc[-1]["observation_date"].strftime("%Y-%m-%d")
            if len(series) >= 2:
                mom = _pct_change(latest, float(series.iloc[-2]["metric_value"]))
            if len(series) >= 4:
                qoq = _pct_change(latest, float(series.iloc[-4]["metric_value"]))
            if len(series) >= 13:
                yoy = _pct_change(latest, float(series.iloc[-13]["metric_value"]))
            elif len(series) >= 12:
                yoy = _pct_change(latest, float(series.iloc[0]["metric_value"]))

    peer_zips: list[dict[str, Any]] = []
    for z in available_zips:
        s = _series_for_zip(df, z)
        if s.empty:
            continue
        peer_zips.append({
            "zip": z,
            "latest": float(s.iloc[-1]["metric_value"]),
            "as_of": s.iloc[-1]["observation_date"].strftime("%Y-%m"),
            "is_primary": z == primary_zip,
        })

    gap_pct = None
    gap_dollars = None
    if assessed is not None and latest is not None and latest != 0:
        gap_dollars = assessed - latest
        gap_pct = (assessed / latest - 1.0) * 100.0

    if latest is not None and as_of:
        summary = (
            f"ZIP {primary_zip} ZHVI median home value was {_fmt_money(latest)} as of {as_of} "
            f"({source or 'market-trends'}). "
        )
        if assessed is not None:
            summary += (
                f"Subject assessed value is {_fmt_money(assessed)} "
                f"({_fmt_pct(gap_pct)} vs ZIP ZHVI). "
            )
        if yoy is not None:
            summary += f"Trailing ~12-month ZIP move: {_fmt_pct(yoy)}. "
        summary += (
            "This is a market-context memo from TownEye Gold — not a CMA or appraisal. "
            "MLS sold comps are not connected in the pilot."
        )
    elif assessed is not None:
        summary = (
            f"No ZIP market-trends series matched for this parcel. "
            f"Assessor context only: assessed {_fmt_money(assessed)}. "
            "MLS comps are not connected in the pilot."
        )
    else:
        summary = (
            "Market-trends Gold and assessor value were unavailable for this parcel. "
            "Confirm with MLS / town assessor before underwriting."
        )

    signals: list[str] = []
    if mom is not None:
        signals.append(f"1-month ZIP ZHVI change: {_fmt_pct(mom)}")
    if qoq is not None:
        signals.append(f"3-month ZIP ZHVI change: {_fmt_pct(qoq)}")
    if yoy is not None:
        signals.append(f"~12-month ZIP ZHVI change: {_fmt_pct(yoy)}")
    if assessor["lot_sqft"]:
        signals.append(f"Lot size: {_fmt_num(assessor['lot_sqft'], ' sf')}")
    if assessor["finished_sqft"]:
        signals.append(f"Finished area: {_fmt_num(assessor['finished_sqft'], ' sf')}")
    if assessor["assessed_psf"] is not None:
        signals.append(f"Assessed $/sf (finished): {_fmt_money(assessor['assessed_psf'])}")
    if assessor["year_built"]:
        signals.append(f"Year built: {assessor['year_built']}")
    zone_bits = [x for x in (assessor["zone_code"], assessor["overlay"]) if x]
    if zone_bits:
        signals.append("Zoning stack: " + " · ".join(zone_bits))
    if not signals:
        signals.append("Limited Gold coverage for this parcel — expand market-trends ingest for DOM / inventory.")

    data_tier = "gold_zhvi" if latest is not None else "assessor_only"
    sources = []
    if latest is not None:
        sources.append(f"market-trends.parquet ({source or 'zillow-zhvi'} · ZIP {primary_zip})")
    sources.append("property.parquet (assessor)")
    if data.headline_verdict_text:
        sources.append("zoning GIS / Gold zoning stack (context only)")

    return {
        "report_title": "Market Trend Report",
        "prepared_on": date.today().isoformat(),
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "data_tier": data_tier,
        "summary": summary,
        "primary_zip": primary_zip,
        "available_zips": available_zips,
        "zhvi_latest": latest,
        "zhvi_as_of": as_of,
        "zhvi_source": source,
        "change_1m_pct": mom,
        "change_3m_pct": qoq,
        "change_12m_pct": yoy,
        "series_12m": series_rows,
        "sparkline_values": spark_values,
        "peer_zips": peer_zips,
        "assessor": assessor,
        "assessed_vs_zhvi_pct": gap_pct,
        "assessed_vs_zhvi_dollars": gap_dollars,
        "signals": signals,
        "comps_status": "unavailable",
        "comps_note": (
            "Sold comps require MLS / public deed sale feed. Not connected in this pilot — "
            "do not treat assessor value as a comparable sale."
        ),
        "data_sources": sources,
        "disclaimer": (
            "TownEye Market Trend Report is for directional diligence only. "
            "It is not an appraisal, CMA, or lending valuation. Verify with MLS and the town assessor."
        ),
        # Back-compat keys used by older callers / tests
        "median_price": latest if latest is not None else assessed,
        "days_on_market": None,
        "inventory_months": None,
        "comps_radius_mi": 0.25,
        "comps": [],
        "trends": signals,
        "fallback": latest is None,
    }


def render_market_html(payload: dict, address: str) -> str:
    assessor = payload.get("assessor") or {}
    series = payload.get("series_12m") or []
    peers = payload.get("peer_zips") or []
    signals = payload.get("signals") or payload.get("trends") or []
    spark = _sparkline_bars([float(v) for v in (payload.get("sparkline_values") or [])])

    series_rows = "".join(
        f"<tr><td>{r.get('date')}</td><td class='num'>{_fmt_money(r.get('value'))}</td></tr>"
        for r in reversed(series)
    ) or "<tr><td colspan='2'>No monthly ZIP series in Gold for this geography.</td></tr>"

    peer_rows = "".join(
        f"<tr class='{'primary' if p.get('is_primary') else ''}'>"
        f"<td>{p.get('zip')}{' <span class=\"tag\">Subject ZIP</span>' if p.get('is_primary') else ''}</td>"
        f"<td class='num'>{_fmt_money(p.get('latest'))}</td>"
        f"<td>{p.get('as_of') or '—'}</td></tr>"
        for p in peers
    ) or "<tr><td colspan='3'>No ZIP peers in market-trends Gold.</td></tr>"

    signal_items = "".join(f"<li>{s}</li>" for s in signals)

    change_1m = _fmt_pct(payload.get("change_1m_pct"))
    change_3m = _fmt_pct(payload.get("change_3m_pct"))
    change_12m = _fmt_pct(payload.get("change_12m_pct"))
    gap = _fmt_pct(payload.get("assessed_vs_zhvi_pct"))
    gap_amt = _fmt_money(payload.get("assessed_vs_zhvi_dollars"))

    zhvi = _fmt_money(payload.get("zhvi_latest"))
    assessed = _fmt_money(assessor.get("assessed_value"))
    primary_zip = payload.get("primary_zip") or "—"
    as_of = payload.get("zhvi_as_of") or "—"
    prepared = payload.get("prepared_on") or date.today().isoformat()
    parcel_id = payload.get("parcel_id") or "—"
    source = payload.get("zhvi_source") or "market-trends"
    tier = payload.get("data_tier") or "—"

    gap_class = "lbl"
    gap_n = _safe_float(payload.get("assessed_vs_zhvi_pct"))
    if gap_n is not None:
        if gap_n <= -5:
            gap_class = "ok"
        elif gap_n >= 5:
            gap_class = "wn"
        else:
            gap_class = "lbl"

    sources = payload.get("data_sources") or []
    source_line = " · ".join(str(s) for s in sources)
    disclaimer = payload.get("disclaimer") or ""
    comps_note = payload.get("comps_note") or ""
    summary = payload.get("summary") or ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Market Trend Report — {address}</title>
<style>
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 13.5px;
    line-height: 1.55;
    color: #0b1f3a;
    max-width: 860px;
    margin: 28px auto;
    padding: 0 28px 40px;
    background: #fff;
  }}
  h1 {{ font-size: 22px; margin: 0 0 2px; color: #0b2545; letter-spacing: .3px; }}
  h2 {{
    font-size: 11.5px; letter-spacing: 1.5px; text-transform: uppercase;
    color: #0b2545; border-bottom: 2px solid #0b2545; padding: 18px 0 4px; margin: 20px 0 10px;
  }}
  .hd {{ border-bottom: 1px solid #d5dbe7; padding-bottom: 12px; margin-bottom: 8px; position: relative; }}
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
  .metric .val {{ font-size: 17px; font-weight: bold; color: #0b2545; font-variant-numeric: tabular-nums; }}
  .metric .sub {{ display: block; font-size: 10.5px; color: #64748b; margin-top: 3px; }}
  .exec {{ margin: 8px 0 4px; color: #1e293b; }}
  .note {{
    font-size: 12px; color: #7a5a00; background: #fff8e8; border-left: 4px solid #c89800;
    padding: 8px 12px; margin: 10px 0;
  }}
  .two {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 18px; align-items: start; }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 12.5px; }}
  th {{ background: #0b2545; color: #fff; text-align: left; padding: 7px 9px; font-size: 11px; letter-spacing: .4px; }}
  td {{ padding: 6px 9px; border-bottom: 1px solid #e5e5e5; vertical-align: top; color: #0b1f3a; }}
  tr:nth-child(even) td {{ background: #f7f9fc; }}
  tr.primary td {{ background: #eef3fa; font-weight: 600; }}
  .kv td:first-child {{ color: #555; width: 42%; }}
  .num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .tag {{
    display: inline-block; background: #0b2545; color: #fff; font-size: 9px;
    padding: 1px 6px; border-radius: 8px; margin-left: 4px; letter-spacing: .3px; vertical-align: middle;
  }}
  .ok {{ color: #1a7a1a; font-weight: bold; }}
  .wn {{ color: #a06b00; font-weight: bold; }}
  .lbl {{ color: #334155; }}
  ul {{ margin: 6px 0; padding-left: 18px; color: #1e293b; }}
  li {{ margin: 3px 0; }}
  .spark {{ margin: 8px 0 2px; }}
  .footnote {{ font-size: 10.5px; color: #64748b; margin-top: 18px; border-top: 1px solid #dde3ee; padding-top: 10px; }}
  @media (max-width: 760px) {{
    .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .two {{ grid-template-columns: 1fr; }}
  }}
</style></head><body>
<div class="hd">
  <h1>Market Trend Report</h1>
  <div class="addr">{address}</div>
  <div class="meta">
    <span class="pill">{tier.replace('_', ' ')}</span>
    Prepared {prepared} · Parcel {parcel_id} · ZIP focus {primary_zip}
  </div>
</div>

<p class="note">{disclaimer}</p>

<div class="metrics">
  <div class="metric">
    <span class="lbl">ZIP ZHVI median</span>
    <span class="val">{zhvi}</span>
    <span class="sub">As of {as_of} · {source}</span>
  </div>
  <div class="metric">
    <span class="lbl">Assessed value</span>
    <span class="val">{assessed}</span>
    <span class="sub">Town assessor (Gold)</span>
  </div>
  <div class="metric">
    <span class="lbl">Assessed vs ZHVI</span>
    <span class="val {gap_class}">{gap}</span>
    <span class="sub">{gap_amt} dollar gap</span>
  </div>
  <div class="metric">
    <span class="lbl">12-mo ZIP move</span>
    <span class="val">{change_12m}</span>
    <span class="sub">1-mo {change_1m} · 3-mo {change_3m}</span>
  </div>
</div>

{f'<div class="spark">{spark}</div>' if spark else ''}

<h2>1 · Market narrative</h2>
<p class="exec">{summary}</p>

<h2>2 · Subject assessor context</h2>
<table class="kv">
  <tr><td>Assessed value</td><td class="num"><strong>{assessed}</strong></td></tr>
  <tr><td>Land / building (assessor)</td><td class="num">{_fmt_money(assessor.get('land_val'))} / {_fmt_money(assessor.get('bldg_val'))}</td></tr>
  <tr><td>Finished area</td><td class="num">{_fmt_num(assessor.get('finished_sqft'), ' sf')}</td></tr>
  <tr><td>Assessed $/sf</td><td class="num">{_fmt_money(assessor.get('assessed_psf'))}</td></tr>
  <tr><td>Lot size</td><td class="num">{_fmt_num(assessor.get('lot_sqft'), ' sf')}</td></tr>
  <tr><td>Year built</td><td>{assessor.get('year_built') or '—'}</td></tr>
  <tr><td>Building type</td><td>{assessor.get('building_type') or '—'}</td></tr>
  <tr><td>Zoning stack</td><td>{' · '.join(x for x in (assessor.get('zone_code'), assessor.get('overlay')) if x) or '—'}</td></tr>
</table>

<div class="two">
  <div>
    <h2>3 · ZIP ZHVI history (12 mo)</h2>
    <table>
      <tr><th>Month</th><th>Median value</th></tr>
      {series_rows}
    </table>
  </div>
  <div>
    <h2>4 · Arlington ZIP peers</h2>
    <table>
      <tr><th>ZIP</th><th>Latest ZHVI</th><th>As of</th></tr>
      {peer_rows}
    </table>
    <h2>5 · Local signals</h2>
    <ul>{signal_items}</ul>
  </div>
</div>

<h2>6 · Comparable sales</h2>
<p class="note">{comps_note}</p>

<p class="footnote">Sources: {source_line}. {disclaimer}</p>
</body></html>"""
