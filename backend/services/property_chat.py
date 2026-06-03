"""Property Q&A — chatbot answers grounded in BriefData."""

from __future__ import annotations

import re
from typing import Any

from backend.services.brief_context import brief_context_text
from backend.services.buildability import collect_brief_data
from backend.services.llm import answer_property_question
from reports.buildability_brief import BriefData


def _zones_label(data: BriefData) -> str:
    base = ", ".join(h.code for h in data.base_zoning_hits) or "—"
    overlays = ", ".join(h.code for h in data.overlay_zoning_hits)
    if overlays:
        return f"{base} + {overlays}"
    return base


def _all_allowed_uses(data: BriefData) -> list[str]:
    uses: list[str] = []
    for rule in data.zoning_rules.values():
        for u in rule.allowed_uses or []:
            if u and u not in uses:
                uses.append(str(u))
    return uses


def _uses_matching(uses: list[str], *keywords: str) -> list[str]:
    hits: list[str] = []
    for u in uses:
        upper = u.upper()
        if any(k in upper for k in keywords):
            hits.append(u)
    return hits


def _zoning_verdict_answer(data: BriefData) -> str:
    base = ", ".join(h.label for h in data.base_zoning_hits) or "—"
    overlays = ", ".join(h.label for h in data.overlay_zoning_hits) or "none"
    env_lines = [
        f"• {e.label}: up to ~{e.max_gfa_sqft:,} sf GFA (FAR {e.max_far})"
        for e in data.envelopes[:3]
        if e.max_gfa_sqft
    ]
    env_block = "\n".join(env_lines) if env_lines else "• See Buildability Brief for envelope detail."
    return (
        f"**Zoning verdict — {data.parcel.address}**\n\n"
        f"{data.headline_verdict_text}\n\n"
        f"Districts: {base}"
        + (f" with overlays {overlays}" if overlays != "none" else "")
        + f" (codes {_zones_label(data)}).\n\n"
        f"Indicative buildable area:\n{env_block}\n\n"
        "This is TownEye's planning read from GIS + zoning tables — confirm permits with Arlington "
        "Building & Zoning before construction."
    )


def _adu_answer(data: BriefData) -> str:
    uses = _all_allowed_uses(data)
    adu_hits = _uses_matching(uses, "ADU", "ACCESSORY", "IN-LAW", "IN LAW")
    zones = _zones_label(data)
    if adu_hits:
        return (
            f"For **{data.parcel.address}** (zones {zones}), accessory/ADU-type uses appear in "
            f"the permitted-use list, including: {', '.join(adu_hits[:8])}. "
            "That supports ADU feasibility **by-right or by special permit**, depending on the "
            "specific unit type and Arlington accessory-dwelling bylaws — verify with the Building "
            f"Department. Overall verdict: {data.headline_verdict_text}"
        )
    return (
        f"For **{data.parcel.address}** (zones {zones}), ADU/accessory uses are **not clearly listed** "
        "in TownEye's permitted-use table for this stack. That does not automatically prohibit an "
        "ADU — state ADU law, special permits, or overlay rules may still apply. "
        f"Current verdict: {data.headline_verdict_text}. "
        "Consult Arlington zoning staff before design."
    )


def _by_right_answer(data: BriefData) -> str:
    base = ", ".join(h.label for h in data.base_zoning_hits) or "—"
    overlays = ", ".join(h.label for h in data.overlay_zoning_hits) or "none"
    return (
        "**By-right** means a conforming use or structure may proceed **without** a special permit, "
        "variance, or zoning relief. Non-by-right projects typically need special permit, variance, "
        "or other approval.\n\n"
        f"For **{data.parcel.address}**, TownEye's stack is **{base}**"
        + (f" with overlays **{overlays}**" if overlays != "none" else "")
        + f". Summary verdict: **{data.headline_verdict_text}**"
    )


def _garage_answer(data: BriefData) -> str:
    uses = _all_allowed_uses(data)
    hits = _uses_matching(
        uses,
        "GARAGE",
        "PARKING",
        "CARPORT",
        "ACCESSORY BUILDING",
        "ACCESSORY STRUCTURE",
        "STORAGE",
    )
    zones = _zones_label(data)
    if hits:
        return (
            f"For **{data.parcel.address}** (zones {zones}), TownEye's permitted-use list includes "
            f"garage/parking-related uses such as: **{', '.join(hits[:8])}**. "
            "A new or expanded garage is often feasible if it meets setback, height, lot coverage, "
            "and access rules for your district — the Building Department will confirm whether your "
            f"design is **by-right** or needs a permit. Overall verdict: {data.headline_verdict_text}"
        )
    return (
        f"For **{data.parcel.address}** (zones {zones}), **garage** is not spelled out in the "
        "permitted-use rows TownEye has for this parcel. Many Arlington projects still add garages "
        "via accessory-structure or parking provisions, or through special permit — "
        f"your headline verdict is: {data.headline_verdict_text}. "
        "Bring a sketch plan to Building & Zoning for a definitive answer."
    )


