# [FILE PATH]: core/llm_client.py
# Patch #179
# Execution Mode: Shared Multi-Provider LLM Client
# Date: 2026-03-03
"""
TownEye UMF — Shared LLM Client
================================
Single dispatch point for all LLM calls across the UMF:

  * OpenAI   (GPT-4o-mini, GPT-4o, …)  — ``OPENAI_API_KEY``
  * Anthropic (Claude Haiku/Sonnet, …)  — ``ANTHROPIC_API_KEY``
  * Google    (Gemini 2.5 Flash/Pro, …) — ``GEMINI_API_KEY``

Provider auto-selection order (when ``provider=None``):
  GEMINI_API_KEY  →  gemini
  OPENAI_API_KEY  →  openai
  ANTHROPIC_API_KEY → anthropic

Zero-Hardcoding contract
------------------------
* No model name, API endpoint, or town-specific string is hardcoded here.
* Default model names are module-level constants; every caller can
  override them via the ``model`` argument or the ``TOWNEYE_LLM_MODEL``
  environment variable.
* API keys are read exclusively from environment variables.

Usage
-----
  from core.llm_client import call_llm, select_provider

  # Auto-detect provider from env:
  text = call_llm(system="You are ...", user="Suggest ...", n_tokens=2048)

  # Explicit provider + model:
  text = call_llm(
      system="...", user="...",
      provider="gemini", model="gemini-2.5-flash",
  )
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model identifiers (overridable via TOWNEYE_LLM_MODEL env var)
# ---------------------------------------------------------------------------
_DEFAULT_OPENAI_MODEL    = "gpt-4o-mini"
_DEFAULT_ANTHROPIC_MODEL = "claude-3-5-haiku-20250219"
_DEFAULT_GEMINI_MODEL    = "gemini-2.5-flash"

_LLM_TEMPERATURE = 0.2
_LLM_MAX_TOKENS  = 2048

# ---------------------------------------------------------------------------
# Provider auto-detection
# ---------------------------------------------------------------------------

def select_provider() -> str:
    """
    Return the best available LLM provider based on set environment variables.

    Priority: ``gemini`` > ``openai`` > ``anthropic``.
    Raises ``RuntimeError`` if no key is found.
    """
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "llm_client | No LLM API key found in environment. "
        "Set one of: GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.\n"
        "  export GEMINI_API_KEY=AIza..."
    )


def _default_model(provider: str) -> str:
    """Return the default model name for *provider*."""
    if provider == "gemini":
        return _DEFAULT_GEMINI_MODEL
    if provider == "anthropic":
        return _DEFAULT_ANTHROPIC_MODEL
    return _DEFAULT_OPENAI_MODEL


# ---------------------------------------------------------------------------
# Provider-specific call functions
# ---------------------------------------------------------------------------

def _call_openai(system: str, user: str, model: str, n_tokens: int) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "llm_client | OPENAI_API_KEY is not set. "
            "Export it before running:\n  export OPENAI_API_KEY=sk-..."
        )
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "llm_client | 'openai' package not installed. "
            "Run: pip install openai>=1.0"
        ) from exc

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=_LLM_TEMPERATURE,
        max_tokens=n_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(system: str, user: str, model: str, n_tokens: int) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "llm_client | ANTHROPIC_API_KEY is not set. "
            "Export it before running:\n  export ANTHROPIC_API_KEY=sk-ant-..."
        )
    try:
        import anthropic  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "llm_client | 'anthropic' package not installed. "
            "Run: pip install anthropic>=0.25"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=n_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text.strip()


def _call_gemini(system: str, user: str, model: str, n_tokens: int) -> str:
    """
    Call the Google Gemini API via the ``google-genai`` SDK.

    The system instruction and user prompt are passed separately so the model
    receives proper role separation.  Temperature is set via
    ``GenerateContentConfig`` to match the determinism level used by the
    OpenAI and Anthropic callers.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "llm_client | GEMINI_API_KEY is not set. "
            "Export it before running:\n  export GEMINI_API_KEY=AIza..."
        )
    try:
        from google import genai                          # type: ignore[import]
        from google.genai import types as genai_types    # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "llm_client | 'google-genai' package not installed. "
            "Run: pip install google-genai>=1.0"
        ) from exc

    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(
        system_instruction=system,
        temperature=_LLM_TEMPERATURE,
        max_output_tokens=n_tokens,
    )
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=config,
    )
    return response.text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_llm(
    system: str,
    user: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    n_tokens: int = _LLM_MAX_TOKENS,
) -> str:
    """
    Dispatch an LLM call to the best available provider.

    Parameters
    ----------
    system : str
        System / instruction prompt (role: system).
    user : str
        User / query prompt (role: user).
    provider : str, optional
        ``"gemini"``, ``"openai"``, or ``"anthropic"``.
        Auto-detected from environment variables when omitted.
    model : str, optional
        Model identifier override.  Falls back to ``TOWNEYE_LLM_MODEL``
        env var, then the per-provider default.
    n_tokens : int
        Maximum output tokens (default: 2048).

    Returns
    -------
    str
        The raw text response from the LLM.

    Raises
    ------
    RuntimeError
        If no API key is found, or the required package is not installed.
    ValueError
        Propagated from caller if the response cannot be parsed.
    """
    effective_provider = provider or select_provider()
    effective_model = (
        model
        or os.environ.get("TOWNEYE_LLM_MODEL", "")
        or _default_model(effective_provider)
    )

    logger.info(
        "llm_client | provider=%s  model=%s  max_tokens=%d",
        effective_provider, effective_model, n_tokens,
    )

    if effective_provider == "gemini":
        return _call_gemini(system, user, effective_model, n_tokens)
    if effective_provider == "anthropic":
        return _call_anthropic(system, user, effective_model, n_tokens)
    return _call_openai(system, user, effective_model, n_tokens)
