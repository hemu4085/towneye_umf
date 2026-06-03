"""Property Q&A — chatbot answers grounded in BriefData."""

from __future__ import annotations

from typing import Any

from backend.services.brief_context import brief_context_text
from backend.services.buildability import collect_brief_data
from backend.services.llm import answer_property_question
from reports.buildability_brief import BriefData


def _all_allowed_uses(data: BriefData) -> list[str]:
    uses: list[str] = []
    for rule in data.zoning_rules.values():
        for u in rule.allowed_uses or []:
            if u and u not in uses:
                uses.append(str(u))
    return uses


def _adu_answer(data: BriefData) -> str:
    uses = _all_allowed_uses(data)
    adu_hits = [u for u in uses if "ADU" in u.upper() or "ACCESSORY" in u.upper()]
    zones = ", ".join(h.code for h in data.base_zoning_hits + data.overlay_zoning_hits) or "—"
    if adu_hits:
        return (
            f"For **{data.parcel.address}** (zones: {zones}), accessory/ADU-type uses appear in "
            f"the permitted-use list for this parcel's zoning stack, including: "
            f"{', '.join(adu_hits[:6])}. "
            "That suggests an ADU may be allowed **by-right** or by special permit depending on "
            "the specific ADU type and Arlington's accessory dwelling rules — verify with the "
            "Building Department and a quick Title V review. "
            f"Buildability verdict: {data.headline_verdict_text}"
        )
    return (
        f"For **{data.parcel.address}** (zones: {zones}), ADU/accessory uses are **not clearly listed** "
        "in the permitted-use table TownEye has for this stack. That does not automatically prohibit "
        "an ADU — special permits, overlay districts, or state ADU law may still apply. "
        "Consult Arlington zoning staff. "
        f"Current verdict: {data.headline_verdict_text}"
    )


def _by_right_answer(data: BriefData) -> str:
    base = ", ".join(h.label for h in data.base_zoning_hits) or "—"
    overlays = ", ".join(h.label for h in data.overlay_zoning_hits) or "none"
    return (
        "**By-right** (sometimes written *by right*) means you may proceed with a use or structure "
        "that conforms to the zoning code **without** a special permit, variance, or zoning relief. "
        "If a proposed project (e.g. an addition or ADU) is not listed as allowed by-right, you "
        "typically need a special permit, variance, or other approval.\n\n"
        f"For this parcel ({data.parcel.address}), TownEye's stack is {base} "
        f"with overlays {overlays}. "
        f"Summary verdict: **{data.headline_verdict_text}**"
    )


def _fallback_answer(question: str, data: BriefData) -> str:
    q = question.lower()
    if "adu" in q or "accessory" in q or "in-law" in q or "in law" in q:
        return _adu_answer(data)
    if "by-right" in q or "by right" in q or "byright" in q:
        return _by_right_answer(data)
    if "far" in q or "floor area" in q:
        parts = [
            f"{e.label}: max FAR {e.max_far}, max GFA ~{e.max_gfa_sqft} sf"
            for e in data.envelopes[:3]
        ]
        return "Buildable envelope (indicative):\n" + ("\n".join(parts) or "See Full Property Report.")
    if "flood" in q or "wetland" in q or "historic" in q:
        rows = [f"• {w.label}: {w.status} — {w.detail}" for w in data.wraparound]
        return "Risk & constraint layers:\n" + ("\n".join(rows) or "No overlay hits in TownEye data.")
    if "zoning" in q or "zone" in q:
        base = ", ".join(h.label for h in data.base_zoning_hits) or "—"
        overlays = ", ".join(h.label for h in data.overlay_zoning_hits) or "none"
        return f"Zoning: base {base}; overlays {overlays}. {data.headline_verdict_text}"
    return (
        f"TownEye has assessor, zoning, and constraint data for **{data.parcel.address}**. "
        f"Verdict: {data.headline_verdict_text}. "
        "Try asking about ADU, by-right, FAR, flood, or historic overlays. "
        "For richer answers, configure ANTHROPIC_API_KEY on the API server."
    )


def ask_about_property(
    town_slug: str,
    parcel_id: str,
    question: str,
    *,
    prepared_for: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    data = collect_brief_data(town_slug, parcel_id, prepared_for)
    context = brief_context_text(data)
    answer = answer_property_question(question, context, history=history)
    if not answer:
        answer = _fallback_answer(question, data)
        source = "rules"
    else:
        source = "claude"
    return {
        "answer": answer,
        "source": source,
        "parcel_id": parcel_id,
        "address": data.parcel.address,
    }
