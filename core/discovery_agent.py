# [FILE PATH]: core/discovery_agent.py
# Patch #183
# Execution Mode: URL Discovery Agent — LLM + Web Search
# Date: 2026-03-03
"""
DiscoveryAgent
==============
Autonomously discovers the real official data URLs for any onboarded
municipality and injects them into its ``configs/{town_slug}/config.yaml``,
replacing ``PLACEHOLDER`` strings left by the Expansion Engine.

Architecture
------------
For each URL slot that still contains ``PLACEHOLDER``:

  1. **Tavily search** (``TAVILY_API_KEY`` required) — queries the web for
     the official municipal URL (e.g. "Waltham MA property assessor URL").
  2. **LLM validation** — the raw Tavily results are passed to a Gemini /
     OpenAI / Anthropic model, which selects the single best candidate URL
     and explains its choice.
  3. **YAML injection** — the confirmed URL is written back into the
     ``configs/{town_slug}/config.yaml`` file in-place.

If Tavily is not available (no ``TAVILY_API_KEY`` or package not installed),
the agent falls back to an **LLM-only** path: the model is asked to recall
the URL from its training knowledge.  This path is clearly logged so the
operator can later swap in real search results.

Zero-Hardcoding contract
------------------------
* The set of URL slots to discover and their search-query templates are
  defined in the ``URL_DISCOVERY_TARGETS`` constant at the bottom of this
  module.  No town name or URL appears in logic code.
* All config reads/writes go through ``configs/{town_slug}/config.yaml``.
* The agent is fully injectable: ``LLM provider``, ``Tavily client``, and
  ``config_base_dir`` are constructor parameters.

Usage
-----
    # Discover URLs for one town (uses env-var API keys):
    python core/discovery_agent.py --town waltham-ma

    # Dry-run — print proposed replacements without writing:
    python core/discovery_agent.py --town waltham-ma --dry-run

    # Use a specific LLM provider:
    python core/discovery_agent.py --town waltham-ma --provider openai

Environment variables
---------------------
``TAVILY_API_KEY``          — Tavily web-search API key (optional but recommended)
``GEMINI_API_KEY``          — Gemini LLM key
``OPENAI_API_KEY``          — OpenAI LLM key
``ANTHROPIC_API_KEY``       — Anthropic LLM key
``TOWNEYE_LLM_MODEL``       — Override default LLM model
"""

import argparse
import json
import logging
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import yaml

from core.config_loader import ConfigLoader
from core.llm_client import call_llm, select_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL discovery targets
# Each entry maps a config key-path (dot-separated) to a search-query
# template.  {town_name}, {state}, {town_slug} are substituted at runtime.
# Only slots whose current value contains "PLACEHOLDER" are processed.
# ---------------------------------------------------------------------------
URL_DISCOVERY_TARGETS: List[Dict[str, str]] = [
    {
        "config_key":   "scraper_urls.property_assessor",
        "search_query": "{town_name} {state} property assessor portal search URL site:.gov OR site:.us",
        "llm_hint":     (
            "Return the URL of the public property search page for the "
            "{town_name}, {state} assessor's office (often Patriot Properties, "
            "CAMA, or a .gov portal). Include the full https:// URL."
        ),
    },
    {
        "config_key":   "scraper_urls.school_calendar_ics",
        "search_query": "{town_name} {state} school district calendar ICS iCal download URL",
        "llm_hint":     (
            "Return the direct .ics iCalendar URL for {town_name}, {state} "
            "public schools academic calendar. Include the full https:// URL."
        ),
    },
    {
        "config_key":   "scraper_urls.zoning_bylaws_json",
        "search_query": "{town_name} {state} zoning bylaws JSON GIS open data URL site:.gov OR site:.us",
        "llm_hint":     (
            "Return the URL of a JSON or GeoJSON endpoint for zoning data in "
            "{town_name}, {state}. This might be an ArcGIS FeatureServer, "
            "OpenData portal, or town GIS site. Include the full https:// URL."
        ),
    },
    {
        "config_key":   "scraper_urls.dpw_capital_plans_pdf",
        "search_query": "{town_name} {state} DPW capital improvement plan PDF budget site:.gov OR site:.us",
        "llm_hint":     (
            "Return the URL of the most recent Capital Improvement Plan (CIP) "
            "PDF for {town_name}, {state}. Include the full https:// URL."
        ),
    },
    {
        "config_key":   "scraper_urls.permits_api",
        "search_query": "{town_name} {state} building permits open data API JSON URL site:.gov OR site:.us",
        "llm_hint":     (
            "Return the URL of the building/construction permits API or open-data "
            "endpoint for {town_name}, {state} (often OpenGov, Accela, or "
            "ViewPoint ISD). Include the full https:// URL."
        ),
    },
]

