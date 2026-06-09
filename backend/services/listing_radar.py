"""Listing Radar — town-wide ranked listing-opportunity scan for RE agents (v0)."""

from __future__ import annotations

import base64
import csv
import io
import json
from datetime import date
from typing import Any

import pandas as pd

from backend.services.deal_radar import (
    _existing_gfa,
    _fmt_int,
    _fmt_money,
    _fmt_pct,
    _indicative_far,
    _is_excluded,
    _open_permit_parcel_ids,
    _parcel_lot_map,
    _property_frame,
    _tenure_years,
)
from backend.services.deal_radar_config import base_zone_far_map
from backend.services.listing_radar_config import (
    criteria_snapshot,
    get_town_display_name,
    merge_criteria_overrides,
)

_SIGNAL_LABELS = {
    "tenure_sweet_spot": "Owner tenure in listing window",
    "listing_story": "Moderate utilization / expansion story",
    "no_active_permit": "No active building permit",
}


def _in_range(
    value: float | None,
    minimum: Any,
    maximum: Any,
) -> bool:
    if value is None:
        return minimum is None and maximum is None
    if minimum is not None:
        try:
            if value < float(minimum):
                return False
        except (TypeError, ValueError):
            pass
    if maximum is not None:
        try:
            if value > float(maximum):
                return False
        except (TypeError, ValueError):
            pass
    return True


def _tenure_sweet_spot_score(tenure: float, cfg: dict[str, Any]) -> float:
    lo = float(cfg.get("min_owner_tenure_years") or 7)
    hi = float(cfg.get("max_owner_tenure_years") or 35)
    if tenure < lo or tenure > hi:
        return 0.0
    mid = (lo + hi) / 2.0
    half_span = max((hi - lo) / 2.0, 1.0)
    distance = abs(tenure - mid) / half_span
    return max(0.0, 1.0 - distance) * 100.0


def _utilization_story_score(utilization: float | None, cfg: dict[str, Any]) -> float:
    if utilization is None:
        return 50.0
    lo = float(cfg.get("min_utilization_pct") or 25) / 100.0
    hi = float(cfg.get("max_utilization_pct") or 75) / 100.0
    if utilization < lo or utilization > hi:
        return 0.0
    mid = (lo + hi) / 2.0
    half_span = max((hi - lo) / 2.0, 0.05)
    distance = abs(utilization - mid) / half_span
    return max(0.0, 1.0 - distance) * 100.0


def _score_candidate(
    *,
    tenure: float,
    utilization: float | None,
    lot_sqft: float,
    assessed: float | None,
    has_open_permit: bool,
    cfg: dict[str, Any],
) -> float:
    weights = cfg.get("scoring") or {}
    w_tenure = float(weights.get("tenure_sweet_spot_weight") or 0.30)
    w_util = float(weights.get("utilization_story_weight") or 0.30)
    w_permit = float(weights.get("no_permit_weight") or 0.20)
    w_lot = float(weights.get("lot_weight") or 0.10)
    w_value = float(weights.get("value_weight") or 0.10)

    tenure_component = _tenure_sweet_spot_score(tenure, cfg)
    util_component = _utilization_story_score(utilization, cfg)
    permit_component = 0.0 if has_open_permit else 100.0
    lot_component = min(lot_sqft / 8_000.0, 1.0) * 100.0

    value_component = 50.0
    min_val = cfg.get("min_assessed_value")
    max_val = cfg.get("max_assessed_value")
    if assessed is not None and min_val is not None and max_val is not None:
        try:
            lo, hi = float(min_val), float(max_val)
            if hi > lo and lo <= assessed <= hi:
                value_component = 100.0
            elif hi > lo:
                value_component = 40.0
        except (TypeError, ValueError):
            pass

    return round(
        w_tenure * tenure_component
        + w_util * util_component
        + w_permit * permit_component
        + w_lot * lot_component
        + w_value * value_component,
        1,
    )


