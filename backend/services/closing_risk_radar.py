"""Closing Risk Radar — town-wide ranked closing-risk scan for attorneys (v0)."""

from __future__ import annotations

import base64
import csv
import io
import json
import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd
from shapely.geometry import Point as ShapelyPoint
from shapely.strtree import STRtree

from backend.config import get_settings
from backend.services.closing_risk_radar_config import (
    criteria_snapshot,
    get_town_display_name,
    merge_criteria_overrides,
)
from backend.services.parcel_permits import _OPEN_STATUSES, _parse_metadata
from core.spatial import OverlayResolver, _shapely_from_row

_SIGNAL_LABELS = {
    "open_permit": "Open building permit",
    "expired_permit": "Expired permit on record",
    "flood_effective": "FEMA flood zone (effective)",
    "flood_preliminary": "FEMA flood zone (preliminary)",
    "flood_sfha": "Special Flood Hazard Area",
    "wetland": "Wetland overlay",
    "historic": "Historic resource / district",
    "21e_site": "MassDEP 21E Contamination Site",
    "ust_site": "Underground Storage Tank (UST)",
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


def _truthy_sfha(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().upper()
    return text in {"1", "TRUE", "T", "YES", "Y"}


def _layer_text(row: pd.Series) -> str:
    parts = [
        str(row.get("source_layer_name") or ""),
        str(row.get("category") or ""),
    ]
    return " ".join(parts).lower()


def _classify_env_row(row: pd.Series) -> set[str]:
    layer = _layer_text(row)
    flags: set[str] = set()
    if "flood-effective" in layer:
        flags.add("flood_effective")
        if _truthy_sfha(row.get("sfha_flag")):
            flags.add("flood_sfha")
    if "flood-preliminary" in layer:
        flags.add("flood_preliminary")
        if _truthy_sfha(row.get("sfha_flag")):
            flags.add("flood_sfha")
    if "wetland" in layer:
        flags.add("wetland")
    return flags


def _normalize_address(address: str | None) -> str:
    if not address:
        return ""
    text = str(address).upper().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" STREET", " ST").replace(" AVENUE", " AVE").replace(" ROAD", " RD")
    return text


def _address_prefix(address: str | None) -> str | None:
    norm = _normalize_address(address)
    match = re.match(r"^\s*(\d+)\s+(\w+)", norm)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


@lru_cache(maxsize=8)
def _property_frame(town_slug: str) -> pd.DataFrame:
    path = get_settings().gold_data_path / town_slug / "property.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


@lru_cache(maxsize=8)
def _parcel_frame(town_slug: str) -> pd.DataFrame:
    path = get_settings().gold_data_path / town_slug / "parcel.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


@lru_cache(maxsize=8)
def _parcel_lot_map(town_slug: str) -> dict[str, float]:
    df = _parcel_frame(town_slug)
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
def _permit_summary_map(town_slug: str) -> dict[str, dict[str, Any]]:
    path = get_settings().gold_data_path / town_slug / "permits.parquet"
    if not path.is_file():
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}

    summaries: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        md = _parse_metadata(row.get("metadata"))
        pid = str(md.get("parcel_id") or "").strip()
        if not pid:
            continue
        status = str(row.get("status") or "").upper()
        entry = summaries.setdefault(
            pid,
            {"open_count": 0, "expired_count": 0, "total_count": 0},
        )
        entry["total_count"] += 1
        if status in _OPEN_STATUSES:
            entry["open_count"] += 1
        if status == "EXPIRED":
            entry["expired_count"] += 1
    return summaries


