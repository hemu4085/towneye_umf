"""Parcel resolution endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.utils.parcel_lookup import (
    ParcelNotFoundError,
    UnsupportedTownError,
    _address_index_entries,
    _town_display_name,
    resolve_address,
    suggest_addresses,
)

router = APIRouter(prefix="/api/parcels", tags=["parcels"])


class ResolveRequest(BaseModel):
    address: str = Field(..., min_length=3)
    parcel_id: Optional[str] = None
    town_slug: Optional[str] = None


@router.get("/suggest")
def suggest_parcel_addresses(q: str = "", limit: int = 8):
    safe_limit = max(1, min(limit, 20))
    return {"suggestions": suggest_addresses(q, limit=safe_limit)}


@router.get("/address-index")
def get_address_index():
    """Compact street list for instant client-side autocomplete."""
    towns = []
    for slug in get_settings().town_slugs:
        entries = _address_index_entries(slug)
        towns.append(
            {
                "town_slug": slug,
                "town_name": _town_display_name(slug),
                "count": len(entries),
                "entries": [
                    {"address": addr, "parcel_id": pid} for addr, pid in entries
                ],
            },
        )
    return {"towns": towns}


@router.post("/resolve")
async def resolve_parcel(body: ResolveRequest):
    try:
        return await resolve_address(
            body.address,
            parcel_id=body.parcel_id,
            town_slug=body.town_slug,
        )
    except UnsupportedTownError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ParcelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dossier")
async def parcel_dossier(town_slug: str, parcel_id: str, address: str = ""):
    """Permit ledger + code violations for closing-risk drill-down."""
    if town_slug not in get_settings().town_slugs:
        raise HTTPException(status_code=422, detail=f"Town '{town_slug}' is not supported.")

    from backend.services.buildability import collect_brief_data
    from backend.services.lender_phase3 import _analyze_violations
    from backend.services.parcel_permits import summarize_parcel_permits
    from backend.utils.parcel_lookup import _load_town_config

    if not address.strip():
        try:
            data = collect_brief_data(town_slug, parcel_id, None)
            address = data.parcel.address or address
        except Exception:
            pass

    town_cfg: dict = {}
    try:
        town_cfg = _load_town_config(town_slug) or {}
    except Exception:
        town_cfg = {}

    permits = summarize_parcel_permits(town_slug, parcel_id, address)
    violations: dict = {
        "status": "clear",
        "note": "Violation detail unavailable.",
        "rows": [],
        "open_count": 0,
        "isd_url": "",
        "sources": [],
    }
    try:
        data = collect_brief_data(town_slug, parcel_id, None)
        violations = _analyze_violations(data, town_cfg)
    except Exception:
        pass

    lender_cfg = town_cfg.get("lender_report") or town_cfg.get("lender") or {}
    isd_url = (
        (violations.get("isd_url") if isinstance(violations, dict) else None)
        or lender_cfg.get("isd_portal_url")
        or ""
    )
    if isinstance(violations, dict) and not violations.get("isd_url"):
        violations["isd_url"] = isd_url

    permits_portal_url = (
        (permits.get("permits_portal_url") if isinstance(permits, dict) else None)
        or lender_cfg.get("permits_portal_url")
        or ""
    )
    permits_activity_url = (
        (permits.get("permits_activity_url") if isinstance(permits, dict) else None)
        or lender_cfg.get("permits_activity_url")
        or ""
    )

    # Do NOT invent OpenGov searchKey / ?q= / portal-home links — those hang or
    # do not accept paste lookup. Violation deep links only when Gold has IDs.

    return {
        "town_slug": town_slug,
        "parcel_id": parcel_id,
        "address": address,
        "permits": permits,
        "violations": violations,
        "isd_url": isd_url,
        "permits_portal_url": permits_portal_url,
        "permits_activity_url": permits_activity_url,
    }