def _passes_filters(
    *,
    tenure: float | None,
    utilization: float | None,
    existing: float | None,
    lot_sqft: float | None,
    assessed: float | None,
    has_open_permit: bool,
    cfg: dict[str, Any],
) -> bool:
    min_tenure = float(cfg.get("min_owner_tenure_years") or 7)
    max_tenure = float(cfg.get("max_owner_tenure_years") or 35)
    if tenure is None or tenure < min_tenure or tenure > max_tenure:
        return False

    require_no_permit = cfg.get("require_no_open_permit", True)
    if require_no_permit and has_open_permit:
        return False

    min_gfa = float(cfg.get("min_existing_gfa_sqft") or 800)
    if existing is None or existing < min_gfa:
        return False

    util_pct = utilization * 100.0 if utilization is not None else None
    min_util = cfg.get("min_utilization_pct")
    max_util = cfg.get("max_utilization_pct")
    if min_util is not None and util_pct is not None and util_pct < float(min_util):
        return False
    if max_util is not None and util_pct is not None and util_pct > float(max_util):
        return False

    if not _in_range(existing, cfg.get("min_existing_gfa_sqft"), cfg.get("max_existing_gfa_sqft")):
        return False
    if not _in_range(assessed, cfg.get("min_assessed_value"), cfg.get("max_assessed_value")):
        return False
    if not _in_range(lot_sqft, cfg.get("min_lot_sqft"), cfg.get("max_lot_sqft")):
        return False
    return True


def _sort_candidates(candidates: list[dict[str, Any]], sort_by: str) -> None:
    key_map = {
        "score": lambda c: (-float(c.get("score") or 0), -float(c.get("tenure_years") or 0)),
        "tenure": lambda c: (-float(c.get("tenure_years") or 0), -float(c.get("score") or 0)),
        "assessed_value": lambda c: (-float(c.get("assessed_value") or 0), -float(c.get("score") or 0)),
        "utilization": lambda c: (
            float(c.get("utilization_pct") or 0),
            -float(c.get("score") or 0),
        ),
    }
    candidates.sort(key=key_map.get(sort_by, key_map["score"]))