def _addition_answer(data: BriefData) -> str:
    uses = _all_allowed_uses(data)
    hits = _uses_matching(
        uses,
        "SINGLE FAMILY",
        "DWELLING",
        "RESIDENTIAL",
        "ADDITION",
        "RENOVATION",
        "IMPROVEMENT",
    )
    env = data.envelopes[0] if data.envelopes else None
    gfa_hint = (
        f"TownEye estimates up to ~{env.max_gfa_sqft:,} sf max GFA (FAR {env.max_far}) on this lot."
        if env and env.max_gfa_sqft
        else "Generate the Buildability Brief for max GFA on this lot."
    )
    use_hint = (
        f"Permitted residential uses include: {', '.join(hits[:6])}."
        if hits
        else "Residential use is implied for this single-family parcel."
    )
    return (
        f"For **{data.parcel.address}** ({_zones_label(data)}), an addition or expansion generally "
        f"must stay within zoning envelope and district rules. {use_hint} {gfa_hint} "
        f"Overall verdict: {data.headline_verdict_text}. "
        "Setbacks, height, and lot coverage still apply — verify with Arlington before drawings."
    )


def _constraints_answer(data: BriefData) -> str:
    rows = [f"• **{w.label}**: {w.status} — {w.detail}" for w in data.wraparound]
    body = "\n".join(rows) if rows else "• No flood, wetland, or historic flags in TownEye overlay data."
    return (
        f"**Risk & constraints — {data.parcel.address}**\n\n{body}\n\n"
        f"Planning verdict: {data.headline_verdict_text}"
    )


def _contextual_answer(question: str, data: BriefData) -> str:
    """Best-effort answer using parcel zoning facts when the question is open-ended."""
    uses = _all_allowed_uses(data)
    use_sample = ", ".join(uses[:10]) if uses else "see town zoning tables"
    constraints = [w.label for w in data.wraparound if w.status and "clear" not in w.status.lower()]
    constraint_line = (
        f"Active constraint layers: {', '.join(constraints)}."
        if constraints
        else "No major constraint overlays flagged in TownEye data."
    )
    return (
        f"For **{data.parcel.address}** ({_zones_label(data)}):\n\n"
        f"**Verdict:** {data.headline_verdict_text}\n\n"
        f"Sample permitted uses in TownEye's stack: {use_sample}.\n"
        f"{constraint_line}\n\n"
        f"Your question was: “{question.strip()}”. TownEye does not replace a zoning attorney — "
        "for project-specific yes/no (garage, addition, ADU, deck), ask about that item directly "
        "or generate the **Buildability Brief** for full envelope and use tables."
    )


def _fallback_answer(question: str, data: BriefData) -> str:
    q = question.lower()
    if "verdict" in q or "zoning verdict" in q:
        return _zoning_verdict_answer(data)
    if "adu" in q or "accessory" in q or "in-law" in q or "in law" in q:
        return _adu_answer(data)
    if "by-right" in q or "by right" in q or "byright" in q:
        return _by_right_answer(data)
    if "garage" in q or "carport" in q or "parking structure" in q:
        return _garage_answer(data)
    if any(
        w in q
        for w in (
            "addition",
            "add on",
            "expand",
            "extension",
            "second story",
            "2nd story",
            "basement",
            "remodel",
            "renovation",
        )
    ):
        return _addition_answer(data)
    if "deck" in q or "porch" in q or "shed" in q or "pool" in q:
        return _garage_answer(data) if "shed" in q or "garage" in q else _addition_answer(data)
    if "far" in q or "floor area" in q or "square feet" in q or "sq ft" in q:
        parts = [
            f"• {e.label}: max FAR {e.max_far}, ~{e.max_gfa_sqft:,} sf GFA"
            for e in data.envelopes[:3]
            if e.max_gfa_sqft
        ]
        return (
            f"**Buildable envelope — {data.parcel.address}**\n\n"
            + ("\n".join(parts) or "Envelope data unavailable — open Buildability Brief.")
            + f"\n\nVerdict: {data.headline_verdict_text}"
        )
    if "flood" in q or "wetland" in q or "historic" in q or "constraint" in q:
        return _constraints_answer(data)
    if "zoning" in q or re.search(r"\bzone\b", q):
        return _zoning_verdict_answer(data)
    return _contextual_answer(question, data)


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
