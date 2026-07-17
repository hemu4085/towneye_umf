"""Neighborhood Guide — Gold-backed area intel for buyers / agents ($44 tier).

No invented Walk Scores or school ratings. Uses assessor street context, ZIP ZHVI,
MBTA alerts, APS calendar events, DPW capital projects, and town-profile narrative.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services import market
from backend.services.zoning import _zoning_constraints
from reports.buildability_brief import BriefData

_STREET_SUFFIXES = (
    " STREET",
    " ST",
    " AVENUE",
    " AVE",
    " ROAD",
    " RD",
    " DRIVE",
    " DR",
    " LANE",
    " LN",
    " COURT",
    " CT",
    " PLACE",
    " PL",
    " WAY",
    " TERRACE",
    " TER",
    " PARKWAY",
    " PKWY",
    " CIRCLE",
    " CIR",
)


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


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_md(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").upper()).strip()


def _street_core(address: str | None) -> str:
    needle = _norm(address).split(",")[0]
    # Strip house numbers and ranges: "5-7 BELKNAP ST", "102-106 MASS AVE", "34A ACTON ST"
    needle = re.sub(r"^[\d]+[A-Z]?(?:\s*[-/]\s*[\d]+[A-Z]?)?\s+", "", needle)
    for token in _STREET_SUFFIXES:
        if needle.endswith(token):
            return needle[: -len(token)].strip()
    return needle


@lru_cache(maxsize=8)
def _read_parquet(town_slug: str, name: str) -> pd.DataFrame:
    path = Path(get_settings().gold_data_path) / town_slug / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _same_street_neighbors(town_slug: str, parcel_id: str, address: str | None, limit: int = 8) -> list[dict[str, Any]]:
    df = _read_parquet(town_slug, "property.parquet")
    if df.empty or "address" not in df.columns:
        return []
    core = _street_core(address)
    if not core:
        return []
    work = df.copy()
    work["_addr"] = work["address"].astype(str).str.upper()
    hits = work[work["_addr"].str.contains(core, regex=False, na=False)]
    hits = hits[hits["parcel_id"].astype(str) != str(parcel_id)]
    if hits.empty:
        return []
    if "assessed_value" in hits.columns:
        hits = hits.sort_values("assessed_value", ascending=False)
    rows: list[dict[str, Any]] = []
    for _, row in hits.head(limit).iterrows():
        rows.append({
            "address": str(row.get("address") or "—"),
            "assessed_value": _safe_float(row.get("assessed_value")),
            "year_built": int(row["year_built"]) if pd.notna(row.get("year_built")) else None,
            "zone_code": str(row.get("zone_code") or "") or None,
        })
    return rows


def _transit_alerts(town_slug: str, limit: int = 5) -> list[dict[str, Any]]:
    df = _read_parquet(town_slug, "transit.parquet")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        md = _parse_md(row.get("metadata"))
        rows.append({
            "event_type": str(row.get("event_type") or md.get("event_type") or "TRANSIT"),
            "summary": str(
                row.get("event_name")
                or row.get("summary")
                or md.get("summary")
                or md.get("header")
                or "Transit advisory"
            ),
            "status": str(row.get("status") or md.get("status") or "ACTIVE"),
        })
    return rows


def _school_calendar(town_slug: str, limit: int = 6) -> list[dict[str, Any]]:
    df = _read_parquet(town_slug, "school-calendar.parquet")
    if df.empty:
        return []
    work = df.copy()
    date_col = None
    for cand in ("start_time", "event_date", "start_date", "observation_date", "date"):
        if cand in work.columns:
            date_col = cand
            break
    name_col = "event_name" if "event_name" in work.columns else None
    if date_col:
        work[date_col] = pd.to_datetime(work[date_col], utc=True, errors="coerce")
        work = work.sort_values(date_col)
        today = datetime.now(timezone.utc)
        future = work[work[date_col].isna() | (work[date_col] >= today)]
        if not future.empty:
            work = future
    rows: list[dict[str, Any]] = []
    for _, row in work.head(limit).iterrows():
        md = _parse_md(row.get("metadata"))
        name = str(
            (row.get(name_col) if name_col else None)
            or row.get("summary")
            or md.get("summary")
            or md.get("title")
            or "School calendar event"
        )
        when = None
        if date_col and pd.notna(row.get(date_col)):
            when = pd.Timestamp(row[date_col]).strftime("%Y-%m-%d")
        rows.append({"date": when, "name": name})
    return rows


def _infra_nearby(town_slug: str, address: str | None, limit: int = 5) -> list[dict[str, Any]]:
    df = _read_parquet(town_slug, "infra-projects.parquet")
    if df.empty:
        return []
    core = _street_core(address)
    work = df.copy()
    text_cols = [c for c in ("project_name", "location_description", "summary", "name") if c in work.columns]
    scored: list[tuple[int, dict[str, Any]]] = []
    for _, row in work.iterrows():
        blob = _norm(" ".join(str(row.get(c) or "") for c in text_cols))
        md = _parse_md(row.get("metadata"))
        blob = f"{blob} {_norm(md.get('location') or '')} {_norm(md.get('summary') or '')}"
        score = 10 if core and core in blob else 0
        # East Arlington / Mass Ave corridor boost when subject is near those streets
        if any(tok in blob for tok in ("MASS", "BROADWAY", "EAST ARLINGTON", "SPY POND")):
            score += 2
        name = str(
            row.get("project_name")
            or row.get("name")
            or md.get("project_name")
            or "Capital project"
        )
        status = str(row.get("status") or md.get("status") or "—")
        loc = str(
            row.get("location_description")
            or md.get("location")
            or md.get("corridor")
            or ""
        )
        scored.append((score, {"name": name, "status": status, "location": loc, "score": score}))
    scored.sort(key=lambda x: -x[0])
    # Prefer street matches; otherwise return top town projects
    picked = [r for s, r in scored if s >= 10][:limit]
    if not picked:
        picked = [r for _, r in scored[:limit]]
    return picked


def _town_profile(town_slug: str) -> dict[str, Any]:
    df = _read_parquet(town_slug, "town-profile.parquet")
    if df.empty:
        return {}
    row = df.iloc[0]
    md = _parse_md(row.get("metadata"))
    employers_raw = md.get("major_employers") or row.get("major_employers") or []
    if isinstance(employers_raw, str):
        try:
            employers_raw = json.loads(employers_raw)
        except json.JSONDecodeError:
            employers_raw = [employers_raw]
    # Intentionally omit mock walkability_score / transit_score / school_rating
    return {
        "town_name": str(row.get("town_name") or town_slug),
        "neighborhood_vibes": str(row.get("neighborhood_vibes") or md.get("summary") or "") or None,
        "housing_character": str(row.get("housing_character") or "") or None,
        "political_lean": str(row.get("political_lean") or "") or None,
        "nimby_index": _safe_float(row.get("nimby_index")),
        "major_employers": list(employers_raw) if isinstance(employers_raw, list) else [],
        "sweet_spots": list(md.get("sweet_spots") or []) if isinstance(md.get("sweet_spots"), list) else [],
        "risks": list(md.get("risks") or []) if isinstance(md.get("risks"), list) else [],
        "source": str(row.get("te_source") or md.get("llm_model") or "town-profile"),
    }


def _street_stats(neighbors: list[dict[str, Any]], subject_assessed: float | None) -> dict[str, Any]:
    vals = [n["assessed_value"] for n in neighbors if n.get("assessed_value") is not None]
    if not vals:
        return {"neighbor_count": len(neighbors), "median_assessed": None, "min_assessed": None, "max_assessed": None}
    vals_sorted = sorted(vals)
    mid = vals_sorted[len(vals_sorted) // 2]
    return {
        "neighbor_count": len(neighbors),
        "median_assessed": mid,
        "min_assessed": vals_sorted[0],
        "max_assessed": vals_sorted[-1],
        "subject_vs_street_median_pct": (
            ((subject_assessed / mid) - 1.0) * 100.0
            if subject_assessed is not None and mid
            else None
        ),
    }


def _highlights(
    data: BriefData,
    *,
    mkt: dict[str, Any],
    street: dict[str, Any],
    transit: list[dict[str, Any]],
    infra: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[str]:
    out: list[str] = []
    assessor = mkt.get("assessor") or {}
    core = _street_core(data.parcel.address)
    if core and street.get("neighbor_count"):
        out.append(
            f"{core.title()} street context: {street['neighbor_count']} nearby assessor records "
            f"(median assessed {_fmt_money(street.get('median_assessed'))})."
        )
    if mkt.get("zhvi_latest") is not None:
        out.append(
            f"ZIP {mkt.get('primary_zip')} ZHVI {_fmt_money(mkt.get('zhvi_latest'))} "
            f"as of {mkt.get('zhvi_as_of')} · 12-mo {_fmt_pct(mkt.get('change_12m_pct'))}."
        )
    if assessor.get("assessed_vs_zhvi_pct") is not None or mkt.get("assessed_vs_zhvi_pct") is not None:
        gap = mkt.get("assessed_vs_zhvi_pct")
        out.append(f"Subject assessed vs ZIP ZHVI: {_fmt_pct(gap)}.")
    zone_bits = [x for x in (data.primary_zone_code, data.primary_overlay_code) if x]
    if zone_bits:
        out.append("Zoning stack: " + " · ".join(zone_bits) + ".")
    for c in _zoning_constraints(data):
        if c.get("status") == "flagged":
            out.append(f"Watch: {c.get('label')} — {c.get('detail') or 'see Zoning report'}.")
        elif c.get("status") == "clear" and c.get("label"):
            out.append(f"Clear on file: {c.get('label')}.")
            break
    if transit:
        out.append(f"Active transit note: {transit[0].get('summary')}")
    if infra:
        out.append(f"Nearby capital project: {infra[0].get('name')} ({infra[0].get('status')}).")
    if profile.get("sweet_spots"):
        out.append("Town sweet spots (profile): " + "; ".join(str(x) for x in profile["sweet_spots"][:3]) + ".")
    # Dedup
    seen: set[str] = set()
    uniq: list[str] = []
    for h in out:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return uniq[:10]


def generate_neighborhood(data: BriefData) -> dict[str, Any]:
    """Deterministic Gold neighborhood guide — no LLM required."""
    mkt = market.generate_market_report(data)
    assessor = mkt.get("assessor") or {}
    neighbors = _same_street_neighbors(
        data.inputs.town_slug,
        data.parcel.parcel_id,
        data.parcel.address,
    )
    street = _street_stats(neighbors, assessor.get("assessed_value"))
    transit = _transit_alerts(data.inputs.town_slug)
    calendar = _school_calendar(data.inputs.town_slug)
    infra = _infra_nearby(data.inputs.town_slug, data.parcel.address)
    profile = _town_profile(data.inputs.town_slug)
    highlights = _highlights(
        data,
        mkt=mkt,
        street=street,
        transit=transit,
        infra=infra,
        profile=profile,
    )

    street_name = _street_core(data.parcel.address)
    area_label = f"{street_name.title()} · {profile.get('town_name') or data.inputs.town_slug}" if street_name else (
        profile.get("town_name") or data.inputs.town_slug
    )

    summary_parts = [
        f"Neighborhood guide for {data.parcel.address}.",
    ]
    if profile.get("neighborhood_vibes"):
        summary_parts.append(str(profile["neighborhood_vibes"]))
    else:
        summary_parts.append(
            "Built from TownEye Gold street assessor context, ZIP market trends, transit alerts, "
            "school calendar, and capital-project layers."
        )
    if mkt.get("zhvi_latest") is not None:
        summary_parts.append(
            f"Local pricing pulse: ZIP {mkt.get('primary_zip')} ZHVI {_fmt_money(mkt.get('zhvi_latest'))}."
        )

    sources = list(mkt.get("data_sources") or [])
    sources.extend([
        "property.parquet (same-street assessor context)",
        "transit.parquet (MBTA alerts)",
        "school-calendar.parquet (APS events — not ratings)",
        "infra-projects.parquet (DPW capital plan)",
        "town-profile.parquet (narrative only)",
    ])

    return {
        "report_title": "Neighborhood Guide",
        "prepared_on": date.today().isoformat(),
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "area_label": area_label,
        "summary": " ".join(summary_parts),
        "lat": data.parcel.centroid_lat,
        "lng": data.parcel.centroid_lon,
        "zoning_stack": " · ".join(x for x in (data.primary_zone_code, data.primary_overlay_code) if x) or "—",
        "assessor": assessor,
        "market": {
            "primary_zip": mkt.get("primary_zip"),
            "zhvi_latest": mkt.get("zhvi_latest"),
            "zhvi_as_of": mkt.get("zhvi_as_of"),
            "change_12m_pct": mkt.get("change_12m_pct"),
            "assessed_vs_zhvi_pct": mkt.get("assessed_vs_zhvi_pct"),
            "series_12m": mkt.get("series_12m") or [],
            "sparkline_values": mkt.get("sparkline_values") or [],
        },
        "street": street,
        "neighbors": neighbors,
        "transit_alerts": transit,
        "school_calendar": calendar,
        "infra_projects": infra,
        "town_profile": {
            "neighborhood_vibes": profile.get("neighborhood_vibes"),
            "housing_character": profile.get("housing_character"),
            "political_lean": profile.get("political_lean"),
            "nimby_index": profile.get("nimby_index"),
            "major_employers": profile.get("major_employers") or [],
            "sweet_spots": profile.get("sweet_spots") or [],
            "risks": profile.get("risks") or [],
            "source": profile.get("source"),
        },
        "highlights": highlights,
        "walk_score": None,
        "transit_score": None,
        "schools": [],
        "walk_score_note": (
            "Walk Score® / Transit Score® are not licensed in this pilot. "
            "We show live MBTA alerts and street/market context instead of invented scores."
        ),
        "schools_note": (
            "School ratings are not in TownEye Gold. Below are Arlington Public Schools calendar "
            "events only — confirm district assignment on the APS / MLS listing."
        ),
        "data_sources": sources,
        "disclaimer": (
            "TownEye Neighborhood Guide is a $44-tier area briefing for buyers and agents. "
            "It is not a school rating, Walk Score, or appraisal. Verify marketing claims before publishing."
        ),
        "data_tier": "gold_neighborhood",
        "fallback": False,
        # Back-compat for older HTML
        "transit_summary": transit[0]["summary"] if transit else "No active MBTA alerts in Gold.",
    }


def render_neighborhood_html(payload: dict, address: str) -> str:
    assessor = payload.get("assessor") or {}
    mkt = payload.get("market") or {}
    street = payload.get("street") or {}
    neighbors = payload.get("neighbors") or []
    transit = payload.get("transit_alerts") or []
    calendar = payload.get("school_calendar") or []
    infra = payload.get("infra_projects") or []
    profile = payload.get("town_profile") or {}
    highlights = payload.get("highlights") or []

    spark_vals = [float(v) for v in (mkt.get("sparkline_values") or [])]
    spark = ""
    if len(spark_vals) >= 2:
        lo, hi = min(spark_vals), max(spark_vals)
        span = (hi - lo) or 1.0
        width, height, gap = 180, 36, 2.0
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
        spark = (
            f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'aria-hidden="true">{"".join(rects)}</svg>'
        )

    neighbor_rows = "".join(
        f"<tr><td>{n.get('address')}</td>"
        f"<td class='num'>{_fmt_money(n.get('assessed_value'))}</td>"
        f"<td>{n.get('year_built') or '—'}</td>"
        f"<td>{n.get('zone_code') or '—'}</td></tr>"
        for n in neighbors
    ) or "<tr><td colspan='4'>No same-street assessor neighbors matched in Gold.</td></tr>"

    transit_items = "".join(f"<li>{t.get('summary')}</li>" for t in transit) or (
        "<li>No active transit alerts in Gold right now.</li>"
    )
    cal_items = "".join(
        f"<li><strong>{c.get('date') or 'TBD'}</strong> — {c.get('name')}</li>" for c in calendar
    ) or "<li>No school-calendar events loaded.</li>"
    infra_items = "".join(
        f"<li><strong>{p.get('name')}</strong> · {p.get('status')}"
        f"{(' — ' + p['location']) if p.get('location') else ''}</li>"
        for p in infra
    ) or "<li>No capital projects matched.</li>"
    highlight_items = "".join(f"<li>{h}</li>" for h in highlights)
    employer_items = "".join(f"<li>{e}</li>" for e in (profile.get("major_employers") or [])[:6])
    risk_items = "".join(f"<li>{r}</li>" for r in (profile.get("risks") or [])[:5])
    sweet_items = "".join(f"<li>{s}</li>" for s in (profile.get("sweet_spots") or [])[:5])

    prepared = payload.get("prepared_on") or date.today().isoformat()
    parcel_id = payload.get("parcel_id") or "—"
    sources = " · ".join(str(s) for s in (payload.get("data_sources") or []))
    disclaimer = payload.get("disclaimer") or ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Neighborhood Guide — {address}</title>
<style>
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 13.5px; line-height: 1.55; color: #0b1f3a;
    max-width: 880px; margin: 28px auto; padding: 0 28px 40px; background: #fff;
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
  .exec {{ margin: 8px 0 4px; color: #1e293b; }}
  .note {{
    font-size: 12px; color: #7a5a00; background: #fff8e8; border-left: 4px solid #c89800;
    padding: 8px 12px; margin: 10px 0;
  }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 12.5px; }}
  th {{ background: #0b2545; color: #fff; text-align: left; padding: 7px 9px; font-size: 11px; }}
  td {{ padding: 6px 9px; border-bottom: 1px solid #e5e5e5; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #f7f9fc; }}
  .kv td:first-child {{ color: #555; width: 40%; }}
  .num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  ul {{ margin: 6px 0; padding-left: 18px; }}
  li {{ margin: 4px 0; }}
  .spark {{ margin: 6px 0 2px; }}
  .footnote {{ font-size: 10.5px; color: #64748b; margin-top: 18px; border-top: 1px solid #dde3ee; padding-top: 10px; }}
  @media (max-width: 760px) {{
    .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .two {{ grid-template-columns: 1fr; }}
  }}
</style></head><body>
<div class="hd">
  <h1>Neighborhood Guide</h1>
  <div class="addr">{address}</div>
  <div class="meta">
    <span class="pill">gold neighborhood</span>
    {payload.get('area_label') or ''} · Prepared {prepared} · Parcel {parcel_id}
  </div>
</div>

<p class="note">{disclaimer}</p>

<div class="metrics">
  <div class="metric">
    <span class="lbl">Subject assessed</span>
    <span class="val">{_fmt_money(assessor.get('assessed_value'))}</span>
    <span class="sub">{_fmt_num(assessor.get('lot_sqft'), ' sf')} lot</span>
  </div>
  <div class="metric">
    <span class="lbl">ZIP ZHVI</span>
    <span class="val">{_fmt_money(mkt.get('zhvi_latest'))}</span>
    <span class="sub">ZIP {mkt.get('primary_zip') or '—'} · {mkt.get('zhvi_as_of') or '—'}</span>
  </div>
  <div class="metric">
    <span class="lbl">Street median assessed</span>
    <span class="val">{_fmt_money(street.get('median_assessed'))}</span>
    <span class="sub">{street.get('neighbor_count') or 0} neighbors · vs street {_fmt_pct(street.get('subject_vs_street_median_pct'))}</span>
  </div>
  <div class="metric">
    <span class="lbl">12-mo ZIP move</span>
    <span class="val">{_fmt_pct(mkt.get('change_12m_pct'))}</span>
    <span class="sub">Assessed vs ZHVI {_fmt_pct(mkt.get('assessed_vs_zhvi_pct'))}</span>
  </div>
</div>
{f'<div class="spark">{spark}</div>' if spark else ''}

<h2>1 · Area narrative</h2>
<p class="exec">{payload.get('summary') or ''}</p>
<ul>{highlight_items}</ul>

<div class="two">
  <div>
    <h2>2 · Your parcel</h2>
    <table class="kv">
      <tr><td>Zoning stack</td><td>{payload.get('zoning_stack') or '—'}</td></tr>
      <tr><td>Finished area</td><td class="num">{_fmt_num(assessor.get('finished_sqft'), ' sf')}</td></tr>
      <tr><td>Year built</td><td>{assessor.get('year_built') or '—'}</td></tr>
      <tr><td>Assessed $/sf</td><td class="num">{_fmt_money(assessor.get('assessed_psf'))}</td></tr>
      <tr><td>Coordinates</td><td class="num">{payload.get('lat') or '—'}, {payload.get('lng') or '—'}</td></tr>
    </table>
  </div>
  <div>
    <h2>3 · Town character</h2>
    <table class="kv">
      <tr><td>Housing character</td><td>{profile.get('housing_character') or '—'}</td></tr>
      <tr><td>Political lean (profile)</td><td>{profile.get('political_lean') or '—'}</td></tr>
      <tr><td>NIMBY index (profile)</td><td>{profile.get('nimby_index') if profile.get('nimby_index') is not None else '—'}</td></tr>
      <tr><td>Profile source</td><td>{profile.get('source') or '—'}</td></tr>
    </table>
  </div>
</div>

<h2>4 · Same-street assessor context</h2>
<table>
  <tr><th>Address</th><th>Assessed</th><th>Year</th><th>Zone</th></tr>
  {neighbor_rows}
</table>

<div class="two">
  <div>
    <h2>5 · Transit now</h2>
    <p class="note">{payload.get('walk_score_note') or ''}</p>
    <ul>{transit_items}</ul>
  </div>
  <div>
    <h2>6 · School calendar (not ratings)</h2>
    <p class="note">{payload.get('schools_note') or ''}</p>
    <ul>{cal_items}</ul>
  </div>
</div>

<h2>7 · Infrastructure watch</h2>
<ul>{infra_items}</ul>

<div class="two">
  <div>
    <h2>8 · Sweet spots</h2>
    <ul>{sweet_items or '<li>None listed in town-profile Gold.</li>'}</ul>
  </div>
  <div>
    <h2>9 · Area risks / employers</h2>
    <p><strong>Risks</strong></p>
    <ul>{risk_items or '<li>None listed.</li>'}</ul>
    <p><strong>Major employers</strong></p>
    <ul>{employer_items or '<li>None listed.</li>'}</ul>
  </div>
</div>

<p class="footnote">Sources: {sources}. {disclaimer}</p>
</body></html>"""