# Prompt templates — no town values live here
_SYSTEM_PROMPT_URL = (
    "You are a municipal open-data researcher for TownEye, a civic-intelligence platform.\n\n"
    "Your task: given web-search results or your own knowledge, identify the single best "
    "official URL for the requested data source for the specified municipality.\n\n"
    "Rules:\n"
    "- Prefer official government (.gov, .us, .org/city) domains over third-party aggregators.\n"
    "- If web-search results are provided, choose the most relevant result URL.\n"
    "- If no reliable URL is found, return exactly: UNKNOWN\n\n"
    "Return ONLY the URL string (or UNKNOWN). No explanation, no markdown."
)

_USER_PROMPT_SEARCH = (
    "Municipality: {town_name}, {state}\n\n"
    "Task: {llm_hint}\n\n"
    "Web search results (top candidates):\n"
    "{search_results}\n\n"
    "Return the single best URL, or UNKNOWN if none are reliable."
)

_USER_PROMPT_NO_SEARCH = (
    "Municipality: {town_name}, {state}\n\n"
    "Task: {llm_hint}\n\n"
    "No web-search results available — use your training knowledge.\n"
    "Return the single best URL you know, or UNKNOWN if uncertain."
)


# ---------------------------------------------------------------------------
# Tavily search helper
# ---------------------------------------------------------------------------

