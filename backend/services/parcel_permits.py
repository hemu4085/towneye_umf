"""Parcel-scoped building permits from Gold permits.parquet."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import pandas as pd
import yaml

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


@lru_cache(maxsize=16)
def _town_lender_cfg(town_slug: str) -> dict[str, Any]:
    cfg_path = get_settings().config_dir / town_slug / "config.yaml"
    if not cfg_path.is_file():
        return {}
    try:
        with cfg_path.open(encoding="utf-8") as fh:
            town_cfg = yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        return {}
    block = town_cfg.get("lender_report") or town_cfg.get("lender") or {}
    return block if isinstance(block, dict) else {}


def resolve_permit_external_link(
    *,
    town_slug: str,
    permit_number: Any = None,
    metadata: dict[str, Any] | None = None,
    address: str | None = None,
) -> dict[str, str | None]:
    """Resolve an OpenGov deep link only when a real record/location id exists.

    Arlington OpenGov ignores ``?q=`` and ``/search/locations?searchKey=`` hangs
    on a Turnstile-gated API (infinite Loading). Do not send users there.
    """
    md = metadata or {}
    lender = _town_lender_cfg(town_slug)
    portal = str(lender.get("permits_portal_url") or "").rstrip("/")
    record_tmpl = str(lender.get("permits_record_url_template") or "")
    location_tmpl = str(lender.get("permits_location_url_template") or "")

    street = str(md.get("address") or address or "").split(",")[0].strip() or None
    permit_txt = str(permit_number or "").strip() or None

    explicit = (
        md.get("detail_url")
        or md.get("source_url")
        or md.get("url")
        or md.get("permit_url")
    )
    # Reject known-broken search URLs if they somehow landed in metadata
    if explicit:
        url = str(explicit)
        if "/search" in url and ("searchKey=" in url or "?q=" in url):
            explicit = None
        else:
            return {
                "detail_url": url,
                "link_kind": "record",
                "link_label": "Open this permit in OpenGov",
                "search_hint": permit_txt or street,
            }

    record_id = (
        md.get("opengov_record_id")
        or md.get("record_id")
        or md.get("viewpoint_record_id")
    )
    if record_id and record_tmpl:
        return {
            "detail_url": record_tmpl.format(record_id=record_id),
            "link_kind": "record",
            "link_label": "Open this permit in OpenGov",
            "search_hint": permit_txt,
        }
    if record_id and portal:
        return {
            "detail_url": f"{portal}/records/{record_id}",
            "link_kind": "record",
            "link_label": "Open this permit in OpenGov",
            "search_hint": permit_txt,
        }

    location_id = md.get("opengov_location_id") or md.get("location_id")
    if location_id and location_tmpl:
        return {
            "detail_url": location_tmpl.format(location_id=location_id),
            "link_kind": "location",
            "link_label": "Open this property in OpenGov",
            "search_hint": street or permit_txt,
        }
    if location_id and portal:
        return {
            "detail_url": f"{portal}/locations/{location_id}",
            "link_kind": "location",
            "link_label": "Open this property in OpenGov",
            "search_hint": street or permit_txt,
        }

    # No deep link — OpenGov portal home does not accept paste of permit # / address.
    # Caller should surface ISD / Building Permit Activity links instead.
    hint_parts = [p for p in (permit_txt, street) if p]
    return {
        "detail_url": None,
        "link_kind": "manual",
        "link_label": None,
        "search_hint": " · ".join(hint_parts) if hint_parts else None,
    }


def town_permit_ledger_stats(town_slug: str) -> dict[str, Any]:
    df = _permits_frame(town_slug)
    if df.empty:
        return {"total": 0, "open": 0, "closed": 0}
    statuses = df["status"].astype(str).str.upper()
    open_n = int(statuses.isin(_OPEN_STATUSES).sum())
    return {
        "total": len(df),
        "open": open_n,
        "closed": int(len(df) - open_n),
    }


def _row_matches_parcel(md: dict[str, Any], parcel_id: str, address: str) -> bool:
    if str(md.get("parcel_id") or "") == str(parcel_id):
        return True
    addr = str(md.get("address") or "").upper()
    street = str(address or "").split(",")[0].upper().strip()
    if street and street in addr:
        return True
    return False


def get_parcel_permits(town_slug: str, parcel_id: str, address: str = "") -> list[dict[str, Any]]:
    df = _permits_frame(town_slug)
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        md = _parse_metadata(row.get("metadata"))
        if not _row_matches_parcel(md, parcel_id, address):
            continue
        status = str(row.get("status") or "").upper()
        permit_number = row.get("permit_number")
        link = resolve_permit_external_link(
            town_slug=town_slug,
            permit_number=permit_number,
            metadata=md,
            address=str(md.get("address") or address or "") or None,
        )
        rows.append({
            "permit_number": permit_number,
            "permit_type": row.get("permit_type"),
            "status": status,
            "is_open": status in _OPEN_STATUSES,
            "application_date": str(row.get("application_date") or "")[:10] or None,
            "approval_date": str(row.get("approval_date") or "")[:10] or None,
            "estimated_value": row.get("estimated_value"),
            "description": md.get("description"),
            "address": md.get("address"),
            "inspector": md.get("inspector"),
            "owner_name": md.get("owner_name") or md.get("applicant"),
            "work_type": md.get("work_type") or md.get("work_description"),
            "detail_url": link.get("detail_url"),
            "link_kind": link.get("link_kind"),
            "link_label": link.get("link_label"),
            "search_hint": link.get("search_hint"),
        })
    rows.sort(key=lambda r: r.get("application_date") or "", reverse=True)
    return rows


def summarize_parcel_permits(
    town_slug: str,
    parcel_id: str,
    address: str = "",
) -> dict[str, Any]:
    ledger = town_permit_ledger_stats(town_slug)
    permits = get_parcel_permits(town_slug, parcel_id, address)
    open_permits = [p for p in permits if p.get("is_open")]
    expired = [p for p in permits if p.get("status") == "EXPIRED"]
    lender = _town_lender_cfg(town_slug)
    return {
        "permits": permits,
        "open_count": len(open_permits),
        "expired_count": len(expired),
        "total_count": len(permits),
        "has_open": bool(open_permits),
        "has_expired": bool(expired),
        "ledger_total": ledger["total"],
        "ledger_open": ledger["open"],
        "permits_portal_url": lender.get("permits_portal_url") or "",
        "permits_activity_url": lender.get("permits_activity_url") or "",
        "isd_portal_url": lender.get("isd_portal_url") or "",
    }