@lru_cache(maxsize=4)
def _overlay_risk_index(town_slug: str) -> dict[str, dict[str, Any]]:
    """Batch spatial + address scan for env / historic flags keyed by parcel_id."""
    parcel_df = _parcel_frame(town_slug)
    if parcel_df.empty:
        return {}

    prop_df = _property_frame(town_slug)
    address_by_pid: dict[str, str] = {}
    if not prop_df.empty and "parcel_id" in prop_df.columns:
        for _, row in prop_df.iterrows():
            pid = str(row.get("parcel_id") or "")
            addr = str(row.get("address") or "").strip()
            if pid and addr:
                address_by_pid[pid] = addr

    gold = get_settings().gold_data_path / town_slug
    env_path = gold / "environmental-overlay.parquet"
    env_geoms: list[Any] = []
    env_meta: list[set[str]] = []
    if env_path.is_file():
        env_df = pd.read_parquet(env_path)
        for _, row in env_df.iterrows():
            geom = _shapely_from_row(row)
            if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            flags = _classify_env_row(row)
            if not flags:
                continue
            env_geoms.append(geom)
            env_meta.append(flags)
    env_tree = STRtree(env_geoms) if env_geoms else None

    resolver = OverlayResolver(town_slug=town_slug, data_dir=str(get_settings().gold_data_path))

    historic_prefixes: set[str] = set()
    historic_norms: set[str] = set()
    for domain in ("macris", "local_historic"):
        df = resolver._load(domain)
        if df.empty or "address" not in df.columns:
            continue
        for _, row in df.iterrows():
            gtype = str(row.get("geometry_type") or "").lower()
            if gtype not in ("point", "multipoint"):
                continue
            norm = _normalize_address(row.get("address"))
            if norm:
                historic_norms.add(norm)
            prefix = _address_prefix(row.get("address"))
            if prefix:
                historic_prefixes.add(prefix)

    historic_geoms: list[Any] = []
    for domain in ("macris", "local_historic"):
        df = resolver._load(domain)
        for _, row in df.iterrows():
            geom = _shapely_from_row(row)
            if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            historic_geoms.append(geom)
    historic_tree = STRtree(historic_geoms) if historic_geoms else None

    out: dict[str, dict[str, Any]] = {}
    for _, row in parcel_df.iterrows():
        pid = str(row.get("parcel_id") or "")
        lat = row.get("centroid_lat")
        lon = row.get("centroid_lon")
        if not pid or lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
            continue

        flags: set[str] = set()
        point = ShapelyPoint(float(lon), float(lat))
        if env_tree is not None:
            for idx in env_tree.query(point):
                geom = env_geoms[int(idx)]
                if geom.contains(point) or geom.intersects(point):
                    flags |= env_meta[int(idx)]

        if historic_tree is not None:
            for idx in historic_tree.query(point):
                geom = historic_geoms[int(idx)]
                if geom.contains(point) or geom.intersects(point):
                    flags.add("historic")

        addr = address_by_pid.get(pid) or str(row.get("address") or "")
        norm_addr = _normalize_address(addr)
        prefix = _address_prefix(addr)
        if norm_addr and norm_addr in historic_norms:
            flags.add("historic")
        elif prefix and prefix in historic_prefixes:
            flags.add("historic")

        out[pid] = {
            "flood_effective": "flood_effective" in flags,
            "flood_preliminary": "flood_preliminary" in flags,
            "flood_sfha": "flood_sfha" in flags,
            "wetland": "wetland" in flags,
            "historic": "historic" in flags,
            "21e_site": "21e_site" in flags,
            "ust_site": "ust_site" in flags,
        }
    return out


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


def _in_range(value: float | None, minimum: Any, maximum: Any) -> bool:
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


def _active_signals(
    permit: dict[str, Any],
    overlay: dict[str, Any],
    cfg: dict[str, Any],
) -> list[str]:
    signals: list[str] = []
    if cfg.get("include_open_permit", True) and permit.get("open_count", 0) > 0:
        signals.append("open_permit")
    if cfg.get("include_expired_permit", True) and permit.get("expired_count", 0) > 0:
        signals.append("expired_permit")
    if cfg.get("include_flood_effective", True) and overlay.get("flood_effective"):
        if cfg.get("require_flood_sfha_only"):
            if overlay.get("flood_sfha"):
                signals.append("flood_sfha")
        else:
            signals.append("flood_effective")
            if overlay.get("flood_sfha"):
                signals.append("flood_sfha")
    if cfg.get("include_flood_preliminary", False) and overlay.get("flood_preliminary"):
        signals.append("flood_preliminary")
        if overlay.get("flood_sfha"):
            signals.append("flood_sfha")
    if cfg.get("include_wetland", True) and overlay.get("wetland"):
        signals.append("wetland")
    if cfg.get("include_historic", True) and overlay.get("historic"):
        signals.append("historic")
    if cfg.get("include_21e_sites", True) and overlay.get("21e_site"):
        signals.append("21e_site")
    if cfg.get("include_ust_sites", True) and overlay.get("ust_site"):
        signals.append("ust_site")
    return sorted(set(signals))


