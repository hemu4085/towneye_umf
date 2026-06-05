"""Lender Due Diligence Pack — comprehensive collateral regulatory dossier."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.lender_phase3 import (
    _analyze_property_tax,
    _analyze_registry,
    _analyze_sale_comps,
    _analyze_violations,
)
from backend.services.risk import generate_risk_json
from backend.services.zoning import generate_zoning_json
from backend.utils.parcel_lookup import _load_town_config, _town_display_name
from core.spatial import OverlayHit
from reports.buildability_brief import BriefData, BuildableEnvelope

_OPEN_PERMIT_STATUSES = frozenset({"SUBMITTED", "UNDER_REVIEW", "APPROVED", "INSPECTIONS"})
_ACTIVE_INFRA_STATUSES = frozenset({"PLANNED", "DESIGN", "BID", "IN_PROGRESS"})
_HIGH_SIGNAL_PERMIT_TYPES = frozenset({
    "DEMOLITION", "RESIDENTIAL_NEW", "RESIDENTIAL_RENO",
    "MECHANICAL", "SOLAR", "ELECTRICAL", "PLUMBING",
})
_ADDR_STOPWORDS = frozenset({
    "ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "DR", "DRIVE",
    "LN", "LANE", "CT", "COURT", "PL", "PLACE", "MA", "UNIT",
})

_STATUS_PILL = {
    "clear": ("#1a7a1a", "Clear"),
    "caution": ("#a06b00", "Caution"),
    "flagged": ("#a02020", "Flagged"),
    "pass": ("#1a7a1a", "Pass"),
    "review": ("#a06b00", "Review"),
    "escalate": ("#a02020", "Escalate"),
}


def _esc(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _pill(status: str, label: str | None = None) -> str:
    color, default = _STATUS_PILL.get(status, ("#555", status.title()))
    text = label or default
    return (
        f'<span style="color:{color};font-weight:bold;text-transform:uppercase">'
        f"{_esc(text)}</span>"
    )


def _zip_from_address(address: str | None) -> str | None:
    if not address:
        return None
    match = re.search(r"\b(\d{5})\b", address)
    return match.group(1) if match else None


def _attr(hit: OverlayHit, *keys: str) -> Any:
    attrs = hit.attributes or {}
    for key in keys:
        if key in attrs and attrs[key] not in (None, ""):
            return attrs[key]
    return None


def _truthy_sfha(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().upper() in {"T", "TRUE", "1", "YES", "Y"}


def _owner_entity_type(owner_name: str | None, keywords: list[str]) -> str:
    if not owner_name:
        return "Unknown"
    upper = owner_name.upper()
    for kw in keywords:
        token = kw.upper()
        if re.search(rf"\b{re.escape(token)}\b", upper):
            return "Organization / Trust"
    return "Individual"


def _gold_parquet(town_slug: str, domain: str) -> Path:
    return get_settings().gold_data_path / town_slug / f"{domain}.parquet"


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_addr(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.upper().strip())


def _fmt_date(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return "—"
        return ts.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(value)


def _lender_cfg(town_cfg: dict[str, Any]) -> dict[str, Any]:
    block = town_cfg.get("lender_report")
    return block if isinstance(block, dict) else {}


def _permit_lookback_years(town_cfg: dict[str, Any]) -> int:
    raw = _lender_cfg(town_cfg).get("permit_lookback_years", 10)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 10


def _street_tokens(address: str | None, town_cfg: dict[str, Any]) -> set[str]:
    if not address:
        return set()
    tokens = set()
    for part in re.sub(r"[^\w\s]", " ", address.upper()).split():
        if len(part) > 2 and part not in _ADDR_STOPWORDS:
            tokens.add(part)
    aliases = _lender_cfg(town_cfg).get("infra_street_aliases") or {}
    if isinstance(aliases, dict):
        for key, values in aliases.items():
            key_up = str(key).upper()
            if key_up in tokens or any(str(v).upper() in _normalize_addr(address) for v in values):
                tokens.add(key_up)
                tokens.update(str(v).upper() for v in values if v)
    return tokens


def _permit_matches_parcel(
    meta: dict[str, Any],
    parcel_id: str,
    address: str | None,
) -> bool:
    if str(meta.get("parcel_id") or "") == parcel_id:
        return True
    permit_addr = _normalize_addr(str(meta.get("address") or ""))
    target = _normalize_addr(address)
    if permit_addr and target and permit_addr == target:
        return True
    if permit_addr and target:
        permit_tokens = _street_tokens(permit_addr, {})
        target_tokens = _street_tokens(target, {})
        if permit_tokens & target_tokens:
            num_match = re.search(r"^\d+", target)
            if num_match and num_match.group(0) in permit_addr:
                return True
    return False


def _analyze_permits(
    data: BriefData,
    town_cfg: dict[str, Any],
) -> dict[str, Any]:
    path = _gold_parquet(data.inputs.town_slug, "permits")
    lookback = _permit_lookback_years(town_cfg)
    cutoff = pd.Timestamp.now(tz=UTC) - pd.DateOffset(years=lookback)
    parcel_id = data.inputs.parcel_id
    address = data.parcel.address

    if not path.is_file():
        return {
            "status": "caution",
            "note": "Building permit history is not loaded for this town.",
            "rows": [],
            "open_count": 0,
            "total_value": None,
            "signals": [],
            "lookback_years": lookback,
            "sources": _source_slugs(town_cfg, "permits") or ["permits"],
        }

    df = pd.read_parquet(path)
    rows: list[dict[str, str]] = []
    open_count = 0
    total_value = 0.0
    has_value = False
    signals: list[str] = []

    for _, row in df.iterrows():
        meta = _ensure_dict(row.get("metadata"))
        if not _permit_matches_parcel(meta, parcel_id, address):
            continue
        app_date = row.get("application_date")
        if app_date is not None and pd.notna(app_date):
            ts = pd.Timestamp(app_date)
            if ts.tzinfo is None:
                ts = ts.tz_localize(UTC)
            if ts < cutoff:
                continue

        status = str(row.get("status") or "")
        permit_type = str(row.get("permit_type") or "")
        est = row.get("estimated_value")
        if est is not None and pd.notna(est):
            total_value += float(est)
            has_value = True
        if status in _OPEN_PERMIT_STATUSES:
            open_count += 1
        if permit_type == "DEMOLITION" and status in _OPEN_PERMIT_STATUSES:
            signals.append(f"Open demolition permit ({row.get('permit_number')})")
        if permit_type == "MECHANICAL" and status == "CLOSED":
            signals.append("Recent HVAC/mechanical work — verify remaining useful life")
        if permit_type == "SOLAR" and status == "CLOSED":
            signals.append("Rooftop solar installation on record")

        rows.append({
            "permit_number": str(row.get("permit_number") or "—"),
            "permit_type": permit_type or "—",
            "status": status or "—",
            "application_date": _fmt_date(app_date),
            "approval_date": _fmt_date(row.get("approval_date")),
            "estimated_value": _fmt_money(est) if est is not None and pd.notna(est) else "—",
            "description": str(meta.get("description") or "—")[:120],
            "contractor": str(meta.get("contractor_license") or "—"),
        })

    rows.sort(key=lambda r: r["application_date"], reverse=True)

    if not rows:
        status = "clear"
        note = (
            f"No building permits in the last {lookback} years matched this parcel "
            f"(parcel_id or address). Confirm with Inspectional Services / ISD."
        )
    elif open_count > 0:
        status = "flagged" if any("demolition" in s.lower() for s in signals) else "caution"
        note = (
            f"{len(rows)} permit(s) on record; {open_count} still open or in inspections. "
            "Open work may affect collateral condition and completion risk."
        )
    else:
        status = "clear"
        note = (
            f"{len(rows)} closed permit(s) in the last {lookback} years — "
            "improvement history supports collateral condition review."
        )

    return {
        "status": status,
        "note": note,
        "rows": rows,
        "open_count": open_count,
        "total_value": total_value if has_value else None,
        "signals": signals,
        "lookback_years": lookback,
        "sources": _source_slugs(town_cfg, "permits") or ["permits"],
    }


def _infra_location_match(location: str, tokens: set[str]) -> bool:
    if not location or not tokens:
        return False
    loc = location.upper()
    return any(token in loc for token in tokens)


def _analyze_infra(
    data: BriefData,
    town_cfg: dict[str, Any],
) -> dict[str, Any]:
    path = _gold_parquet(data.inputs.town_slug, "infra-projects")
    tokens = _street_tokens(data.parcel.address, town_cfg)

    if not path.is_file():
        return {
            "status": "caution",
            "note": "DPW capital improvement plan data is not loaded for this town.",
            "nearby_rows": [],
            "town_active_count": 0,
            "sources": _source_slugs(town_cfg, "infra_friction") or ["infra-projects"],
        }

    df = pd.read_parquet(path)
    if df.empty:
        return {
            "status": "clear",
            "note": "No infrastructure projects in Gold data.",
            "nearby_rows": [],
            "town_active_count": 0,
            "sources": _source_slugs(town_cfg, "infra_friction") or ["infra-projects"],
        }

    active = df[df["status"].isin(_ACTIVE_INFRA_STATUSES)] if "status" in df.columns else df
    nearby_rows: list[dict[str, str]] = []
    disruption_types = frozenset({"ROAD_PAVING", "WATER_MAIN", "SEWER_MAIN", "STORMWATER"})

    for _, row in active.iterrows():
        loc = str(row.get("location_description") or "")
        if not _infra_location_match(loc, tokens):
            continue
        project_type = str(row.get("project_type") or "")
        nearby_rows.append({
            "project_name": str(row.get("project_name") or "—"),
            "project_type": project_type or "—",
            "status": str(row.get("status") or "—"),
            "location": loc,
            "estimated_cost": _fmt_money(row.get("estimated_cost")),
            "start_date": _fmt_date(row.get("start_date")),
            "end_date": _fmt_date(row.get("end_date")),
            "disruption": "Yes" if project_type in disruption_types else "Monitor",
        })

    town_active_count = len(active)
    if nearby_rows:
        high_impact = sum(1 for r in nearby_rows if r["disruption"] == "Yes")
        status = "flagged" if high_impact else "caution"
        note = (
            f"{len(nearby_rows)} active capital project(s) mention streets near this address. "
            "Road, water, or sewer work can affect access, noise, and basement/sewer risk during the loan term."
        )
    else:
        status = "clear"
        note = (
            f"No active DPW capital projects matched street tokens for this address "
            f"({town_active_count} town-wide active/upcoming projects in dataset)."
        )

    return {
        "status": status,
        "note": note,
        "nearby_rows": nearby_rows,
        "town_active_count": town_active_count,
        "match_tokens": sorted(tokens),
        "sources": _source_slugs(town_cfg, "infra_friction") or ["infra-projects"],
    }


def _cama_values(data: BriefData) -> dict[str, Any]:
    raw = (data.parcel_metadata_extras or {}).get("raw_attributes") or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _env_hits_by_category(hits: list[OverlayHit]) -> dict[str, list[OverlayHit]]:
    buckets: dict[str, list[OverlayHit]] = {
        "flood_effective": [],
        "flood_preliminary": [],
        "wetland": [],
        "other": [],
    }
    for hit in hits:
        category = str(_attr(hit, "category", "source_layer_name") or hit.layer or "").lower()
        if "prelim" in category or "preliminary" in category:
            buckets["flood_preliminary"].append(hit)
        elif "flood" in category or _attr(hit, "sfha_flag", "SFHA_TF") is not None:
            buckets["flood_effective"].append(hit)
        elif "wetland" in category or "wet" in category:
            buckets["wetland"].append(hit)
        else:
            code = str(hit.code or "").upper()
            if code in {"AE", "AH", "AO", "A", "VE", "X", "D"} or _truthy_sfha(_attr(hit, "sfha_flag")):
                buckets["flood_effective"].append(hit)
            elif code:
                buckets["wetland"].append(hit)
            else:
                buckets["other"].append(hit)
    return buckets


def _source_slugs(town_cfg: dict[str, Any], *keys: str) -> list[str]:
    mappings = town_cfg.get("source_mappings") or {}
    return [str(mappings[k]) for k in keys if mappings.get(k)]


def _analyze_flood(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    hits = data.raw_stack.environmental_overlay
    buckets = _env_hits_by_category(hits)
    effective = buckets["flood_effective"]
    preliminary = buckets["flood_preliminary"]
    wetlands = buckets["wetland"]

    primary_zone = None
    primary_subtype = None
    sfha = False
    static_bfe = None
    for hit in effective:
        zone = _attr(hit, "zone_code", "FLD_ZONE", "fld_zone") or hit.code
        if zone:
            primary_zone = str(zone).strip().upper()
        subtype = _attr(hit, "zone_subtype", "ZONE_SUBTY", "zone_subty")
        if subtype:
            primary_subtype = str(subtype)
        if _truthy_sfha(_attr(hit, "sfha_flag", "SFHA_TF", "sfha_tf")):
            sfha = True
        bfe = _attr(hit, "static_bfe", "STATIC_BFE", "static_bfe")
        if bfe is not None:
            try:
                static_bfe = float(bfe)
            except (TypeError, ValueError):
                pass

    if not effective and not wetlands:
        status = "clear"
        risk_level = "NONE"
        insurance_required = False
        note = (
            "No effective flood-zone or wetland polygon overlaps this parcel centroid. "
            "FEMA NFHL point query would typically classify this as Zone X (minimal hazard). "
            "Flood insurance is NOT required by federally-backed lenders."
        )
    elif sfha or (primary_zone and primary_zone not in {"X", "C", "D"} and primary_zone[0] in {"A", "V"}):
        status = "flagged"
        risk_level = "HIGH"
        insurance_required = True
        note = (
            f"This parcel overlaps a Special Flood Hazard Area (Zone {primary_zone or 'SFHA'}). "
            "Flood insurance IS required for federally-backed mortgages. "
            "Obtain an elevation certificate if BFE is disputed."
        )
    elif primary_zone and primary_zone.startswith("X"):
        status = "caution"
        risk_level = "MODERATE"
        insurance_required = False
        note = (
            f"Parcel is in FEMA Zone {primary_zone} (0.2% annual chance / moderate risk). "
            "Flood insurance is recommended but not required for federally-backed lenders."
        )
    elif wetlands:
        status = "caution"
        risk_level = "MODERATE"
        insurance_required = False
        note = (
            "Wetland overlay intersects this parcel. Flood insurance may not be required, "
            "but wetland permitting can restrict improvements and delay collateral repairs."
        )
    else:
        status = "caution"
        risk_level = "MODERATE"
        insurance_required = False
        note = "Environmental overlay hit detected — review flood/wetland detail rows below."

    prelim_zone = None
    map_change = False
    if preliminary:
        prelim_zone = _attr(preliminary[0], "zone_code", "fld_zone", "FLD_ZONE") or preliminary[0].code
        if primary_zone and prelim_zone and str(prelim_zone).upper() != str(primary_zone).upper():
            map_change = True

    rows: list[dict[str, str]] = []
    for hit in effective + preliminary + wetlands:
        rows.append({
            "layer": hit.layer or _attr(hit, "category", "source_layer_name") or "environmental",
            "zone": str(_attr(hit, "zone_code", "FLD_ZONE", "fld_zone") or hit.code or "—"),
            "subtype": str(_attr(hit, "zone_subtype", "ZONE_SUBTY", "zone_subty") or "—"),
            "sfha": "Yes" if _truthy_sfha(_attr(hit, "sfha_flag", "SFHA_TF")) else "No",
            "bfe": str(_attr(hit, "static_bfe", "STATIC_BFE") or "—"),
            "label": str(hit.label or "—"),
        })

    return {
        "status": status,
        "risk_level": risk_level,
        "insurance_required": insurance_required,
        "note": note,
        "primary_zone": primary_zone,
        "primary_subtype": primary_subtype,
        "static_bfe": static_bfe,
        "map_change_warning": map_change,
        "preliminary_zone": str(prelim_zone) if prelim_zone else None,
        "wetland_count": len(wetlands),
        "rows": rows,
        "sources": _source_slugs(
            town_cfg, "environmental_overlay", "climate_resilience",
        ) or ["environmental-overlay", "fema-flood-maps"],
    }


def _analyze_historic(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    macris_hits = data.raw_stack.macris
    local_hits = data.raw_stack.local_historic
    hist_cfg = town_cfg.get("historic_resources") or {}

    designations: list[str] = []
    names: list[str] = []
    rows: list[dict[str, str]] = []

    for hit in macris_hits + local_hits:
        desig = _attr(hit, "designation", "DESIGNATIO", "legend", "Designated") or hit.layer
        name = hit.label or _attr(hit, "historic_name", "HISTORIC_N", "Hist_Name", "district", "Name")
        if desig:
            designations.append(str(desig))
        if name:
            names.append(str(name))
        rows.append({
            "source": "MACRIS (state)" if hit in macris_hits else "Local historic GIS",
            "designation": str(desig or "—"),
            "name": str(name or "—"),
            "constructed": str(_attr(hit, "construction_date", "CONSTRUCTI", "Cnstr_Date") or "—"),
            "style": str(_attr(hit, "architectural_style", "ARCHITECTU", "Architect") or "—"),
            "id": str(_attr(hit, "mhcn", "MHCN", "MHC_id") or hit.code or "—"),
        })

    in_lhd = any(
        "LHD" in d.upper() or "LOCAL HISTORIC" in d.upper() or "LOCAL_HISTORIC" in d.upper()
        for d in designations
    ) or any("local_historic" in (h.layer or "").lower() for h in local_hits)

    if not rows:
        status = "clear"
        note = (
            "No MACRIS inventory point/area overlap and no local historic district boundary "
            "intersects this parcel. No Certificate of Appropriateness workflow expected."
        )
    elif in_lhd:
        status = "flagged"
        note = (
            "This property IS in a Local Historic District. Exterior alterations visible from "
            "a public way require a Certificate of Appropriateness BEFORE any building permit "
            "is issued. Budget additional time and design review for renovation loans."
        )
    else:
        status = "caution"
        note = (
            "Historic resource overlap detected (MACRIS inventory or town historic layer). "
            "Demolition or substantial exterior work may trigger demolition-delay review even "
            "if not in a binding Local Historic District."
        )

    return {
        "status": status,
        "in_lhd": in_lhd,
        "hit_count": len(rows),
        "designations": sorted(set(designations)),
        "names": names[:6],
        "note": note,
        "macris_search_url": hist_cfg.get("macris_search_url", ""),
        "ahc_url": hist_cfg.get("ahc_inventory_url", ""),
        "rows": rows,
        "sources": _source_slugs(town_cfg, "historic_resources", "local_historic")
        or ["ma-mhc-macris", "local-historic"],
    }


def _analyze_conformity(data: BriefData) -> dict[str, Any]:
    noncomp_hits = data.raw_stack.noncompliance
    prop = data.property_info
    rows: list[dict[str, str]] = []
    for hit in noncomp_hits:
        rows.append({
            "land_use_code": str(_attr(hit, "land_use_code", "LandUseCod") or "—"),
            "zone_diff": str(_attr(hit, "land_use_zone_diff", "luzndiff") or "—"),
            "status": str(hit.label or hit.layer or _attr(hit, "status") or "Non-conforming"),
        })

    nonconforming_lot = any(
        env.qualifies is False for env in data.envelopes if env.qualifies is not None
    )
    over_far = any(
        env.pct_of_far_cap is not None and env.pct_of_far_cap > 1.0 for env in data.envelopes
    )

    if rows or nonconforming_lot or over_far:
        status = "flagged" if rows else "caution"
        parts = []
        if rows:
            parts.append(f"{len(rows)} land-use / zoning non-compliance polygon(s)")
        if nonconforming_lot:
            parts.append("lot below base-zone minimum size")
        if over_far:
            parts.append("existing GFA exceeds FAR cap (legal non-conforming envelope)")
        note = (
            "Collateral legal-use review required: " + "; ".join(parts) + ". "
            "Pre-existing non-conforming uses may continue but expansion or tear-down rebuild "
            "typically must conform to current zoning."
        )
    else:
        status = "clear"
        note = (
            "No land-use non-compliance polygon overlap and dimensional minimums appear satisfied "
            "under resolved zoning rules."
        )

    return {
        "status": status,
        "note": note,
        "noncomp_rows": rows,
        "assessor_use": (
            f"{prop.luc or ''} — {prop.luc_description}".strip(" —")
            if prop and (prop.luc or prop.luc_description)
            else None
        ),
        "nonconforming_lot": nonconforming_lot,
        "over_far": over_far,
    }


def _load_market_metrics(town_slug: str, zipcode: str | None) -> dict[str, Any]:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.is_file():
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}

    def _latest(metric: str) -> float | None:
        sub = df[df["metric_name"] == metric].copy()
        if sub.empty:
            return None
        if zipcode and "geo_value" in sub.columns:
            z = sub[sub["geo_value"] == zipcode]
            if not z.empty:
                sub = z
        sub["observation_date"] = pd.to_datetime(sub["observation_date"], utc=True, errors="coerce")
        sub = sub.dropna(subset=["observation_date"]).sort_values("observation_date")
        if sub.empty:
            return None
        val = sub.iloc[-1]["metric_value"]
        return None if pd.isna(val) else float(val)

    return {
        "median_sale_price": _latest("MEDIAN_SALE_PRICE"),
        "median_dom": _latest("AVG_DAYS_ON_MARKET"),
        "months_supply": _latest("MONTHS_OF_SUPPLY"),
        "price_per_sqft": _latest("PRICE_PER_SQFT"),
        "zip": zipcode,
    }


def _estimate_market_value(assessed: float, town_slug: str, zipcode: str | None) -> dict[str, Any] | None:
    path = get_settings().gold_data_path / town_slug / "market-trends.parquet"
    if not path.is_file() or assessed <= 0:
        return None
    df = pd.read_parquet(path)
    if df.empty or "metric_name" not in df.columns:
        return None

    sp = df[df["metric_name"] == "MEDIAN_SALE_PRICE"].copy()
    if sp.empty:
        return None
    if zipcode and "geo_value" in sp.columns:
        z = sp[sp["geo_value"] == zipcode]
        if not z.empty:
            sp = z
    sp["observation_date"] = pd.to_datetime(sp["observation_date"], utc=True, errors="coerce")
    sp = sp.dropna(subset=["observation_date"]).sort_values("observation_date")
    if len(sp) < 2:
        return None

    latest = sp.iloc[-1]
    latest_val = float(latest["metric_value"])
    latest_date = latest["observation_date"]
    target = latest_date - pd.DateOffset(months=12)
    sp["_delta"] = (sp["observation_date"] - target).abs()
    yr_ago = sp.loc[sp["_delta"].idxmin()]
    yr_ago_val = float(yr_ago["metric_value"])
    if yr_ago_val <= 0:
        return None

    factor = latest_val / yr_ago_val
    return {
        "estimated_value": round(assessed * factor, -2),
        "appreciation_1yr_pct": round((factor - 1) * 100, 1),
        "as_of": str(latest_date.date()),
        "method": "Assessed value × zip median sale price YoY trend (market-trends.parquet)",
    }


def _overall_grade(
    flood: dict,
    historic: dict,
    conformity: dict,
    risk: dict,
    permits: dict | None = None,
    infra: dict | None = None,
    tax: dict | None = None,
    registry: dict | None = None,
    violations: dict | None = None,
) -> tuple[str, str]:
    statuses = [flood["status"], historic["status"], conformity["status"], risk["overall_status"]]
    if permits:
        statuses.append(permits["status"])
    if infra:
        statuses.append(infra["status"])
    if tax:
        statuses.append(tax["status"])
    if registry:
        statuses.append(registry["status"])
    if violations:
        statuses.append(violations["status"])
    if "flagged" in statuses:
        return "escalate", "One or more material collateral flags require senior review."
    if "caution" in statuses:
        return "review", "Mixed collateral signals — standard underwriting with documented exceptions."
    return "pass", "No material regulatory overlays flagged at parcel resolution."


def _facts_rows(data: BriefData, town_cfg: dict[str, Any]) -> list[tuple[str, str]]:
    p = data.parcel
    prop = data.property_info
    cama = _cama_values(data)
    org_keywords = town_cfg.get("party_type_org_keywords") or []
    rows: list[tuple[str, str]] = [
        ("Street address", p.address or "—"),
        ("Parcel ID", p.parcel_id),
        ("Town", _town_display_name(data.inputs.town_slug)),
    ]

    short_id = cama.get("Short_id") or cama.get("MAP_PAR_ID")
    if short_id:
        rows.append(("Map–block–lot", str(short_id)))

    if prop and prop.owner_name:
        entity = _owner_entity_type(prop.owner_name, org_keywords)
        rows.append(("Owner of record", f"{prop.owner_name} ({entity})"))

    if prop and prop.book_page:
        rows.append(("Deed reference (book/page)", prop.book_page))
    elif cama.get("LS_BOOK") or cama.get("LS_PAGE"):
        rows.append((
            "Deed reference (book/page)",
            f"{cama.get('LS_BOOK', '—')} / {cama.get('LS_PAGE', '—')}",
        ))

    if prop and prop.year_built:
        style = f" ({prop.building_type})" if prop.building_type else ""
        rows.append(("Year built", f"{prop.year_built}{style}"))

    if prop and (prop.beds or prop.baths):
        rows.append(("Bedrooms / bathrooms", f"{prop.beds or '—'} / {prop.baths or '—'}"))

    if prop and prop.finished_area_sqft:
        rows.append(("Finished living area", f"{_fmt_int(prop.finished_area_sqft)} sf (assessor)"))

    lot_parts = []
    if prop and prop.lot_size_sqft:
        lot_parts.append(f"{_fmt_int(prop.lot_size_sqft)} sf assessor (regulatory)")
    if p.area_sqft:
        lot_parts.append(f"{_fmt_int(p.area_sqft)} sf GIS polygon")
    if lot_parts:
        rows.append(("Lot size", " · ".join(lot_parts)))

    if p.longest_edge_ft:
        rows.append(("Longest parcel edge (frontage proxy)", f"{_fmt_int(p.longest_edge_ft)} ft"))

    if prop and prop.last_sale_date:
        rows.append((
            "Last arm's-length sale",
            f"{_fmt_money(prop.last_sale_price)} on {prop.last_sale_date}",
        ))
    elif cama.get("LS_DATE") or cama.get("LS_PRICE"):
        rows.append((
            "Last sale (CAMA)",
            f"{_fmt_money(cama.get('LS_PRICE'))} on {cama.get('LS_DATE', '—')}",
        ))

    land_val = cama.get("LAND_VAL")
    bldg_val = cama.get("BLDG_VAL")
    total_val = (prop.assessed_value if prop else None) or cama.get("TOTAL_VAL")
    if land_val or bldg_val:
        rows.append((
            "Assessed value (land / building / total)",
            f"{_fmt_money(land_val)} / {_fmt_money(bldg_val)} / {_fmt_money(total_val)}",
        ))
    elif total_val:
        rows.append(("Total assessed value", _fmt_money(total_val)))

    if prop and (prop.luc_description or prop.luc):
        rows.append(("Assessor use code", f"{prop.luc or ''} — {prop.luc_description or ''}".strip(" —")))

    rows.append(("GIS centroid", f"{p.centroid_lat:.6f}, {p.centroid_lon:.6f}"))
    return rows


def _envelope_rows(envelopes: list[BuildableEnvelope]) -> str:
    if not envelopes:
        return "<tr><td colspan='7'>No envelope math — zoning rules missing for resolved hits.</td></tr>"
    rows = ""
    for e in envelopes:
        pct = _fmt_pct(e.pct_of_far_cap * 100) if e.pct_of_far_cap is not None else "—"
        qual = (
            "Yes" if e.qualifies else ("No — NON-CONFORMING" if e.qualifies is False else "—")
        )
        rows += f"""<tr>
          <td><strong>{_esc(e.label)}</strong></td>
          <td>{_fmt_int(e.lot_sqft)} sf</td>
          <td>{e.max_far if e.max_far is not None else "—"}</td>
          <td>{_fmt_int(e.max_gfa_sqft)} sf</td>
          <td>{_fmt_int(e.existing_gfa_sqft)} sf</td>
          <td>{_fmt_int(e.expansion_room_sqft)} sf</td>
          <td>{pct}</td>
          <td>{_esc(qual)}</td>
        </tr>
        <tr><td colspan="8" class="small">{_esc(e.rationale)}</td></tr>"""
    return rows


def _zoning_detail_rows(zoning: dict) -> str:
    zones = (zoning.get("base_zones") or []) + (zoning.get("overlay_zones") or [])
    if not zones:
        return "<tr><td colspan='8'>No machine-readable zoning rules for resolved zone codes.</td></tr>"
    rows = ""
    for z in zones:
        uses = ", ".join((z.get("allowed_uses") or [])[:8]) or "—"
        rows += f"""<tr>
          <td><strong>{_esc(z.get('zone_code'))}</strong>{' (overlay)' if z.get('is_overlay') else ''}</td>
          <td>{_esc(z.get('description') or '—')}</td>
          <td class="small">{_esc(uses)}</td>
          <td>{z.get('max_far') if z.get('max_far') is not None else '—'}</td>
          <td>{_fmt_int(z.get('min_lot_sqft'))}</td>
          <td>{z.get('max_height_ft') if z.get('max_height_ft') is not None else '—'}</td>
          <td>{z.get('setback_front_ft') if z.get('setback_front_ft') is not None else '—'}</td>
          <td>{z.get('setback_side_ft') if z.get('setback_side_ft') is not None else '—'} / {z.get('setback_rear_ft') if z.get('setback_rear_ft') is not None else '—'}</td>
        </tr>"""
    return rows


def generate_lender_html(data: BriefData, prepared_for: str | None) -> str:
    town_slug = data.inputs.town_slug
    town_cfg = _load_town_config(town_slug)
    risk = generate_risk_json(data)
    zoning = generate_zoning_json(data)
    flood = _analyze_flood(data, town_cfg)
    historic = _analyze_historic(data, town_cfg)
    conformity = _analyze_conformity(data)
    permits = _analyze_permits(data, town_cfg)
    infra = _analyze_infra(data, town_cfg)
    tax = _analyze_property_tax(data, town_cfg)
    registry = _analyze_registry(data, town_cfg)
    violations = _analyze_violations(data, town_cfg)
    comps = _analyze_sale_comps(data, town_cfg)
    grade, grade_note = _overall_grade(
        flood, historic, conformity, risk, permits, infra, tax, registry, violations,
    )

    address = data.parcel.address or data.inputs.parcel_id
    zipcode = _zip_from_address(address)
    assessed = None
    if data.property_info and data.property_info.assessed_value:
        assessed = float(data.property_info.assessed_value)
    if assessed is None:
        cama = _cama_values(data)
        if cama.get("TOTAL_VAL"):
            try:
                assessed = float(cama["TOTAL_VAL"])
            except (TypeError, ValueError):
                pass

    market = _load_market_metrics(town_slug, zipcode)
    avm = _estimate_market_value(assessed, town_slug, zipcode) if assessed else None

    report_date = data.report_date_text
    recipient = prepared_for or data.inputs.prepared_for

    facts_html = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in _facts_rows(data, town_cfg)
    )

    risk_rows = "".join(
        f"""<tr>
          <td>{_esc(c['label'])}</td>
          <td>{_pill(c['status'], c['status_label'])}</td>
          <td>{_esc(c['detail'])}</td>
          <td class="small">{_esc(c['source'])}</td>
        </tr>"""
        for c in risk["constraints"]
    )

    flood_rows = "".join(
        f"""<tr>
          <td>{_esc(r['layer'])}</td>
          <td><strong>{_esc(r['zone'])}</strong></td>
          <td>{_esc(r['subtype'])}</td>
          <td>{_esc(r['sfha'])}</td>
          <td>{_esc(r['bfe'])}</td>
          <td>{_esc(r['label'])}</td>
        </tr>"""
        for r in flood["rows"]
    ) or "<tr><td colspan='6'>No environmental overlay intersections.</td></tr>"

    historic_rows = "".join(
        f"""<tr>
          <td>{_esc(r['source'])}</td>
          <td>{_esc(r['designation'])}</td>
          <td>{_esc(r['name'])}</td>
          <td>{_esc(r['constructed'])}</td>
          <td>{_esc(r['style'])}</td>
          <td>{_esc(r['id'])}</td>
        </tr>"""
        for r in historic["rows"]
    ) or "<tr><td colspan='6'>No historic resource intersections.</td></tr>"

    noncomp_rows = "".join(
        f"""<tr>
          <td>{_esc(r['land_use_code'])}</td>
          <td>{_esc(r['zone_diff'])}</td>
          <td>{_esc(r['status'])}</td>
        </tr>"""
        for r in conformity["noncomp_rows"]
    )

    map_warning = ""
    if flood["map_change_warning"]:
        map_warning = (
            f"<p class='callout warn'><strong>Preliminary map change:</strong> effective zone "
            f"{_esc(flood['primary_zone'])} vs preliminary {_esc(flood['preliminary_zone'])} — "
            "future flood insurance requirements may change.</p>"
        )

    avm_block = ""
    if avm:
        ratio = (assessed / avm["estimated_value"]) if assessed and avm["estimated_value"] else None
        avm_block = f"""
        <tr><th>Indicative market value (trend-adjusted)</th>
            <td>{_fmt_money(avm['estimated_value'])} as of { _esc(avm['as_of']) }
            ({_fmt_pct(avm['appreciation_1yr_pct'])} zip YoY)</td></tr>"""
        if ratio:
            avm_block += f"""
        <tr><th>Assessed / indicative market</th><td>{_fmt_pct(ratio * 100)}</td></tr>"""

    market_rows = ""
    if market:
        market_rows = f"""
        <tr><th>Zip median sale price</th><td>{_fmt_money(market.get('median_sale_price'))} ({_esc(zipcode or 'town')})</td></tr>
        <tr><th>Avg days on market</th><td>{_fmt_int(market.get('median_dom'))} days</td></tr>
        <tr><th>Months of supply</th><td>{market.get('months_supply') if market.get('months_supply') is not None else '—'}</td></tr>
        <tr><th>Median price / sqft (zip)</th><td>{_fmt_money(market.get('price_per_sqft'))}</td></tr>"""

    permit_rows = "".join(
        f"""<tr>
          <td>{_esc(r['permit_number'])}</td>
          <td>{_esc(r['permit_type'])}</td>
          <td>{_esc(r['status'])}</td>
          <td>{_esc(r['application_date'])}</td>
          <td>{_esc(r['approval_date'])}</td>
          <td>{r['estimated_value']}</td>
          <td class="small">{_esc(r['description'])}</td>
        </tr>"""
        for r in permits["rows"]
    )

    permit_signals = ""
    if permits["signals"]:
        permit_signals = "<ul class=\"small\">" + "".join(
            f"<li>{_esc(s)}</li>" for s in permits["signals"]
        ) + "</ul>"

    infra_rows = "".join(
        f"""<tr>
          <td>{_esc(r['project_name'])}</td>
          <td>{_esc(r['project_type'])}</td>
          <td>{_esc(r['status'])}</td>
          <td class="small">{_esc(r['location'])}</td>
          <td>{r['estimated_cost']}</td>
          <td>{_esc(r['start_date'])} – {_esc(r['end_date'])}</td>
          <td>{_esc(r['disruption'])}</td>
        </tr>"""
        for r in infra["nearby_rows"]
    )

    tax_rows = "".join(
        f"""<tr>
          <td>{_esc(r['fiscal_year'])}</td><td>{_esc(r['status'])}</td>
          <td>{r['balance_due']}</td><td>{_esc(r['due_date'])}</td>
          <td>{_esc(r['last_payment'])}</td><td>{_esc(r['bill_type'])}</td>
        </tr>"""
        for r in tax["rows"]
    )

    registry_rows = "".join(
        f"""<tr>
          <td>{_esc(r['record_type'])}</td><td>{_esc(r['status'])}</td>
          <td>{_esc(r['recording_date'])}</td><td>{r['amount']}</td>
          <td>{_esc(r['book_page'])}</td><td class="small">{_esc(r['grantee'])}</td>
        </tr>"""
        for r in registry["rows"]
    )

    violation_rows = "".join(
        f"""<tr>
          <td>{_esc(r['source'])}</td><td>{_esc(r['violation_type'])}</td>
          <td>{_esc(r['status'])}</td><td>{_esc(r['opened'])}</td>
          <td class="small">{_esc(r['detail'])}</td>
        </tr>"""
        for r in violations["rows"]
    )

    comp_rows = "".join(
        f"""<tr>
          <td class="small">{_esc(c['address'])}</td>
          <td>{_fmt_int(c['distance_ft'])} ft</td>
          <td>{_fmt_money(c['sale_price'])}</td>
          <td>{_esc(c['sale_date'])}</td>
          <td>{_fmt_int(c['finished_sf'])} sf</td>
          <td>{_fmt_money(c['price_per_sf']) if c['price_per_sf'] else '—'}</td>
        </tr>"""
        for c in comps["rows"]
    )

    infra_tokens_note = ""
    if infra.get("match_tokens"):
        infra_tokens_note = (
            f"<p class=\"small\">Street/corridor match tokens: "
            f"{_esc(', '.join(infra['match_tokens']))}</p>"
        )

    hist_links = ""
    if historic["macris_search_url"]:
        hist_links += f'<a href="{_esc(historic["macris_search_url"])}">MACRIS map</a>'
    if historic["ahc_url"]:
        if hist_links:
            hist_links += " · "
        hist_links += f'<a href="{_esc(historic["ahc_url"])}">Town Historical Commission</a>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lender Due Diligence Pack — {_esc(address)}</title>
<style>
  html,body{{box-sizing:border-box;margin:0;padding:0}}
  *,*::before,*::after{{box-sizing:inherit}}
  .te-report{{font-family:'DM Sans',Arial,sans-serif;color:#0B1F3A;width:100%;max-width:none;
        padding:28px clamp(16px,3vw,48px);font-size:14px;line-height:1.5}}
  h1{{font-family:Georgia,serif;color:#0B1F3A;border-bottom:3px solid #C9A84C;padding-bottom:8px;margin:0 0 8px}}
  h2{{font-family:Georgia,serif;font-size:15px;letter-spacing:.5px;text-transform:uppercase;color:#0B1F3A;
      border-bottom:2px solid #C9A84C;padding-bottom:4px;margin:28px 0 12px}}
  h3{{font-size:14px;color:#0B1F3A;margin:16px 0 8px}}
  .hero{{background:#0B1F3A;color:#F5F0E8;padding:20px 24px;border-radius:8px;margin-bottom:24px}}
  .hero h1{{color:#C9A84C;border:none;margin:0 0 6px}}
  .hero .meta{{font-size:12px;opacity:.9}}
  .grade{{font-size:1.05rem;font-weight:600;color:#C9A84C;margin-top:8px}}
  table{{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:13px;table-layout:auto}}
  th{{background:#0B1F3A;color:#F5F0E8;text-align:left;padding:8px;vertical-align:top}}
  td{{padding:8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#faf9f6}}
  .facts th{{width:38%}}
  .summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:12px 0}}
  .summary-card{{border:1px solid #ddd;border-radius:6px;padding:12px;background:#fff}}
  .summary-card h3{{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.4px}}
  .callout{{padding:10px 14px;border-radius:4px;margin:10px 0}}
  .callout.ok{{background:#edf7ed;border-left:4px solid #1a7a1a}}
  .callout.warn{{background:#fff8e6;border-left:4px solid #c89800}}
  .callout.bad{{background:#fdecec;border-left:4px solid #a02020}}
  .small{{font-size:11.5px;color:#555}}
  .page-break{{page-break-before:always}}
  .disclaimer{{font-size:11px;color:#666;margin-top:36px;border-top:1px solid #ccc;padding-top:12px}}
  .verdict{{padding:10px 14px;border-radius:4px;background:#f4f6fb;border-left:4px solid #0B1F3A;margin:10px 0}}
</style></head><body>
<div class="te-report">

<div class="hero">
  <h1>Lender Due Diligence Pack</h1>
  <p><strong>{_esc(address)}</strong></p>
  <p class="meta">
    {f'Prepared for {_esc(recipient)} · ' if recipient else ''}
    Prepared on {_esc(report_date)} · Parcel {_esc(data.inputs.parcel_id)}
  </p>
  <p class="grade">Overall collateral grade: {_pill(grade)} — {_esc(grade_note)}</p>
</div>

<h2>1 · Executive collateral memo</h2>
<div class="summary-grid">
  <div class="summary-card">
    <h3>Flood &amp; insurability</h3>
    <p>{_pill(flood['status'])} · Zone {_esc(flood['primary_zone'] or 'X / none')}</p>
    <p class="small">{'Insurance required' if flood['insurance_required'] else 'Insurance not required (GSE)'}</p>
  </div>
  <div class="summary-card">
    <h3>Historic &amp; preservation</h3>
    <p>{_pill(historic['status'])} · {historic['hit_count']} hit(s)</p>
    <p class="small">{'LHD — COA required' if historic['in_lhd'] else 'Review historic rows'}</p>
  </div>
  <div class="summary-card">
    <h3>Legal use &amp; conformity</h3>
    <p>{_pill(conformity['status'])}</p>
    <p class="small">{_esc(conformity['assessor_use'] or 'See zoning section')}</p>
  </div>
  <div class="summary-card">
    <h3>Improvement history</h3>
    <p>{_pill(permits['status'])} · {len(permits['rows'])} permit(s)</p>
    <p class="small">{permits['open_count']} open · lookback {permits['lookback_years']} yr</p>
  </div>
  <div class="summary-card">
    <h3>Nearby capital projects</h3>
    <p>{_pill(infra['status'])} · {len(infra['nearby_rows'])} match(es)</p>
    <p class="small">{infra['town_active_count']} active town-wide in CIP dataset</p>
  </div>
  <div class="summary-card">
    <h3>Property tax</h3>
    <p>{_pill(tax['status'])}</p>
    <p class="small">{len(tax['rows'])} fiscal year row(s) matched</p>
  </div>
  <div class="summary-card">
    <h3>Registry &amp; liens</h3>
    <p>{_pill(registry['status'])} · {registry['active_liens']} active</p>
    <p class="small">{len(registry['rows'])} instrument(s) on record</p>
  </div>
  <div class="summary-card">
    <h3>Violations</h3>
    <p>{_pill(violations['status'])} · {violations['open_count']} open</p>
    <p class="small">{len(violations['rows'])} total matched</p>
  </div>
  <div class="summary-card">
    <h3>Assessor comps</h3>
    <p>{_pill(comps['status'])} · {len(comps['rows'])} within {comps['radius_mi']} mi</p>
    <p class="small">Median {_fmt_money(comps['median_ppsf'])}/sf (CAMA sales)</p>
  </div>
</div>
<div class="verdict">{_esc(data.headline_verdict_text)}</div>

<h2>2 · Collateral identification</h2>
<p class="small">Assessor &amp; MassGIS CAMA fields from TownEye Gold — not a title report or MLS listing.</p>
<table class="facts">{facts_html}</table>

<h2>3 · Flood, wetland &amp; hazard insurability</h2>
<div class="callout {'bad' if flood['insurance_required'] else 'ok'}">{_esc(flood['note'])}</div>
{map_warning}
<table>
  <tr><th>Layer</th><th>Zone</th><th>Subtype</th><th>SFHA</th><th>Static BFE</th><th>Label</th></tr>
  {flood_rows}
</table>
<p class="small">Sources: {', '.join(_esc(s) for s in flood['sources'])}</p>

<h2>4 · Historic &amp; preservation overlays</h2>
<div class="callout {'bad' if historic['in_lhd'] else ('warn' if historic['rows'] else 'ok')}">{_esc(historic['note'])}</div>
{f'<p class="small">{hist_links}</p>' if hist_links else ''}
<table>
  <tr><th>Source</th><th>Designation</th><th>Name</th><th>Built</th><th>Style</th><th>ID</th></tr>
  {historic_rows}
</table>

<h2>5 · Zoning stack &amp; permitted envelope</h2>
<p><strong>Base:</strong> {_esc(', '.join(zoning.get('base_labels') or []) or '—')}
 &nbsp;·&nbsp; <strong>Overlays:</strong> {_esc(', '.join(zoning.get('overlay_labels') or []) or '—')}</p>
<table>
  <tr><th>Zone</th><th>Description</th><th>Permitted uses</th><th>Max FAR</th><th>Min lot</th><th>Max ht</th><th>Front sb</th><th>Side/rear sb</th></tr>
  {_zoning_detail_rows(zoning)}
</table>

<h3>Buildable envelope (regulatory math)</h3>
<table>
  <tr><th>Regime</th><th>Lot</th><th>FAR</th><th>Max GFA</th><th>Existing GFA</th><th>Expansion room</th><th>% of FAR cap</th><th>Qualifies</th></tr>
  {_envelope_rows(data.envelopes)}
</table>

<h2>6 · Legal use &amp; non-conformance</h2>
<div class="callout {'bad' if conformity['status'] == 'flagged' else ('warn' if conformity['status'] == 'caution' else 'ok')}">{_esc(conformity['note'])}</div>
{f'''<table><tr><th>Land use code</th><th>Zone diff</th><th>Status</th></tr>{noncomp_rows}</table>''' if noncomp_rows else '<p class="small">No land-use non-compliance polygon overlap.</p>'}

<h2>7 · Risk &amp; constraints scorecard</h2>
<p>Overall: {_pill(risk['overall_status'], risk['overall_status'].upper())}</p>
<table>
  <tr><th>Constraint</th><th>Status</th><th>Detail</th><th>Source</th></tr>
  {risk_rows}
</table>

<h2>8 · Improvement &amp; permit history</h2>
<div class="callout {'bad' if permits['status'] == 'flagged' else ('warn' if permits['status'] == 'caution' else 'ok')}">{_esc(permits['note'])}</div>
<p class="small">
  Matched permits: <strong>{len(permits['rows'])}</strong>
  · Open / in progress: <strong>{permits['open_count']}</strong>
  · Declared value total: <strong>{_fmt_money(permits['total_value'])}</strong>
  · Lookback: <strong>{permits['lookback_years']} years</strong>
</p>
{permit_signals}
{f'''<table>
  <tr><th>Permit #</th><th>Type</th><th>Status</th><th>Applied</th><th>Approved</th><th>Est. value</th><th>Description</th></tr>
  {permit_rows}
</table>''' if permit_rows else '<p class="small">No parcel-matched permits in Gold data for this lookback window.</p>'}
<p class="small">Sources: {', '.join(_esc(s) for s in permits['sources'])}</p>

<h2>9 · Infrastructure &amp; capital projects near collateral</h2>
<div class="callout {'bad' if infra['status'] == 'flagged' else ('warn' if infra['status'] == 'caution' else 'ok')}">{_esc(infra['note'])}</div>
{infra_tokens_note}
{f'''<table>
  <tr><th>Project</th><th>Type</th><th>Status</th><th>Location</th><th>Est. cost</th><th>Schedule</th><th>Disruption</th></tr>
  {infra_rows}
</table>''' if infra_rows else '<p class="small">No active CIP projects matched streets near this address. See town-wide count in summary above.</p>'}
<p class="small">Sources: {', '.join(_esc(s) for s in infra['sources'])}</p>

<h2>10 · Property tax &amp; payment status</h2>
<div class="callout {'bad' if tax['status'] == 'flagged' else ('warn' if tax['status'] == 'caution' else 'ok')}">{_esc(tax['note'])}</div>
{f'<p class="small">Payment portal: <a href="{_esc(tax["portal_url"])}">{_esc(tax["portal_url"])}</a></p>' if tax.get('portal_url') else ''}
{f'''<table><tr><th>FY</th><th>Status</th><th>Balance due</th><th>Due date</th><th>Last payment</th><th>Bill type</th></tr>{tax_rows}</table>''' if tax_rows else ''}
<p class="small">Sources: {', '.join(_esc(s) for s in tax['sources'])}</p>

<h2>11 · Registry filings &amp; encumbrances</h2>
<div class="callout {'warn' if registry['active_liens'] else ('warn' if registry['status'] == 'caution' else 'ok')}">{_esc(registry['note'])}</div>
{f'<p class="small">Registry search: <a href="{_esc(registry["search_url"])}">{_esc(registry["search_url"])}</a></p>' if registry.get('search_url') else ''}
{f'''<table><tr><th>Instrument</th><th>Status</th><th>Recorded</th><th>Amount</th><th>Book/Page</th><th>Grantee</th></tr>{registry_rows}</table>''' if registry_rows else ''}
<p class="small">Sources: {', '.join(_esc(s) for s in registry['sources'])} — not a title report.</p>

<h2>12 · Code violations &amp; ISD / 311 orders</h2>
<div class="callout {'bad' if violations['status'] == 'flagged' else ('warn' if violations['open_count'] else 'ok')}">{_esc(violations['note'])}</div>
{f'<p class="small">ISD portal: <a href="{_esc(violations["isd_url"])}">{_esc(violations["isd_url"])}</a></p>' if violations.get('isd_url') else ''}
{f'''<table><tr><th>Source</th><th>Type</th><th>Status</th><th>Opened</th><th>Detail</th></tr>{violation_rows}</table>''' if violation_rows else '<p class="small">No matched violation rows.</p>'}
<p class="small">Sources: {', '.join(_esc(s) for s in violations['sources'])}</p>

<h2>13 · Comparable sales (assessor / CAMA, {comps['radius_mi']} mi)</h2>
<div class="callout {'warn' if not comps['rows'] else 'ok'}">{_esc(comps['note'])}</div>
{f'''<table>
  <tr><th>Address</th><th>Distance</th><th>Sale price</th><th>Sale date</th><th>Finished sf</th><th>$/sf</th></tr>
  {comp_rows}
</table>
<p class="small">Median comparable $/sf: <strong>{_fmt_money(comps['median_ppsf'])}</strong></p>''' if comp_rows else ''}
<p class="small">Sources: {', '.join(_esc(s) for s in comps['sources'])}</p>

<h2 class="page-break">14 · Collateral value &amp; market context</h2>
<p class="small">Indicative only — not an appraisal. Zip trends from market-trends; comps in §13 from CAMA transfers.</p>
<table class="facts">
  <tr><th>Total assessed value</th><td>{_fmt_money(assessed)}</td></tr>
  {avm_block}
  {market_rows}
</table>
{f'<p class="small">AVM method: {_esc(avm["method"])}</p>' if avm else ''}

<h2>15 · Data provenance &amp; limitations</h2>
<ul class="small">
  <li>Parcel geometry &amp; overlays: OverlayResolver on Gold parquets (parcel, zoning-overlay, environmental-overlay, macris, local-historic, noncompliance).</li>
  <li>Assessor fields: property.parquet / MassGIS L3 CAMA join (tax-assessor source).</li>
  <li>Zoning rules: zoning.parquet from town zoning bylaw JSON.</li>
  <li>Permits: permits.parquet — matched by parcel_id and address (ISD / OpenGov feed).</li>
  <li>Infrastructure: infra-projects.parquet — active CIP rows matched by street/corridor tokens.</li>
  <li>Property tax: live Invoice Cloud guest lookup (cached property-tax.parquet) or config fixtures.</li>
  <li>Registry: registry-records.parquet or lender_report.registry_records (Middlesex South).</li>
  <li>Violations: code-violation fixtures, 311.parquet, ISD portal records.</li>
  <li>Comps: spatial join property + parcel CAMA last-sale fields — not MLS.</li>
  <li>Market trends: market-trends.parquet (MLS zip aggregates where licensed).</li>
</ul>

<p class="disclaimer">
  TownEye Lender Due Diligence Pack — informational collateral memo only. Not a loan approval,
  flood certification, appraisal, or legal opinion. Verify all flags with the municipality,
  FEMA, and title company before closing. © towneye.ai
</p>
</div>
</body></html>"""
