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
