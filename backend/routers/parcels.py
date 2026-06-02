"""Parcel resolution endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.utils.parcel_lookup import (
    ParcelNotFoundError,
    UnsupportedTownError,
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