def _score_risk(signals: list[str], permit: dict[str, Any], cfg: dict[str, Any]) -> float:
    weights = cfg.get("scoring") or {}
    w_open = float(weights.get("open_permit_weight") or 0.35)
    w_exp = float(weights.get("expired_permit_weight") or 0.15)
    w_flood = float(weights.get("flood_weight") or 0.25)
    w_wetland = float(weights.get("wetland_weight") or 0.15)
    w_hist = float(weights.get("historic_weight") or 0.10)
    w_21e = float(weights.get("21e_weight") or 0.50)
    w_ust = float(weights.get("ust_weight") or 0.20)

    score = 0.0
    open_n = int(permit.get("open_count") or 0)
    if "open_permit" in signals:
        score += w_open * min(open_n, 3) / 3.0 * 100.0
    if "expired_permit" in signals:
        score += w_exp * 100.0
    if "flood_sfha" in signals:
        score += w_flood * 100.0
    elif "flood_effective" in signals or "flood_preliminary" in signals:
        score += w_flood * 70.0
    if "wetland" in signals:
        score += w_wetland * 100.0
    if "historic" in signals:
        score += w_hist * 100.0
    if "21e_site" in signals:
        score += w_21e * 100.0
    if "ust_site" in signals:
        score += w_ust * 100.0
    return round(min(score, 100.0), 1)


def _passes_filters(
    *,
    signals: list[str],
    permit: dict[str, Any],
    lot_sqft: float | None,
    assessed: float | None,
    cfg: dict[str, Any],
) -> bool:
    min_signals = int(cfg.get("min_risk_signals") or 1)
    if len(signals) < min_signals:
        return False

    min_open = int(cfg.get("min_open_permit_count") or 0)
    if min_open > 0 and int(permit.get("open_count") or 0) < min_open:
        return False

    if not _in_range(assessed, cfg.get("min_assessed_value"), cfg.get("max_assessed_value")):
        return False
    if not _in_range(lot_sqft, cfg.get("min_lot_sqft"), cfg.get("max_lot_sqft")):
        return False
    return True


def _sort_candidates(candidates: list[dict[str, Any]], sort_by: str) -> None:
    key_map = {
        "risk_score": lambda c: (
            -float(c.get("risk_score") or 0),
            -int(c.get("open_permit_count") or 0),
        ),
        "open_permit_count": lambda c: (
            -int(c.get("open_permit_count") or 0),
            -float(c.get("risk_score") or 0),
        ),
        "assessed_value": lambda c: (
            -float(c.get("assessed_value") or 0),
            -float(c.get("risk_score") or 0),
        ),
        "tenure": lambda c: (-float(c.get("tenure_years") or 0), -float(c.get("risk_score") or 0)),
    }
    candidates.sort(key=key_map.get(sort_by, key_map["risk_score"]))


