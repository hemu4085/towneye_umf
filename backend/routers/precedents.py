"""Precedent Search API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.config import get_settings
from backend.services.precedents import search_precedents

router = APIRouter(prefix="/api/precedents", tags=["precedents"])


@router.get("/search")
def precedents_search(
    town_slug: str = Query(..., min_length=3),
    q: str = Query("", max_length=200),
    board: Optional[str] = Query(None),
    relief: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    parcel_id: Optional[str] = Query(None),
    address: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=100),
):
    if town_slug not in get_settings().town_slugs:
        raise HTTPException(status_code=422, detail=f"Town '{town_slug}' is not supported.")
    return search_precedents(
        town_slug=town_slug,
        query=q,
        board=board,
        relief=relief,
        decision=decision,
        parcel_id=parcel_id,
        address=address,
        limit=limit,
    )