def scan_town_listings(
    town_slug: str,
    effective_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    cfg = effective_cfg or merge_criteria_overrides(town_slug, {})
    far_map = base_zone_far_map(town_slug)
    lot_map = _parcel_lot_map(town_slug)
    open_permits = _open_permit_parcel_ids(town_slug)
    prop_df = _property_frame(town_slug)
    if prop_df.empty:
        return tuple()

    candidates: list[dict[str, Any]] = []
    max_scan = int((cfg.get("output") or {}).get("max_scan") or 20_000)

    for _, row in prop_df.head(max_scan).iterrows():
        if _is_excluded(row, cfg):
            continue
        parcel_id = str(row.get("parcel_id") or "")
        if not parcel_id:
            continue

        metadata = row.get("metadata")
        if isinstance(metadata, str) and metadata.strip():
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        elif not isinstance(metadata, dict):
            metadata = {}

        tenure = _tenure_years(metadata.get("last_sale_date"))
        if tenure is None:
            continue

        lot_sqft = lot_map.get(parcel_id)
        if lot_sqft is None:
            lot_val = row.get("lot_size_sqft")
            if lot_val is not None and not pd.isna(lot_val):
                try:
                    lot_sqft = float(lot_val)
                except (TypeError, ValueError):
                    lot_sqft = None
        if not lot_sqft or lot_sqft <= 0:
            continue

        zone_code = str(row.get("zone_code") or "").strip().upper() or None
        far = _indicative_far(zone_code, cfg, far_map)
        max_gfa = lot_sqft * far
        existing = _existing_gfa(metadata)
        utilization = (existing / max_gfa) if (existing is not None and max_gfa > 0) else None
        expansion_room = (max_gfa - existing) if (existing is not None and max_gfa > 0) else None

        assessed = (
            float(row.get("assessed_value"))
            if row.get("assessed_value") is not None and not pd.isna(row.get("assessed_value"))
            else None
        )
        has_open = parcel_id in open_permits
        if not _passes_filters(
            tenure=tenure,
            utilization=utilization,
            existing=existing,
            lot_sqft=lot_sqft,
            assessed=assessed,
            has_open_permit=has_open,
            cfg=cfg,
        ):
            continue

        score = _score_candidate(
            tenure=tenure,
            utilization=utilization,
            lot_sqft=lot_sqft,
            assessed=assessed,
            has_open_permit=has_open,
            cfg=cfg,
        )
        signals = ["tenure_sweet_spot", "listing_story"]
        if not has_open:
            signals.append("no_active_permit")

        candidates.append({
            "parcel_id": parcel_id,
            "address": str(row.get("address") or "").strip(),
            "owner_name": str(row.get("owner_name") or "").strip() or None,
            "zone_code": zone_code,
            "tenure_years": round(tenure, 1),
            "last_sale_date": metadata.get("last_sale_date"),
            "existing_gfa_sqft": int(round(existing)) if existing is not None else None,
            "max_gfa_sqft": int(round(max_gfa)),
            "indicative_far": round(far, 2),
            "utilization_pct": round(utilization * 100.0, 1) if utilization is not None else None,
            "expansion_room_sqft": int(round(expansion_room)) if expansion_room is not None else None,
            "lot_sqft": int(round(lot_sqft)),
            "assessed_value": assessed,
            "open_permit_count": 1 if has_open else 0,
            "score": score,
            "signals": signals,
        })

    _sort_candidates(candidates, str(cfg.get("sort_by") or "score"))
    return tuple(candidates)


def _criteria_summary_text(criteria: dict[str, Any], total: int, scanned: int) -> str:
    parts = [f"{total:,} parcels match listing filters (scanned {scanned:,} assessor records)."]
    lo = criteria.get("min_owner_tenure_years")
    hi = criteria.get("max_owner_tenure_years")
    if lo is not None or hi is not None:
        parts.append(f"Tenure {lo or '—'}–{hi or '—'} yr.")
    util_lo = criteria.get("min_utilization_pct")
    util_hi = criteria.get("max_utilization_pct")
    if util_lo is not None or util_hi is not None:
        parts.append(f"Utilization {util_lo or '—'}–{util_hi or '—'}%.")
    gfa = criteria.get("min_existing_gfa_sqft")
    if gfa is not None:
        parts.append(f"Min GFA {_fmt_int(gfa)} sf.")
    if criteria.get("preset"):
        parts.append(f"Preset: {criteria['preset']}.")
    return " ".join(parts)


def _raw_town_state(town_slug: str) -> str | None:
    from backend.services.listing_radar_config import _raw_town_config

    cfg = _raw_town_config(town_slug)
    return cfg.get("state")


def generate_listing_radar(
    town_slug: str,
    *,
    highlight_parcel_id: str | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = merge_criteria_overrides(town_slug, criteria_overrides)
    criteria = cfg.get("applied_criteria") or criteria_snapshot(cfg)
    top_n = int(cfg.get("top_n") or 50)
    all_candidates = list(scan_town_listings(town_slug, cfg))
    ranked = all_candidates[:top_n]

    for i, row in enumerate(ranked, start=1):
        row["rank"] = i

    highlight_rank = None
    highlight_row = None
    if highlight_parcel_id:
        for row in all_candidates:
            if row["parcel_id"] == highlight_parcel_id:
                highlight_row = row
                highlight_rank = all_candidates.index(row) + 1
                break

    town_name = get_town_display_name(town_slug)
    state = str(_raw_town_state(town_slug) or "MA")
    scanned = len(_property_frame(town_slug))

    summary_bits = [_criteria_summary_text(criteria, len(all_candidates), scanned)]
    if highlight_row:
        summary_bits.append(
            f"Your parcel ranks #{highlight_rank:,} town-wide (score {highlight_row['score']}).",
        )
    elif highlight_parcel_id:
        summary_bits.append("Your parcel does not currently match Listing Radar filters.")

    return {
        "report_type": "listing-radar",
        "town_slug": town_slug,
        "town_name": town_name,
        "state": state,
        "prepared_on": date.today().isoformat(),
        "criteria": criteria,
        "criteria_defaults": criteria_snapshot(merge_criteria_overrides(town_slug, {})),
        "executive_summary": " ".join(summary_bits),
        "total_matches": len(all_candidates),
        "parcels_scanned": scanned,
        "top_n": top_n,
        "listings": ranked,
        "highlight_parcel_id": highlight_parcel_id,
        "highlight_rank": highlight_rank,
        "highlight_listing": highlight_row,
        "pilot_gaps": list(cfg.get("pilot_gaps") or []),
        "data_sources": [
            "property.parquet (assessor tenure + GFA)",
            "parcel.parquet (lot area)",
            "permits.parquet (open permit filter)",
            f"configs/{town_slug}/config.yaml (listing_radar scoring rules)",
        ],
    }


def listing_radar_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    criteria = payload.get("criteria") or {}
    if criteria:
        buf.write(f"# criteria={json.dumps(criteria, sort_keys=True)}\n")
    fields = [
        "rank",
        "parcel_id",
        "address",
        "owner_name",
        "zone_code",
        "tenure_years",
        "last_sale_date",
        "existing_gfa_sqft",
        "max_gfa_sqft",
        "utilization_pct",
        "expansion_room_sqft",
        "lot_sqft",
        "assessed_value",
        "score",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in payload.get("listings") or []:
        writer.writerow(row)
    return buf.getvalue()


def _criteria_html_lines(criteria: dict[str, Any]) -> str:
    lines: list[str] = []
    preset = criteria.get("preset")
    if preset:
        lines.append(f"<li>Preset: <strong>{preset}</strong></li>")
    lines.append(
        f"<li>Owner tenure: <strong>{criteria.get('min_owner_tenure_years', 7)}"
        f" – {criteria.get('max_owner_tenure_years', 35)}</strong> years</li>"
    )
    util_lo = criteria.get("min_utilization_pct")
    util_hi = criteria.get("max_utilization_pct")
    if util_lo is not None or util_hi is not None:
        lines.append(
            f"<li>Utilization: <strong>{util_lo or '—'} – {util_hi or '—'}%</strong> "
            f"of indicative max GFA</li>"
        )
    gfa_min = criteria.get("min_existing_gfa_sqft")
    if gfa_min is not None:
        lines.append(f"<li>Min existing GFA ≥ <strong>{_fmt_int(gfa_min)}</strong> sf</li>")
    assessed_min = criteria.get("min_assessed_value")
    assessed_max = criteria.get("max_assessed_value")
    if assessed_min is not None or assessed_max is not None:
        lines.append(
            f"<li>Assessed value: <strong>{_fmt_money(assessed_min)} – {_fmt_money(assessed_max)}</strong></li>"
        )
    zones = criteria.get("include_zone_codes") or []
    if zones:
        lines.append(f"<li>Zones included: <strong>{', '.join(zones)}</strong></li>")
    permit = criteria.get("require_no_open_permit", True)
    lines.append(
        f"<li>Open permits: <strong>{'Excluded' if permit else 'Allowed'}</strong></li>"
    )
    lines.append(f"<li>Sort by: <strong>{criteria.get('sort_by', 'score')}</strong></li>")
    lines.append(f"<li>Top N: <strong>{criteria.get('top_n', 50)}</strong></li>")
    return "".join(lines)


def render_listing_radar_html(payload: dict[str, Any]) -> str:
    town = payload.get("town_name") or payload.get("town_slug") or "Town"
    state = payload.get("state") or "MA"
    listings = payload.get("listings") or []
    highlight_id = payload.get("highlight_parcel_id")
    criteria = payload.get("criteria") or {}
    gaps = payload.get("pilot_gaps") or []
    prepared = payload.get("prepared_on") or date.today().isoformat()
    csv_text = listing_radar_to_csv(payload)
    csv_b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
    csv_href = f"data:text/csv;base64,{csv_b64}"

    listing_rows = ""
    for row in listings:
        is_hi = row.get("parcel_id") == highlight_id
        row_cls = ' class="highlight"' if is_hi else ""
        hi_tag = ' <span class="tag">Your parcel</span>' if is_hi else ""
        listing_rows += f"""<tr{row_cls}>
          <td class="num">{row.get('rank', '—')}</td>
          <td>{row.get('address', '—')}{hi_tag}</td>
          <td class="small">{row.get('parcel_id', '—')}</td>
          <td>{row.get('owner_name') or '—'}</td>
          <td>{row.get('zone_code') or '—'}</td>
          <td class="num">{row.get('tenure_years', '—')}</td>
          <td class="num">{_fmt_int(row.get('existing_gfa_sqft'))}</td>
          <td class="num">{_fmt_pct(row.get('utilization_pct'))}</td>
          <td class="num">{_fmt_int(row.get('expansion_room_sqft'))}</td>
          <td class="num">{_fmt_money(row.get('assessed_value'))}</td>
          <td class="num"><strong>{row.get('score', '—')}</strong></td>
        </tr>"""

    if not listing_rows:
        listing_rows = (
            "<tr><td colspan='11'>No parcels matched the current filters. "
            "Adjust listing_radar rules in town config or refresh Gold data.</td></tr>"
        )

    highlight_block = ""
    hi = payload.get("highlight_listing")
    if hi:
        highlight_block = f"""
<p class="note"><strong>Selected parcel:</strong> {hi.get('address', '—')} ranks
<strong>#{payload.get('highlight_rank')}</strong> with score <strong>{hi.get('score')}</strong>
({hi.get('tenure_years')} yr tenure · {_fmt_pct(hi.get('utilization_pct'))} utilization).</p>"""
    elif highlight_id:
        highlight_block = (
            '<p class="note">Selected parcel is not in the current Listing Radar match set '
            "(may fail tenure, utilization, GFA, or open-permit filters).</p>"
        )

    gap_items = "".join(f"<li>{g}</li>" for g in gaps)
    criteria_html = _criteria_html_lines(criteria)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Listing Radar — {town}, {state}</title>
<style>
  body{{font-family:Georgia,'Times New Roman',serif;font-size:13px;line-height:1.55;color:#1a1a1a;max-width:920px;margin:36px auto;padding:0 28px;background:#fff}}
  h1{{font-size:22px;margin:0 0 4px;color:#0b2545;letter-spacing:.5px}}
  h2{{font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#0b2545;border-bottom:2px solid #0b2545;padding:18px 0 4px;margin:18px 0 10px}}
  .hd{{border-bottom:1px solid #ccc;padding-bottom:10px;margin-bottom:8px}}
  .meta{{font-size:11px;color:#555;margin-top:6px}}
  .exec{{margin:10px 0 14px;color:#222}}
  table{{width:100%;border-collapse:collapse;margin:6px 0 10px;font-size:12px}}
  th{{background:#0b2545;color:#fff;text-align:left;padding:6px 8px;font-size:11px;letter-spacing:.4px}}
  td{{padding:5px 8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#f7f9fc}}
  tr.highlight td{{background:#fff3cf;font-weight:600}}
  .num{{font-variant-numeric:tabular-nums}}
  .small{{font-size:11px;color:#555}}
  .note{{font-size:12px;color:#555;font-style:italic;margin:8px 0}}
  .tag{{display:inline-block;background:#0b2545;color:#fff;font-size:9px;padding:1px 6px;border-radius:8px;margin-left:4px}}
  .btn{{display:inline-block;margin:8px 0 12px;padding:8px 14px;background:#0b2545;color:#fff;text-decoration:none;border-radius:4px;font-size:12px}}
  ul{{margin:6px 0;padding-left:20px}}
  .footnote{{font-size:10.5px;color:#555;margin-top:16px;border-top:1px solid #ddd;padding-top:10px}}
</style></head><body>
<div class="te-report">

<div class="hd">
  <h1>Listing Radar</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{town}, {state}</div>
  <div class="meta">Prepared on {prepared} · Top {payload.get('top_n', 50)} of {payload.get('total_matches', 0):,} matches · {payload.get('parcels_scanned', 0):,} parcels scanned</div>
</div>

<h2>1 · Executive Summary</h2>
<p class="exec">{payload.get('executive_summary', '')}</p>
{highlight_block}
<a class="btn" href="{csv_href}" download="listing-radar-{payload.get('town_slug', 'town')}.csv">Download CSV (top {payload.get('top_n', 50)})</a>

<h2>2 · Screening Criteria</h2>
<ul>
{criteria_html}
</ul>
<p class="small">Signals scored: {', '.join(_SIGNAL_LABELS.values())}. Indicative FAR from town config — confirm on target parcels.</p>

<h2>3 · Ranked Listing Opportunities</h2>
<table>
<tr><th>#</th><th>Address</th><th>Parcel ID</th><th>Owner</th><th>Zone</th><th>Tenure (yr)</th><th>GFA</th><th>Utilization</th><th>Expansion</th><th>Assessed</th><th>Score</th></tr>
{listing_rows}
</table>

<h2>4 · Not Yet Connected (Pilot)</h2>
<ul>{gap_items}</ul>

<p class="footnote">
  Town-wide screening for listing conversations — not MLS data, CMA, or solicitation advice.
  Owner tenure and assessed value come from assessor Gold layers; verify with owners and primary
  sources before outreach. MLS DOM, price reductions, and absentee-owner signals ship in a later phase.
</p>
</div>
</body></html>"""


def generate_listing_radar_html(
    town_slug: str,
    parcel_id: str | None = None,
    prepared_for: str | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> str:
    del prepared_for
    payload = generate_listing_radar(
        town_slug,
        highlight_parcel_id=parcel_id,
        criteria_overrides=criteria_overrides,
    )
    return render_listing_radar_html(payload)
