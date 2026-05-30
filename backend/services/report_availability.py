"""Check which portal reports can be generated for a parcel."""

from __future__ import annotations

from typing import Any

from backend.config import get_settings
from backend.services.buildability import collect_brief_data

LLM_REPORTS = frozenset({"market", "proforma", "neighborhood"})
BRIEF_REPORTS = frozenset({"buildability", "zoning", "risk", "lender"})
ALL_REPORTS = BRIEF_REPORTS | LLM_REPORTS


def get_report_availability(town_slug: str, parcel_id: str) -> dict[str, dict[str, Any]]:
    brief_ok = False
    brief_reason = ""

    try:
        collect_brief_data(town_slug, parcel_id)
        brief_ok = True
    except Exception as exc:
        brief_reason = str(exc) or "Required parcel data is not available."

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
