"""Deal Radar — town-wide ranked development-opportunity scan (Report 01 / Phase B v0)."""

from __future__ import annotations

import base64
import csv
import io
import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.deal_radar_config import (
    base_zone_far_map,
    criteria_snapshot,
    get_deal_radar_config,
    get_town_display_name,
    merge_criteria_overrides,
)
from backend.services.parcel_permits import _OPEN_STATUSES, _parse_metadata

_SIGNAL_LABELS = {
    "long_tenure": "Long owner tenure",
    "underbuilt": "Underbuilt vs zoning envelope",
    "no_active_permit": "No active building permit",
    "by_right_multifamily": "By-right multi-family zoning",
    "absentee_owner": "Absentee owner",
    "entity_owner": "LLC / Corporate owner",
}


def _fmt_int(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def _parse_metadata_field(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _tenure_years(last_sale_date: str | None, *, today: date | None = None) -> float | None:
    if not last_sale_date:
        return None
    ref = today or date.today()
    try:
        sold = datetime.strptime(str(last_sale_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return max(0.0, (ref - sold).days / 365.25)


def _existing_gfa(metadata: dict[str, Any]) -> float | None:
    for key in ("finished_area_sqft", "finished_area_sqft_l3", "building_footprint_sqft"):
        val = metadata.get(key)
        if val is None:
            continue
        try:
            gfa = float(val)
        except (TypeError, ValueError):
            continue
        if gfa > 0:
            return gfa
    return None


def _indicative_far(zone_code: str | None, cfg: dict[str, Any], far_map: dict[str, float]) -> float:
    code = str(zone_code or "").strip().upper()
    overlay = (cfg.get("overlay_indicative_far") or {}).get(code)
    if overlay is not None:
        try:
            return float(overlay)
        except (TypeError, ValueError):
            pass
    if code in far_map:
        return far_map[code]
    return float(cfg.get("default_indicative_far") or 0.5)


@lru_cache(maxsize=8)
def _property_frame(town_slug: str) -> pd.DataFrame:
    path = get_settings().gold_data_path / town_slug / "property.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


@lru_cache(maxsize=8)
def _parcel_lot_map(town_slug: str) -> dict[str, float]:
    path = get_settings().gold_data_path / town_slug / "parcel.parquet"
    if not path.is_file():
        return {}
    df = pd.read_parquet(path, columns=["parcel_id", "area_sqft"])
    if df.empty:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        pid = str(row.get("parcel_id") or "")
        area = row.get("area_sqft")
        if pid and area is not None and not pd.isna(area):
            try:
                out[pid] = float(area)
            except (TypeError, ValueError):
                continue
    return out


@lru_cache(maxsize=8)
def _open_permit_parcel_ids(town_slug: str) -> frozenset[str]:
    path = get_settings().gold_data_path / town_slug / "permits.parquet"
    if not path.is_file():
        return frozenset()
    df = pd.read_parquet(path)
    if df.empty:
        return frozenset()
    open_ids: set[str] = set()
    for _, row in df.iterrows():
        status = str(row.get("status") or "").upper()
        if status not in _OPEN_STATUSES:
            continue
        md = _parse_metadata(row.get("metadata"))
        pid = str(md.get("parcel_id") or "").strip()
        if pid:
            open_ids.add(pid)
    return frozenset(open_ids)


def _is_excluded(row: pd.Series, cfg: dict[str, Any]) -> bool:
    zone = str(row.get("zone_code") or "").strip().upper()
    exclude_zones = {str(z).upper() for z in (cfg.get("exclude_zone_codes") or [])}
    include_zones = {str(z).upper() for z in (cfg.get("include_zone_codes") or [])}
    if include_zones and zone not in include_zones:
        return True
    if zone and zone in exclude_zones:
        return True
    luc = str(row.get("luc") or "").strip()
    for prefix in cfg.get("exclude_luc_prefixes") or []:
        if luc.startswith(str(prefix)):
            return True
    return False


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


def _score_candidate(
    *,
    tenure: float,
    utilization: float | None,
    expansion_room: float | None,
    lot_sqft: float,
    cfg: dict[str, Any],
) -> float:
    weights = cfg.get("scoring") or {}
    w_tenure = float(weights.get("tenure_weight") or 0.35)
    w_under = float(weights.get("underbuilt_weight") or 0.45)
    w_lot = float(weights.get("lot_weight") or 0.20)

    tenure_component = min(tenure / 30.0, 1.0) * 100.0
    if utilization is not None:
        under_component = max(0.0, 1.0 - utilization) * 100.0
    elif expansion_room is not None and lot_sqft > 0:
        under_component = min(expansion_room / lot_sqft, 1.0) * 100.0
    else:
        under_component = 50.0
    lot_component = min(lot_sqft / 10_000.0, 1.0) * 100.0
    return round(
        w_tenure * tenure_component + w_under * under_component + w_lot * lot_component,
        1,
    )


def _passes_filters(
    *,
    tenure: float | None,
    utilization: float | None,
    expansion_room: float | None,
    existing: float | None,
    max_gfa: float | None,
    lot_sqft: float | None,
    assessed: float | None,
    has_open_permit: bool,
    zone_code: str | None,
    cfg: dict[str, Any],
    **kwargs: Any,
) -> bool:
    min_tenure = float(cfg.get("min_owner_tenure_years") or 15)
    if tenure is None or tenure < min_tenure:
        return False

    require_no_permit = cfg.get("require_no_open_permit", True)
    if require_no_permit and has_open_permit:
        return False

    ratio_max = float(cfg.get("underbuilt_ratio_max") or 0.60)
    min_room = float(cfg.get("min_expansion_room_sqft") or 800)
    underbuilt_ok = False
    if utilization is not None and utilization <= ratio_max:
        underbuilt_ok = True
    if expansion_room is not None and expansion_room >= min_room:
        underbuilt_ok = True
    if not underbuilt_ok:
        return False

    util_pct = utilization * 100.0 if utilization is not None else None
    max_util = cfg.get("max_utilization_pct")
    if max_util is not None and util_pct is not None and util_pct > float(max_util):
        return False
    min_util = cfg.get("min_utilization_pct")
    if min_util is not None and util_pct is not None and util_pct < float(min_util):
        return False

    if not _in_range(existing, cfg.get("min_existing_gfa_sqft"), cfg.get("max_existing_gfa_sqft")):
        return False
    if not _in_range(max_gfa, cfg.get("min_max_gfa_sqft"), cfg.get("max_max_gfa_sqft")):
        return False
    if not _in_range(assessed, cfg.get("min_assessed_value"), cfg.get("max_assessed_value")):
        return False
    if not _in_range(lot_sqft, cfg.get("min_lot_sqft"), cfg.get("max_lot_sqft")):
        return False

    require_multifamily = cfg.get("require_by_right_multifamily", False)
    if require_multifamily:
        multifamily_zones = {str(z).upper() for z in (cfg.get("multifamily_zone_codes") or [])}
        if not zone_code or zone_code.upper() not in multifamily_zones:
            return False

    if cfg.get("require_absentee_owner") and not kwargs.get("is_absentee"):
        return False
        
    if cfg.get("require_entity_owner") and not kwargs.get("is_entity"):
        return False

    return True


def _sort_candidates(candidates: list[dict[str, Any]], sort_by: str) -> None:
    key_map = {
        "score": lambda c: (-float(c.get("score") or 0), -float(c.get("expansion_room_sqft") or 0)),
        "expansion": lambda c: (-float(c.get("expansion_room_sqft") or 0), -float(c.get("score") or 0)),
        "assessed_value": lambda c: (-float(c.get("assessed_value") or 0), -float(c.get("score") or 0)),
        "tenure": lambda c: (-float(c.get("tenure_years") or 0), -float(c.get("score") or 0)),
    }
    candidates.sort(key=key_map.get(sort_by, key_map["score"]))


def scan_town_deals(town_slug: str, effective_cfg: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
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

        metadata = _parse_metadata_field(row.get("metadata"))
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
        
        owner_name = str(row.get("owner_name") or "").strip()
        is_entity = False
        if owner_name:
            upper_name = owner_name.upper()
            is_entity = any(kw in upper_name for kw in ["LLC", "INC", "CORP", "TRUST", "TR ", "TRS ", "REALTY", "ASSOCIATES", "L.L.C."])
            
        owner_addr = str(metadata.get("owner_address") or metadata.get("mailing_address") or "").strip().lower()
        site_addr = str(row.get("address") or "").strip().lower()
        
        # Absentee if owner_address exists and isn't a substring of site address (and vice versa)
        # We enforce len > 5 to avoid empty or trivial string matches
        is_absentee = False
        if len(owner_addr) > 5 and len(site_addr) > 5:
            # simple normalized compare: strip spaces and compare first 10 chars
            o_clean = owner_addr.replace(" ", "").replace(",", "")
            s_clean = site_addr.replace(" ", "").replace(",", "")
            is_absentee = o_clean[:10] != s_clean[:10]

        if not _passes_filters(
            tenure=tenure,
            utilization=utilization,
            expansion_room=expansion_room,
            existing=existing,
            max_gfa=max_gfa,
            lot_sqft=lot_sqft,
            assessed=assessed,
            has_open_permit=has_open,
            zone_code=zone_code,
            cfg=cfg,
            is_absentee=is_absentee,
            is_entity=is_entity,
        ):
            continue

        score = _score_candidate(
            tenure=tenure,
            utilization=utilization,
            expansion_room=expansion_room,
            lot_sqft=lot_sqft,
            cfg=cfg,
        )
        
        signals = ["long_tenure", "underbuilt", "no_active_permit"]
        multifamily_zones = {str(z).upper() for z in (cfg.get("multifamily_zone_codes") or [])}
        if zone_code and zone_code.upper() in multifamily_zones:
            signals.append("by_right_multifamily")
        if is_absentee:
            signals.append("absentee_owner")
        if is_entity:
            signals.append("entity_owner")
            
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
            "by_right_multifamily": "by_right_multifamily" in signals,
            "is_absentee": is_absentee,
            "is_entity": is_entity,
        })

    _sort_candidates(candidates, str(cfg.get("sort_by") or "score"))
    return tuple(candidates)


def _criteria_summary_text(criteria: dict[str, Any], total: int, scanned: int) -> str:
    parts = [f"{total:,} parcels match your filters (scanned {scanned:,} assessor records)."]
    tenure = criteria.get("min_owner_tenure_years")
    if tenure is not None:
        parts.append(f"Tenure ≥ {tenure} yr.")
    util = criteria.get("max_utilization_pct")
    if util is not None:
        parts.append(f"Utilization ≤ {util}%.")
    room = criteria.get("min_expansion_room_sqft")
    if room is not None:
        parts.append(f"Expansion ≥ {_fmt_int(room)} sf.")
    zones = criteria.get("include_zone_codes") or []
    if zones:
        parts.append(f"Zones: {', '.join(zones)}.")
    assessed_min = criteria.get("min_assessed_value")
    assessed_max = criteria.get("max_assessed_value")
    if assessed_min is not None or assessed_max is not None:
        parts.append(
            f"Assessed {_fmt_money(assessed_min) if assessed_min else '—'}"
            f" – {_fmt_money(assessed_max) if assessed_max else '—'}."
        )
    if criteria.get("preset"):
        parts.append(f"Preset: {criteria['preset']}.")
    return " ".join(parts)


def generate_deal_radar(
    town_slug: str,
    *,
    highlight_parcel_id: str | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = merge_criteria_overrides(town_slug, criteria_overrides)
    criteria = cfg.get("applied_criteria") or criteria_snapshot(cfg)
    top_n = int(cfg.get("top_n") or 50)
    all_candidates = list(scan_town_deals(town_slug, cfg))
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
    state = str((_raw_town_state(town_slug)) or "MA")
    scanned = len(_property_frame(town_slug))

    summary_bits = [_criteria_summary_text(criteria, len(all_candidates), scanned)]
    if highlight_row:
        summary_bits.append(
            f"Your parcel ranks #{highlight_rank:,} town-wide (score {highlight_row['score']}).",
        )
    elif highlight_parcel_id:
        summary_bits.append("Your parcel does not currently match Deal Radar filters.")

    return {
        "report_type": "deal-radar",
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
        "deals": ranked,
        "highlight_parcel_id": highlight_parcel_id,
        "highlight_rank": highlight_rank,
        "highlight_deal": highlight_row,
        "pilot_gaps": list(cfg.get("pilot_gaps") or []),
        "data_sources": [
            "property.parquet (assessor tenure + GFA)",
            "parcel.parquet (lot area)",
            "permits.parquet (open permit filter)",
            f"configs/{town_slug}/config.yaml (deal_radar scoring rules)",
        ],
    }


def _raw_town_state(town_slug: str) -> str | None:
    from backend.services.deal_radar_config import _raw_town_config

    cfg = _raw_town_config(town_slug)
    return cfg.get("state")


def deal_radar_to_csv(payload: dict[str, Any]) -> str:
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
    for row in payload.get("deals") or []:
        writer.writerow(row)
    return buf.getvalue()


def _criteria_html_lines(criteria: dict[str, Any]) -> str:
    lines: list[str] = []
    preset = criteria.get("preset")
    if preset:
        lines.append(f"<li>Preset: <strong>{preset}</strong></li>")
    lines.append(
        f"<li>Owner tenure ≥ <strong>{criteria.get('min_owner_tenure_years', 15)}</strong> years</li>"
    )
    util = criteria.get("max_utilization_pct")
    if util is not None:
        lines.append(f"<li>Max utilization ≤ <strong>{util}%</strong> of indicative max GFA</li>")
    room = criteria.get("min_expansion_room_sqft")
    if room is not None:
        lines.append(f"<li>Min expansion room ≥ <strong>{_fmt_int(room)}</strong> sf</li>")
    gfa_min = criteria.get("min_existing_gfa_sqft")
    gfa_max = criteria.get("max_existing_gfa_sqft")
    if gfa_min is not None or gfa_max is not None:
        lines.append(
            f"<li>Existing GFA: <strong>{_fmt_int(gfa_min) if gfa_min else '—'}"
            f" – {_fmt_int(gfa_max) if gfa_max else '—'}</strong> sf</li>"
        )
    max_gfa_min = criteria.get("min_max_gfa_sqft")
    max_gfa_max = criteria.get("max_max_gfa_sqft")
    if max_gfa_min is not None or max_gfa_max is not None:
        lines.append(
            f"<li>Max buildable GFA: <strong>{_fmt_int(max_gfa_min) if max_gfa_min else '—'}"
            f" – {_fmt_int(max_gfa_max) if max_gfa_max else '—'}</strong> sf</li>"
        )
    assessed_min = criteria.get("min_assessed_value")
    assessed_max = criteria.get("max_assessed_value")
    if assessed_min is not None or assessed_max is not None:
        lines.append(
            f"<li>Assessed value: <strong>{_fmt_money(assessed_min)} – {_fmt_money(assessed_max)}</strong></li>"
        )
    lot_min = criteria.get("min_lot_sqft")
    lot_max = criteria.get("max_lot_sqft")
    if lot_min is not None or lot_max is not None:
        lines.append(
            f"<li>Lot size: <strong>{_fmt_int(lot_min) if lot_min else '—'}"
            f" – {_fmt_int(lot_max) if lot_max else '—'}</strong> sf</li>"
        )
    zones = criteria.get("include_zone_codes") or []
    if zones:
        lines.append(f"<li>Zones included: <strong>{', '.join(zones)}</strong></li>")
    ex_zones = criteria.get("exclude_zone_codes") or []
    if ex_zones:
        lines.append(f"<li>Zones excluded: <strong>{', '.join(ex_zones)}</strong></li>")
    permit = criteria.get("require_no_open_permit", True)
    lines.append(
        f"<li>Open permits: <strong>{'Excluded' if permit else 'Allowed'}</strong></li>"
    )
    multifamily = criteria.get("require_by_right_multifamily", False)
    lines.append(
        f"<li>By-right multi-family: <strong>{'Required' if multifamily else 'Any'}</strong></li>"
    )
    absentee = criteria.get("require_absentee_owner", False)
    if absentee:
        lines.append(f"<li>Owner occupancy: <strong>Absentee only</strong></li>")
    entity = criteria.get("require_entity_owner", False)
    if entity:
        lines.append(f"<li>Owner entity: <strong>LLC/Corporate only</strong></li>")
        
    lines.append(f"<li>Sort by: <strong>{criteria.get('sort_by', 'score')}</strong></li>")
    lines.append(f"<li>Top N: <strong>{criteria.get('top_n', 50)}</strong></li>")
    return "".join(lines)


def render_deal_radar_html(payload: dict[str, Any]) -> str:
    town = payload.get("town_name") or payload.get("town_slug") or "Town"
    state = payload.get("state") or "MA"
    deals = payload.get("deal_radar") or payload.get("deals") or []
    highlight_id = payload.get("highlight_parcel_id")
    criteria = payload.get("criteria") or {}
    gaps = payload.get("pilot_gaps") or []
    prepared = payload.get("prepared_on") or date.today().isoformat()
    csv_text = deal_radar_to_csv(payload)
    csv_b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
    csv_href = f"data:text/csv;base64,{csv_b64}"

    deal_rows = ""
    for d in deals:
        is_hi = d.get("parcel_id") == highlight_id
        row_cls = ' class="highlight"' if is_hi else ""
        hi_tag = ' <span class="tag">Your parcel</span>' if is_hi else ""
        mf_tag = ' <span class="tag mf">By-Right MF</span>' if d.get('by_right_multifamily') else ""
        absentee_tag = ' <span class="tag absentee">Absentee</span>' if d.get('is_absentee') else ""
        entity_tag = ' <span class="tag entity">LLC/Corp</span>' if d.get('is_entity') else ""
        deal_rows += f"""<tr{row_cls}>
          <td class="num">{d.get('rank', '—')}</td>
          <td>{d.get('address', '—')}{hi_tag}{mf_tag}{absentee_tag}</td>
          <td class="small">{d.get('parcel_id', '—')}</td>
          <td>{d.get('owner_name') or '—'}{entity_tag}</td>
          <td>{d.get('zone_code') or '—'}</td>
          <td class="num">{d.get('tenure_years', '—')}</td>
          <td class="num">{_fmt_int(d.get('existing_gfa_sqft'))}</td>
          <td class="num">{_fmt_int(d.get('max_gfa_sqft'))}</td>
          <td class="num">{_fmt_pct(d.get('utilization_pct'))}</td>
          <td class="num">{_fmt_int(d.get('expansion_room_sqft'))}</td>
          <td class="num">{_fmt_money(d.get('assessed_value'))}</td>
          <td class="num"><strong>{d.get('score', '—')}</strong></td>
        </tr>"""

    if not deal_rows:
        deal_rows = (
            "<tr><td colspan='12'>No parcels matched the current filters. "
            "Adjust deal_radar rules in town config or refresh Gold data.</td></tr>"
        )

    highlight_block = ""
    hi = payload.get("highlight_deal")
    if hi:
        highlight_block = f"""
<p class="note"><strong>Selected parcel:</strong> {hi.get('address', '—')} ranks
<strong>#{payload.get('highlight_rank')}</strong> with score <strong>{hi.get('score')}</strong>
({hi.get('tenure_years')} yr tenure · {_fmt_int(hi.get('expansion_room_sqft'))} sf expansion room).</p>"""
    elif highlight_id:
        highlight_block = (
            '<p class="note">Selected parcel is not in the current Deal Radar match set '
            "(may fail tenure, underbuilt, or open-permit filters).</p>"
        )

    gap_items = "".join(f"<li>{g}</li>" for g in gaps)
    criteria_html = _criteria_html_lines(criteria)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Deal Radar — {town}, {state}</title>
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
  .tag.mf{{background:#1a7a1a}}
  .tag.absentee{{background:#a06b00}}
  .tag.entity{{background:#555}}
  .btn{{display:inline-block;margin:8px 0 12px;padding:8px 14px;background:#0b2545;color:#fff;text-decoration:none;border-radius:4px;font-size:12px}}
  ul{{margin:6px 0;padding-left:20px}}
  .footnote{{font-size:10.5px;color:#555;margin-top:16px;border-top:1px solid #ddd;padding-top:10px}}
  .logo-header {{ position: absolute; top: 20px; right: 28px; height: 32px; opacity: 0.8; }}
</style></head><body>
<div class="te-report">

<div class="hd" style="position: relative;">
  <img src="https://demo.towneye.ai/logo.png" alt="TownEye Logo" class="logo-header" />
  <h1>Deal Radar</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{town}, {state}</div>
  <div class="meta">Prepared on {prepared} · Top {payload.get('top_n', 50)} of {payload.get('total_matches', 0):,} matches · {payload.get('parcels_scanned', 0):,} parcels scanned</div>
</div>

<h2>1 · Executive Summary</h2>
<p class="exec">{payload.get('executive_summary', '')}</p>
{highlight_block}
<a class="btn" href="{csv_href}" download="deal-radar-{payload.get('town_slug', 'town')}.csv">Download CSV (top {payload.get('top_n', 50)})</a>

<h2>2 · Screening Criteria</h2>
<ul>
{criteria_html}
</ul>
<p class="small">Signals scored: {', '.join(_SIGNAL_LABELS.values())}. Indicative FAR from town config — confirm overlays on target parcels.</p>

<h2>3 · Ranked Opportunities</h2>
<table>
<tr><th>#</th><th>Address</th><th>Parcel ID</th><th>Owner</th><th>Zone</th><th>Tenure (yr)</th><th>Existing GFA</th><th>Max GFA</th><th>Utilization</th><th>Expansion</th><th>Assessed</th><th>Score</th></tr>
{deal_rows}
</table>

<h2>4 · Not Yet Connected (Pilot)</h2>
<ul>{gap_items}</ul>

<p class="footnote">
  Town-wide screening model — not investment or solicitation advice. Indicative FAR uses base zone
  rules from town config; overlay districts may allow higher yield — confirm with a Buildability Brief
  on any target parcel. Probate, absentee, and registry distress layers ship in a later phase.
</p>
</div>
</body></html>"""


def generate_deal_radar_html(
    town_slug: str,
    parcel_id: str | None = None,
    prepared_for: str | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> str:
    del prepared_for
    payload = generate_deal_radar(
        town_slug,
        highlight_parcel_id=parcel_id,
        criteria_overrides=criteria_overrides,
    )
    return render_deal_radar_html(payload)
