"""Check which portal reports can be generated for a parcel."""

from __future__ import annotations

from typing import Any

import pandas as pd

from backend.config import get_settings

LLM_REPORTS = frozenset({"market", "proforma", "neighborhood"})
BRIEF_REPORTS = frozenset({"buildability", "zoning", "risk", "lender"})
ALL_REPORTS = BRIEF_REPORTS | LLM_REPORTS


def _parquet_has_parcel_id(path, parcel_id: str) -> bool:
    if not path.is_file():
        return False
    try:
        df = pd.read_parquet(
            path,
            columns=["parcel_id"],
            filters=[("parcel_id", "==", parcel_id)],
        )
        return not df.empty
    except Exception:
        df = pd.read_parquet(path, columns=["parcel_id"])
        return parcel_id in set(df["parcel_id"].astype(str))


def _brief_data_available(town_slug: str, parcel_id: str) -> tuple[bool, str]:
    """Fast check without loading overlay geometry (Render free-tier memory)."""
    gold = get_settings().gold_data_path
    parcel_path = gold / town_slug / "parcel.parquet"
    property_path = gold / town_slug / "property.parquet"
    if not parcel_path.is_file():
        return False, "Parcel layer is not available for this town."
    if not property_path.is_file():
        return False, "Assessor layer is not available for this town."
    try:
        if not _parquet_has_parcel_id(parcel_path, parcel_id):
            return False, "Parcel not found in town GIS layer."
        if not _parquet_has_parcel_id(property_path, parcel_id):
            return False, "Assessor record not found for this parcel."
    except Exception as exc:
        return False, str(exc) or "Required parcel data is not available."
    return True, ""


def get_report_availability(town_slug: str, parcel_id: str) -> dict[str, dict[str, Any]]:
    brief_ok, brief_reason = _brief_data_available(town_slug, parcel_id)
    has_llm = bool(get_settings().anthropic_api_key.strip())
    llm_reason = "AI synthesis is not configured for this report."

    reports: dict[str, dict[str, Any]] = {}
    for report_type in sorted(ALL_REPORTS):
        if report_type in LLM_REPORTS:
            available = brief_ok and has_llm
            reason = brief_reason if not brief_ok else (llm_reason if not has_llm else "")
        else:
            available = brief_ok
            reason = brief_reason if not brief_ok else ""
        reports[report_type] = {"available": available, "reason": reason}
    return reports