def _tavily_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Run a Tavily web search and return a list of result dicts.

    Each result has ``url``, ``title``, and ``content`` keys.

    Falls back to an empty list when:
    * ``TAVILY_API_KEY`` is not set.
    * The ``tavily-python`` package is not installed.
    * The search request fails.

    This means the rest of the pipeline degrades gracefully to LLM-only mode.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.info(
            "discovery_agent | TAVILY_API_KEY not set — skipping web search "
            "(LLM-only mode). Set TAVILY_API_KEY for grounded URL discovery."
        )
        return []

    try:
        from tavily import TavilyClient  # type: ignore[import]
    except ImportError:
        logger.warning(
            "discovery_agent | 'tavily-python' not installed — skipping web search. "
            "Run: pip install tavily-python"
        )
        return []

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_raw_content=False,
        )
        results = response.get("results", [])
        logger.debug(
            "discovery_agent | Tavily returned %d result(s) for query: %s",
            len(results), query[:80],
        )
        return [
            {
                "url":     r.get("url", ""),
                "title":   r.get("title", ""),
                "content": r.get("content", "")[:300],
            }
            for r in results
        ]
    except Exception as exc:
        logger.warning("discovery_agent | Tavily search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# LLM URL selector
# ---------------------------------------------------------------------------

def _select_url_with_llm(
    town_name: str,
    state: str,
    llm_hint: str,
    search_results: List[Dict[str, str]],
    provider: Optional[str],
    model: Optional[str],
) -> str:
    """
    Ask the LLM to pick the best URL from *search_results*, or recall from
    training if no results are available.

    Returns the raw URL string, or ``"UNKNOWN"`` if the model is unsure.
    """
    if search_results:
        results_text = "\n".join(
            f"  [{i+1}] {r['title']}\n       URL: {r['url']}\n       {r['content']}"
            for i, r in enumerate(search_results)
        )
        user_prompt = _USER_PROMPT_SEARCH.format(
            town_name=town_name,
            state=state,
            llm_hint=llm_hint.format(town_name=town_name, state=state),
            search_results=results_text,
        )
    else:
        user_prompt = _USER_PROMPT_NO_SEARCH.format(
            town_name=town_name,
            state=state,
            llm_hint=llm_hint.format(town_name=town_name, state=state),
        )

    raw = call_llm(
        system=_SYSTEM_PROMPT_URL,
        user=user_prompt,
        provider=provider,
        model=model,
        n_tokens=512,
    )

    # Strip any residual markdown or quotes the model might add
    url = raw.strip().strip("`").strip('"').strip("'")

    # Sanity-check: must look like a URL
    if not url.startswith(("http://", "https://")) and url != "UNKNOWN":
        logger.warning(
            "discovery_agent | LLM returned non-URL string %r — treating as UNKNOWN",
            url,
        )
        return "UNKNOWN"

    return url


# ---------------------------------------------------------------------------
# YAML in-place updater
# ---------------------------------------------------------------------------

def _get_nested(data: Dict, key_path: str) -> Any:
    """Get a value from a nested dict using a dot-separated key path."""
    parts = key_path.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_nested(data: Dict, key_path: str, value: Any) -> None:
    """Set a value in a nested dict using a dot-separated key path."""
    parts = key_path.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _update_config_yaml(config_path: pathlib.Path, key_path: str, new_url: str) -> None:
    """
    Read ``config_path``, update the value at ``key_path``, and write it back.

    Uses a regex-based substitution on the raw YAML text so that all
    comments, ordering, and formatting are preserved.  Falls back to a full
    ``yaml.dump`` round-trip only if the regex fails to find the target line.
    """
    raw_text = config_path.read_text(encoding="utf-8")
    last_key = key_path.split(".")[-1]

    # Match lines like:
    #   property_assessor: "https://PLACEHOLDER..."
    #   property_assessor:   https://PLACEHOLDER...
    #   permits_api: "https://PLACEHOLDER/api"  # trailing comment
    #
    # Strategy: capture everything before the URL value as group 1, the
    # optional opening quote as group 2, the URL value (anything up to an
    # optional closing quote) as group 3, and the rest of the line
    # (closing quote + optional comment + EOL whitespace) as group 4.
    # Using a lazy match for the URL body so we don't swallow the closing quote.
    pattern = re.compile(
        rf'^(\s*{re.escape(last_key)}\s*:\s*)(["\']?)(.*?PLACEHOLDER.*?)(["\']?\s*(?:#[^\n]*)?)$',
        re.MULTILINE,
    )
    replacement = rf'\g<1>\g<2>{new_url}\g<4>'

    updated, count = pattern.subn(replacement, raw_text)

    if count > 0:
        config_path.write_text(updated, encoding="utf-8")
        logger.info(
            "discovery_agent | Updated %s → %s in %s",
            key_path, new_url, config_path.name,
        )
        return

    # Fallback: full YAML round-trip (loses comments)
    logger.warning(
        "discovery_agent | Regex substitution failed for %s — "
        "falling back to full YAML round-trip (comments may be lost).",
        key_path,
    )
    with open(config_path) as f:
        data = yaml.safe_load(f)
    _set_nested(data, key_path, new_url)
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    logger.info(
        "discovery_agent | (fallback) Updated %s → %s in %s",
        key_path, new_url, config_path.name,
    )


# ---------------------------------------------------------------------------
# Main discovery class
# ---------------------------------------------------------------------------

class DiscoveryAgent:
    """
    Discovers real data URLs for a municipality and injects them into its config.

    Parameters
    ----------
    town_slug : str
        Kebab-case municipality identifier (e.g. ``"waltham-ma"``).
    provider : str, optional
        LLM provider (``"gemini"``, ``"openai"``, ``"anthropic"``).
        Auto-detected from environment variables when omitted.
    model : str, optional
        Override LLM model name.
    config_base_dir : str, optional
        Root directory for per-town config folders.  Defaults to ``"configs"``.
    dry_run : bool
        When True, print proposed replacements without writing any files.
    """

    def __init__(
        self,
        town_slug: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_base_dir: str = "configs",
        dry_run: bool = False,
    ) -> None:
        self._town_slug = town_slug
        self._config_base = pathlib.Path(config_base_dir)
        self._config_path = self._config_base / town_slug / "config.yaml"
        self._dry_run = dry_run

        if not self._config_path.exists():
            raise FileNotFoundError(
                f"DiscoveryAgent | No config found for town_slug='{town_slug}'. "
                f"Expected: {self._config_path}. "
                "Run the Expansion Engine first to scaffold the config."
            )

        # Load config to get town name + state
        loader = ConfigLoader(base_dir=config_base_dir)
        cfg = loader.get_town_config(town_slug)
        self._town_name: str = cfg.get("town_name", town_slug)
        self._state: str = cfg.get("state", "")
        self._cfg = cfg

        # LLM provider
        try:
            self._provider = provider or select_provider()
        except RuntimeError:
            self._provider = None
        self._model = model

    def _should_discover(self, current_value: Any) -> bool:
        """Return True when a config value still needs URL discovery."""
        return isinstance(current_value, str) and "PLACEHOLDER" in current_value

    def discover_urls(self) -> Dict[str, str]:
        """
        Iterate over all ``URL_DISCOVERY_TARGETS``, discover each placeholder,
        and return a dict mapping ``config_key → discovered_url``.

        If ``dry_run=True``, the config is NOT modified.
        """
        if self._provider is None:
            logger.error(
                "discovery_agent | No LLM API key found. "
                "Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
            )
            return {}

        results: Dict[str, str] = {}
        skipped = 0

        for target in URL_DISCOVERY_TARGETS:
            key_path   = target["config_key"]
            query_tpl  = target["search_query"]
            llm_hint   = target["llm_hint"]

            current = _get_nested(self._cfg, key_path)

            if not self._should_discover(current):
                logger.debug(
                    "discovery_agent | %s already set (%r) — skipping.",
                    key_path, str(current)[:60],
                )
                skipped += 1
                continue

            # Build search query
            query = query_tpl.format(
                town_name=self._town_name,
                state=self._state,
                town_slug=self._town_slug,
            )

            logger.info("discovery_agent | Discovering %s …", key_path)
            logger.debug("discovery_agent | Search query: %s", query)

            # Step 1 — web search (may return empty list)
            search_results = _tavily_search(query)

            # Step 2 — LLM selection
            t0 = time.perf_counter()
            discovered_url = _select_url_with_llm(
                town_name=self._town_name,
                state=self._state,
                llm_hint=llm_hint,
                search_results=search_results,
                provider=self._provider,
                model=self._model,
            )
            elapsed = time.perf_counter() - t0

            grounded = "Tavily+LLM" if search_results else "LLM-only"
            logger.info(
                "discovery_agent | %s → %s  [%s, %.2fs]",
                key_path, discovered_url, grounded, elapsed,
            )

            results[key_path] = discovered_url

            if discovered_url == "UNKNOWN":
                logger.warning(
                    "discovery_agent | Could not determine URL for %s — "
                    "PLACEHOLDER left in config. Investigate manually.",
                    key_path,
                )
                continue

            # Step 3 — inject into YAML
            if self._dry_run:
                print(f"  [DRY-RUN] Would set {key_path}:")
                print(f"            {current!r}")
                print(f"         →  {discovered_url!r}")
            else:
                _update_config_yaml(self._config_path, key_path, discovered_url)

        discovered_count = sum(1 for v in results.values() if v != "UNKNOWN")
        logger.info(
            "discovery_agent | Done — %d/%d URL(s) discovered, %d already set.",
            discovered_count, len(results), skipped,
        )
        return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    p = argparse.ArgumentParser(description="TownEye — URL Discovery Agent (Patch #183)")
    p.add_argument("--town",     required=True, help="Town slug, e.g. waltham-ma")
    p.add_argument("--dry-run",  action="store_true",
                   help="Print proposed URL replacements without writing the config")
    p.add_argument("--provider", choices=["gemini", "openai", "anthropic"], default=None)
    p.add_argument("--model",    default=None, help="Override LLM model name")
    args = p.parse_args()

    agent = DiscoveryAgent(
        town_slug=args.town,
        provider=args.provider,
        model=args.model,
        dry_run=args.dry_run,
    )
    discovered = agent.discover_urls()

    print(f"\n{'═'*60}")
    print(f"  Discovery complete for: {args.town}")
    print(f"{'═'*60}")
    for key, url in discovered.items():
        status = "✓" if url != "UNKNOWN" else "✗"
        print(f"  {status}  {key:<40}  {url}")

# core/discovery_agent.py
# End of Patch #183
