"""Address → parcel resolution for supported Massachusetts towns."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Optional

import httpx
import pandas as pd
import yaml

from backend.config import get_settings


def _normalize_address(addr: str) -> str:
    s = addr.upper().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    for token in (" MASSACHUSETTS", " MA ", " MA", " USA"):
        s = s.replace(token, "")
    return s.strip()


def _street_tokens(addr: str) -> set[str]:
    stop = {"ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "DR", "DRIVE", "LN", "LANE", "CT", "COURT"}
    return {t for t in _normalize_address(addr).split() if t not in stop and not t.isdigit()}


def _load_town_config(town_slug: str) -> dict[str, Any]:
    path = get_settings().config_dir / town_slug / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _town_display_name(town_slug: str) -> str:
    try:
        cfg = _load_town_config(town_slug)
        return str(cfg.get("town_name") or town_slug.split("-")[0].title())
    except OSError:
        return town_slug.split("-")[0].title()


@lru_cache(maxsize=1)
def _town_patterns(supported_key: tuple[str, ...]) -> tuple[tuple[re.Pattern[str], str], ...]:
    patterns: list[tuple[re.Pattern[str], str]] = []
    for slug in supported_key:
        name = _town_display_name(slug)
        patterns.append((re.compile(rf"\b{re.escape(name)}\b", re.I), slug))
    return tuple(patterns)


def _unsupported_town_message(supported: list[str]) -> str:
    names = [_town_display_name(slug) for slug in supported]
    if not names:
        return "TownEye has no supported towns configured yet."
    if len(names) == 1:
        return f"TownEye currently covers {names[0]}, MA. More towns coming soon."
    return f"TownEye currently covers {', '.join(names[:-1])} and {names[-1]}, MA. More towns coming soon."


def detect_town_slug(address: str, supported: list[str]) -> Optional[str]:
    for pattern, slug in _town_patterns(tuple(supported)):
        if pattern.search(address) and slug in supported:
            return slug
    return None


def _score_match(query: str, candidate: str) -> float:
    q, c = _normalize_address(query), _normalize_address(candidate or "")
    if not c:
        return 0.0
    if q in c or c in q:
        return 0.95
    q_tokens = _street_tokens(query)
    c_tokens = _street_tokens(candidate)
    if q_tokens and q_tokens <= c_tokens:
        return 0.9
    return SequenceMatcher(None, q, c).ratio()


def _lookup_parquet(town_slug: str, address: str) -> Optional[dict[str, Any]]:
    path = get_settings().gold_data_path / town_slug / "parcel.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.empty or "address" not in df.columns:
        return None

    best_row = None
    best_score = 0.0
    for _, row in df.iterrows():
        score = _score_match(address, str(row.get("address") or ""))
        if score > best_score:
            best_score = score
            best_row = row
    if best_row is None or best_score < 0.55:
        return None

    md = best_row.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except json.JSONDecodeError:
            md = {}

    return {
        "parcel_id": str(best_row["parcel_id"]),
        "town_slug": town_slug,
        "address": str(best_row.get("address") or address),
        "lat": float(best_row["centroid_lat"]),
        "lng": float(best_row["centroid_lon"]),
        "area_sqft": float(best_row["area_sqft"]) if pd.notna(best_row.get("area_sqft")) else None,
        "match_score": best_score,
        "source": "gold_parquet",
        "metadata": md,
    }


def _gis_address_field_candidates(config: dict[str, Any]) -> list[str]:
    parcels = config.get("parcels") or {}
    return list(parcels.get("address_field_candidates") or ["SITE_ADDR", "FULL_STR", "ADDRESS"])


async def _lookup_gis(town_slug: str, address: str) -> Optional[dict[str, Any]]:
    config = _load_town_config(town_slug)
    parcels_cfg = config.get("parcels") or {}
    base_url = (config.get("scraper_urls") or {}).get("parcels_arcgis_url")
    if not base_url:
        return None

    layer_url = f"{base_url.rstrip('/')}/0/query"
    street_part = re.split(r",\s*", address, maxsplit=1)[0].strip().replace("'", "''")
    where_parts = [f"UPPER(SITE_ADDR) LIKE '%{street_part.upper()}%'"]
    where_clause = parcels_cfg.get("where_clause")
    if where_clause:
        where_parts.append(where_clause)
    where = " AND ".join(where_parts)

    params = {
        "where": where,
        "outFields": "MAP_PAR_ID,SITE_ADDR,LOC_ID",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": 5,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(layer_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features") or []
    if not features:
        return None

    best = None
    best_score = 0.0
    for feat in features:
        attrs = feat.get("attributes") or {}
        addr_val = ""
        for field in _gis_address_field_candidates(config):
            if attrs.get(field):
                addr_val = str(attrs[field])
                break
        score = _score_match(address, addr_val)
        if score > best_score:
            best_score = score
            geom = feat.get("geometry") or {}
            best = {
                "parcel_id": str(attrs.get("MAP_PAR_ID") or attrs.get("LOC_ID") or ""),
                "town_slug": town_slug,
                "address": addr_val or address,
                "lat": float((geom.get("rings") or [[[]]])[0][0][1]) if geom.get("rings") else 0.0,
                "lng": float((geom.get("rings") or [[[]]])[0][0][0]) if geom.get("rings") else 0.0,
                "match_score": score,
                "source": "arcgis",
                "metadata": attrs,
            }
    if best and best_score >= 0.5 and best["parcel_id"]:
        return best
    return None


def _assessor_snapshot(town_slug: str, parcel_id: str) -> dict[str, Any]:
    from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator

    gen = BuildabilityBriefGenerator(town_slug=town_slug, data_dir=get_settings().gold_data_path)
    data = gen.collect_data(BriefInputs(town_slug=town_slug, parcel_id=parcel_id))
    p = data.parcel
    prop = data.property_info
    snapshot: dict[str, Any] = {
        "address": p.address,
        "parcel_id": p.parcel_id,
        "lot_size_sqft": p.area_sqft,
        "year_built": prop.year_built if prop else None,
        "owner": prop.owner_name if prop else None,
        "assessed_value": prop.assessed_value if prop else None,
        "current_use": prop.luc_description or prop.luc if prop else None,
        "zoning_base": data.primary_zone_code,
        "zoning_overlay": data.primary_overlay_code,
        "verdict": data.headline_verdict_text,
    }
    return snapshot


class ParcelNotFoundError(Exception):
    pass


class UnsupportedTownError(Exception):
    pass


async def resolve_address(address: str) -> dict[str, Any]:
    settings = get_settings()
    town_slug = detect_town_slug(address, settings.town_slugs)
    if not town_slug:
        raise UnsupportedTownError(_unsupported_town_message(settings.town_slugs))

    hit = _lookup_parquet(town_slug, address)
    if hit is None:
        hit = await _lookup_gis(town_slug, address)
    if hit is None:
        raise ParcelNotFoundError(
            f"No parcel found for that address in {town_slug.replace('-', ' ').title()}.",
        )

    hit["assessor_snapshot"] = _assessor_snapshot(town_slug, hit["parcel_id"])
    hit["town_name"] = _town_display_name(town_slug)
    return hit


@lru_cache(maxsize=32)
def _town_address_index(town_slug: str) -> tuple[tuple[str, str], ...]:
    path = get_settings().gold_data_path / town_slug / "parcel.parquet"
    if not path.exists():
        return ()
    df = pd.read_parquet(path, columns=["address", "parcel_id"])
    if df.empty or "address" not in df.columns:
        return ()
    rows: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        addr = str(row.get("address") or "").strip()
        parcel_id = str(row.get("parcel_id") or "").strip()
        if addr and parcel_id:
            rows.append((addr, parcel_id))
    return tuple(rows)


def _format_suggestion_address(street: str, town_name: str) -> str:
    street_clean = street.strip().rstrip(",")
    if re.search(rf"\b{re.escape(town_name)}\b", street_clean, re.I):
        if re.search(r"\bMA\b", street_clean, re.I):
            return street_clean
        return f"{street_clean}, MA"
    return f"{street_clean}, {town_name} MA"


def suggest_addresses(query: str, limit: int = 8) -> list[dict[str, Any]]:
    q = query.strip()
    if len(q) < 3:
        return []

    settings = get_settings()
    town_slug = detect_town_slug(q, settings.town_slugs)
    search_slugs = [town_slug] if town_slug else settings.town_slugs

    norm_q = _normalize_address(q)
    q_tokens = _street_tokens(q)
    hits: list[tuple[float, str, str, str, str]] = []

    for slug in search_slugs:
        town_name = _town_display_name(slug)
        for street, parcel_id in _town_address_index(slug):
            norm_addr = _normalize_address(street)
            score = _score_match(q, street)
            if q_tokens and q_tokens <= _street_tokens(street):
                score = max(score, 0.92)
            if norm_q and norm_q in norm_addr:
                score = max(score, 0.88)
            if score < 0.45:
                continue
            label = _format_suggestion_address(street, town_name)
            hits.append((score, label.lower(), label, slug, parcel_id))

    hits.sort(key=lambda item: (-item[0], item[1]))
    seen: set[str] = set()
    suggestions: list[dict[str, Any]] = []
    for score, _, label, slug, parcel_id in hits:
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(
            {
                "address": label,
                "town_slug": slug,
                "town_name": _town_display_name(slug),
                "parcel_id": parcel_id,
                "score": round(score, 3),
            },
        )
        if len(suggestions) >= limit:
            break
    return suggestions