def scan_town_closing_risks(
    town_slug: str,
    effective_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    cfg = effective_cfg or merge_criteria_overrides(town_slug, {})
    prop_df = _property_frame(town_slug)
    if prop_df.empty:
        return tuple()

    permit_map = _permit_summary_map(town_slug)
    overlay_map = _overlay_risk_index(town_slug)
    lot_map = _parcel_lot_map(town_slug)
    max_scan = int((cfg.get("output") or {}).get("max_scan") or 20_000)

    candidates: list[dict[str, Any]] = []
    for _, row in prop_df.head(max_scan).iterrows():
        if _is_excluded(row, cfg):
            continue
        parcel_id = str(row.get("parcel_id") or "")
        if not parcel_id:
            continue

        permit = permit_map.get(
            parcel_id,
            {"open_count": 0, "expired_count": 0, "total_count": 0},
        )
        overlay = overlay_map.get(
            parcel_id,
            {
                "flood_effective": False,
                "flood_preliminary": False,
                "flood_sfha": False,
                "wetland": False,
                "historic": False,
                "21e_site": False,
                "ust_site": False,
            },
        )
        signals = _active_signals(permit, overlay, cfg)
        if not signals:
            continue

        metadata = _parse_metadata_field(row.get("metadata"))
        tenure = _tenure_years(metadata.get("last_sale_date"))
        lot_sqft = lot_map.get(parcel_id)
        if lot_sqft is None:
            lot_val = row.get("lot_size_sqft")
            if lot_val is not None and not pd.isna(lot_val):
                try:
                    lot_sqft = float(lot_val)
                except (TypeError, ValueError):
                    lot_sqft = None
        assessed = (
            float(row.get("assessed_value"))
            if row.get("assessed_value") is not None and not pd.isna(row.get("assessed_value"))
            else None
        )

        if not _passes_filters(
            signals=signals,
            permit=permit,
            lot_sqft=lot_sqft,
            assessed=assessed,
            cfg=cfg,
        ):
            continue

        risk_score = _score_risk(signals, permit, cfg)
        candidates.append({
            "parcel_id": parcel_id,
            "address": str(row.get("address") or "").strip(),
            "owner_name": str(row.get("owner_name") or "").strip() or None,
            "zone_code": str(row.get("zone_code") or "").strip().upper() or None,
            "tenure_years": round(tenure, 1) if tenure is not None else None,
            "last_sale_date": metadata.get("last_sale_date"),
            "lot_sqft": int(round(lot_sqft)) if lot_sqft else None,
            "assessed_value": assessed,
            "open_permit_count": int(permit.get("open_count") or 0),
            "expired_permit_count": int(permit.get("expired_count") or 0),
            "flood_sfha": bool(overlay.get("flood_sfha")),
            "wetland": bool(overlay.get("wetland")),
            "historic": bool(overlay.get("historic")),
            "21e_site": bool(overlay.get("21e_site")),
            "ust_site": bool(overlay.get("ust_site")),
            "risk_score": risk_score,
            "signals": signals,
            "signal_labels": [_SIGNAL_LABELS.get(s, s) for s in signals],
        })

    _sort_candidates(candidates, str(cfg.get("sort_by") or "risk_score"))
    return tuple(candidates)


def _criteria_summary_text(criteria: dict[str, Any], total: int, scanned: int) -> str:
    parts = [f"{total:,} parcels match your closing-risk filters (scanned {scanned:,} assessor records)."]
    if criteria.get("preset"):
        parts.append(f"Preset: {criteria['preset']}.")
    if criteria.get("min_open_permit_count"):
        parts.append(f"Open permits ≥ {criteria['min_open_permit_count']}.")
    zones = criteria.get("include_zone_codes") or []
    if zones:
        parts.append(f"Zones: {', '.join(zones)}.")
    return " ".join(parts)


def generate_closing_risk_radar(
    town_slug: str,
    *,
    highlight_parcel_id: str | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = merge_criteria_overrides(town_slug, criteria_overrides)
    criteria = cfg.get("applied_criteria") or criteria_snapshot(cfg)
    top_n = int(cfg.get("top_n") or 50)
    all_candidates = list(scan_town_closing_risks(town_slug, cfg))
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
            f"Your parcel ranks #{highlight_rank:,} town-wide (risk score {highlight_row['risk_score']}).",
        )
    elif highlight_parcel_id:
        summary_bits.append("Your parcel does not currently match Closing Risk Radar filters.")

    return {
        "report_type": "closing-risk-radar",
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
        "parcels": ranked,
        "highlight_parcel_id": highlight_parcel_id,
        "highlight_rank": highlight_rank,
        "highlight_parcel": highlight_row,
        "pilot_gaps": list(cfg.get("pilot_gaps") or []),
        "data_sources": [
            "property.parquet (assessor + owner of record)",
            "parcel.parquet (centroids for overlay scan)",
            "permits.parquet (open / expired permit ledger)",
            "environmental-overlay.parquet (FEMA flood + wetlands)",
            "macris.parquet + local-historic.parquet (historic flags)",
            f"configs/{town_slug}/config.yaml (closing_risk_radar rules)",
        ],
    }


def _raw_town_state(town_slug: str) -> str | None:
    from backend.services.closing_risk_radar_config import _raw_town_config

    cfg = _raw_town_config(town_slug)
    return cfg.get("state")


def closing_risk_radar_to_csv(payload: dict[str, Any]) -> str:
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
        "risk_score",
        "open_permit_count",
        "expired_permit_count",
        "flood_sfha",
        "wetland",
        "historic",
        "21e_site",
        "ust_site",
        "tenure_years",
        "assessed_value",
        "signals",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in payload.get("parcels") or []:
        out = dict(row)
        out["signals"] = "|".join(row.get("signals") or [])
        writer.writerow(out)
    return buf.getvalue()


def _signal_badges(signals: list[str]) -> str:
    if not signals:
        return "—"
    return ", ".join(_SIGNAL_LABELS.get(s, s) for s in signals)


def _criteria_html_lines(criteria: dict[str, Any]) -> str:
    lines: list[str] = []
    preset = criteria.get("preset")
    if preset:
        lines.append(f"<li>Preset: <strong>{preset}</strong></li>")
    lines.append(f"<li>Min risk signals: <strong>{criteria.get('min_risk_signals', 1)}</strong></li>")
    if criteria.get("min_open_permit_count"):
        lines.append(
            f"<li>Min open permits: <strong>{criteria.get('min_open_permit_count')}</strong></li>"
        )
    toggles = [
        ("include_open_permit", "Open permits"),
        ("include_expired_permit", "Expired permits"),
        ("include_flood_effective", "FEMA flood (effective)"),
        ("include_flood_preliminary", "FEMA flood (preliminary)"),
        ("include_wetland", "Wetlands"),
        ("include_historic", "Historic resources"),
        ("include_21e_sites", "MassDEP 21E Sites"),
        ("include_ust_sites", "UST Registry"),
    ]
    enabled = [label for key, label in toggles if criteria.get(key)]
    if enabled:
        lines.append(f"<li>Signal types: <strong>{', '.join(enabled)}</strong></li>")
    if criteria.get("require_flood_sfha_only"):
        lines.append("<li>Flood flag: <strong>SFHA only</strong></li>")
    zones = criteria.get("include_zone_codes") or []
    if zones:
        lines.append(f"<li>Zones included: <strong>{', '.join(zones)}</strong></li>")
    lines.append(f"<li>Sort by: <strong>{criteria.get('sort_by', 'risk_score')}</strong></li>")
    lines.append(f"<li>Top N: <strong>{criteria.get('top_n', 50)}</strong></li>")
    return "".join(lines)


def render_closing_risk_radar_html(payload: dict[str, Any]) -> str:
    town = payload.get("town_name") or payload.get("town_slug") or "Town"
    state = payload.get("state") or "MA"
    parcels = payload.get("parcels") or []
    highlight_id = payload.get("highlight_parcel_id")
    criteria = payload.get("criteria") or {}
    gaps = payload.get("pilot_gaps") or []
    prepared = payload.get("prepared_on") or date.today().isoformat()
    csv_text = closing_risk_radar_to_csv(payload)
    csv_b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
    csv_href = f"data:text/csv;base64,{csv_b64}"

    parcel_rows = ""
    for row in parcels:
        is_hi = row.get("parcel_id") == highlight_id
        row_cls = ' class="highlight"' if is_hi else ""
        hi_tag = ' <span class="tag">Your parcel</span>' if is_hi else ""
        parcel_rows += f"""<tr{row_cls}>
          <td class="num">{row.get('rank', '—')}</td>
          <td>{row.get('address', '—')}{hi_tag}</td>
          <td class="small">{row.get('parcel_id', '—')}</td>
          <td>{row.get('owner_name') or '—'}</td>
          <td>{row.get('zone_code') or '—'}</td>
          <td class="num"><strong>{row.get('risk_score', '—')}</strong></td>
          <td class="num">{row.get('open_permit_count', 0)}</td>
          <td class="num">{row.get('expired_permit_count', 0)}</td>
          <td>{'Yes' if row.get('flood_sfha') else '—'}</td>
          <td>{'Yes' if row.get('wetland') else '—'}</td>
          <td>{'Yes' if row.get('historic') else '—'}</td>
          <td>{'<span class="fl">Yes</span>' if row.get('21e_site') else '—'}</td>
          <td>{'<span class="wn">Yes</span>' if row.get('ust_site') else '—'}</td>
          <td>{_signal_badges(row.get('signals') or [])}</td>
        </tr>"""

    if not parcel_rows:
        parcel_rows = (
            "<tr><td colspan='12'>No parcels matched the current filters. "
            "Adjust closing_risk_radar rules in town config or refresh Gold data.</td></tr>"
        )

    highlight_block = ""
    hi = payload.get("highlight_parcel")
    if hi:
        highlight_block = f"""
<p class="note"><strong>Selected parcel:</strong> {hi.get('address', '—')} ranks
<strong>#{payload.get('highlight_rank')}</strong> with risk score <strong>{hi.get('risk_score')}</strong>
({_signal_badges(hi.get('signals') or [])}).</p>"""
    elif highlight_id:
        highlight_block = (
            '<p class="note">Selected parcel is not in the current Closing Risk Radar match set '
            "(may have no open/expired permits or env/historic flags under current filters).</p>"
        )

    gap_items = "".join(f"<li>{g}</li>" for g in gaps)
    criteria_html = _criteria_html_lines(criteria)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Closing Risk Radar — {town}, {state}</title>
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
  .logo-header {{ position: absolute; top: 20px; right: 28px; height: 32px; opacity: 0.8; }}
</style></head><body>
<div class="te-report">

<div class="hd" style="position: relative;">
  <img src="https://demo.towneye.ai/logo.png" alt="TownEye Logo" class="logo-header" />
  <h1>Closing Risk Radar</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{town}, {state}</div>
  <div class="meta">Prepared on {prepared} · Top {payload.get('top_n', 50)} of {payload.get('total_matches', 0):,} matches · {payload.get('parcels_scanned', 0):,} parcels scanned</div>
</div>

<h2>1 · Executive Summary</h2>
<p class="exec">{payload.get('executive_summary', '')}</p>
{highlight_block}
<a class="btn" href="{csv_href}" download="closing-risk-radar-{payload.get('town_slug', 'town')}.csv">Download CSV (top {payload.get('top_n', 50)})</a>

<h2>2 · Screening Criteria</h2>
<ul>
{criteria_html}
</ul>
<p class="small">Screening signals: {', '.join(_SIGNAL_LABELS.values())}. Not a title opinion or Phase I environmental report.</p>

<h2>3 · Ranked Closing Risks</h2>
<table>
<tr><th>#</th><th>Address</th><th>Parcel ID</th><th>Owner</th><th>Zone</th><th>Risk</th><th>Open</th><th>Expired</th><th>SFHA</th><th>Wetland</th><th>Historic</th><th>21E</th><th>UST</th><th>Signals</th></tr>
{parcel_rows}
</table>

<h2>4 · Not Yet Connected (Pilot)</h2>
<ul>{gap_items}</ul>

<p class="footnote">
  Town-wide due-diligence screening — not legal advice, not a substitute for registry title search,
  lender counsel review, or certified environmental assessment. Generate a parcel Risk &amp; Constraints
  report for full permit ledger and overlay detail on any target property.
</p>
</div>
</body></html>"""


def generate_closing_risk_radar_html(
    town_slug: str,
    parcel_id: str | None = None,
    prepared_for: str | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> str:
    del prepared_for
    payload = generate_closing_risk_radar(
        town_slug,
        highlight_parcel_id=parcel_id,
        criteria_overrides=criteria_overrides,
    )
    return render_closing_risk_radar_html(payload)
