"""Anthropic Claude Sonnet 4 for portal report synthesis."""

from __future__ import annotations

import json
from typing import Any

from backend.config import get_settings


def _client():
    from anthropic import Anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return Anthropic(api_key=settings.anthropic_api_key)


def generate_json_report(system: str, user_prompt: str) -> dict[str, Any]:
    """Call Claude Sonnet 4; return parsed JSON or structured fallback."""
    client = _client()
    if client is None:
        return {"error": "ANTHROPIC_API_KEY not configured", "fallback": True}

    settings = get_settings()
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=system + "\nRespond with valid JSON only, no markdown fences.",
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def answer_property_question(
    question: str,
    property_context: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    """Return plain-text answer grounded in property context, or None if LLM unavailable."""
    client = _client()
    if client is None:
        return None

    settings = get_settings()
    system = (
        "You are TownEye, a Massachusetts property intelligence assistant. "
        "Answer ONLY using the PROPERTY CONTEXT below. If the context does not contain "
        "enough information, say what is known and what the homeowner should verify with "
        "the town building/zoning department. Use clear, friendly language. "
        "For zoning terms (by-right, special permit, ADU, FAR), explain briefly then "
        "apply them to this parcel. Do not invent MLS listings or Zestimates.\n\n"
        f"PROPERTY CONTEXT:\n{property_context}"
    )
    messages: list[dict[str, str]] = []
    for turn in history or []:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question.strip()})

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1200,
        system=system,
        messages=messages,
    )
    return message.content[0].text.strip()
