"""Parcel-scoped building permits from Gold permits.parquet."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.config import get_settings

_OPEN_STATUSES = frozenset({"SUBMITTED", "UNDER_REVIEW", "APPROVED", "INSPECTIONS"})
_CLOSED_STATUSES = frozenset({"CLOSED", "EXPIRED", "REVOKED"})


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


@lru_cache(maxsize=8)
def _permits_frame(town_slug: str) -> pd.DataFrame:
    path = get_settings().gold_data_path / town_slug / "permits.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


def get_parcel_permits(town_slug: str, parcel_id: str) -> list[dict[str, Any]]:
    df = _permits_frame(town_slug)
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        md = _parse_metadata(row.get("metadata"))
        if str(md.get("parcel_id") or "") != str(parcel_id):
            continue
        status = str(row.get("status") or "").upper()
        rows.append({
            "permit_number": row.get("permit_number"),
            "permit_type": row.get("permit_type"),
            "status": status,
            "is_open": status in _OPEN_STATUSES,
            "application_date": str(row.get("application_date") or "")[:10] or None,
            "approval_date": str(row.get("approval_date") or "")[:10] or None,
            "estimated_value": row.get("estimated_value"),
            "description": md.get("description"),
            "address": md.get("address"),
            "inspector": md.get("inspector"),
        })
    rows.sort(key=lambda r: r.get("application_date") or "", reverse=True)
    return rows


def summarize_parcel_permits(town_slug: str, parcel_id: str) -> dict[str, Any]:
    permits = get_parcel_permits(town_slug, parcel_id)
    open_permits = [p for p in permits if p.get("is_open")]
    expired = [p for p in permits if p.get("status") == "EXPIRED"]
    return {
        "permits": permits,
        "open_count": len(open_permits),
        "expired_count": len(expired),
        "total_count": len(permits),
        "has_open": bool(open_permits),
        "has_expired": bool(expired),
    }
