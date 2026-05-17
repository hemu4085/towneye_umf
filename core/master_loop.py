# [FILE PATH]: core/master_loop.py
# Patch #187 (updated from Patch #183)
# Execution Mode: Master Orchestrator — Fully Autonomous 500-Town Pipeline
# Date: 2026-03-04
"""
MasterLoop
==========
The fully autonomous end-to-end orchestration engine for TownEye UMF.

It chains the three prior agents into a single self-driving loop that
scales the platform from zero to 500 onboarded towns without any human
intervention:

  ┌─────────────────────────────────────────────────────────┐
  │  LOOP until registry hits --target towns                │
  │                                                         │
  │  1. ExpansionAgent  → scaffold N new town configs       │
  │  2. DiscoveryAgent  → inject real URLs into each config │
  │  3. UniversalRunner → execute all 13 scrapers per town  │
  │  4. persist run log & loop metrics                      │
  └─────────────────────────────────────────────────────────┘

Each loop iteration:
  * Calls ``expansion_agent.run_expansion(batch_total=per_round)`` to
    scaffold ``per_round`` new configs.
  * For every newly scaffolded town, runs ``DiscoveryAgent`` to replace
    PLACEHOLDER URLs with real ones.
  * For every town with discovered URLs, executes all enabled scrapers via
    ``_run_scrapers_for_town()``.
  * Writes a JSON run-log to ``data/master_loop_runs.jsonl`` (append-only).
  * Respects ``--skip-discovery`` and ``--skip-scraping`` flags for partial
    runs or dry-run testing.

Direct-onboard mode (Patch #187)
---------------------------------
Pass ``--towns`` to bypass the LLM expansion step and onboard specific,
named municipalities directly::

    python core/master_loop.py --towns "Somerville MA" --skip-expansion
    python core/master_loop.py --towns "Somerville MA,Waltham MA" --skip-expansion

The ``--skip-expansion`` flag is optional but recommended when using
``--towns`` to make intent explicit.  The loop:

  1. Derives a ``town_slug`` from each ``"Town State"`` string.
  2. Scaffolds ``configs/{town_slug}/config.yaml`` if it does not exist.
  3. Adds the town to the expansion registry.
  4. Runs ``DiscoveryAgent`` to replace PLACEHOLDER URLs.
  5. Runs all 13 scrapers for the town.

Scraper registry
----------------
The 13-domain scraper map lives in ``SCRAPER_REGISTRY`` below — the only
place in the codebase where domain-to-module names are listed.  To add a
new domain, add one entry here.  No other file changes required.

Zero-Hardcoding contract
------------------------
* No town name, URL, or path appears in logic code.
* All town-specific values flow from ``configs/{town_slug}/config.yaml``.
* The scraper registry maps domain labels to importable class paths; the
  ``town_slug`` is passed as a constructor argument at runtime.

Usage
-----
    # Onboard a specific town directly (Patch #187):
    python core/master_loop.py --towns "Somerville MA" --skip-expansion

    # Onboard multiple towns at once:
    python core/master_loop.py --towns "Somerville MA,Waltham MA" --skip-expansion

    # Full run to 500 towns (LLM-driven expansion):
    python core/master_loop.py --target 500

    # Dry-run — expand + discover but do not scrape:
    python core/master_loop.py --target 10 --skip-scraping --dry-run

    # Resume from where you left off (reads existing registry):
    python core/master_loop.py --target 500

    # Only scrape already-scaffolded towns with no scrape record:
    python core/master_loop.py --target 0 --scrape-pending

Environment variables
---------------------
``GEMINI_API_KEY`` / ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``  — LLM key
``TAVILY_API_KEY``  — web-search key for DiscoveryAgent (optional)
``DATABASE_URL``    — PostgreSQL DSN for PartyLinker (optional; HashLinker used otherwise)
``TOWNEYE_ENV``     — set to ``production`` to route Parquet writes to GCS
"""

import argparse
import importlib
import json
import logging
import os
import pathlib
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.config_loader import ConfigLoader
from core.expansion_agent import _load_registry, _onboarded_slugs, run_expansion, _make_slug, _scaffold_config
from core.discovery_agent import DiscoveryAgent
from core.identity_linker import get_linker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skip-on-missing-source signal
# ---------------------------------------------------------------------------
class DomainNotApplicableError(Exception):
    """
    Raised by a scraper when a town does not publish any source for the
    domain (e.g. Lexington has no land-use noncompliance layer).

    The master loop catches this and classifies the domain as ``"skipped"``
    in run results — distinct from a real failure.  Towns opt out by
    leaving the relevant ``scraper_urls.<key>`` empty in their config.
    """

    def __init__(self, town_slug: str, domain: str, reason: str = "") -> None:
        self.town_slug = town_slug
        self.domain = domain
        self.reason = reason
        super().__init__(
            f"[{town_slug}] domain '{domain}' not applicable for this town"
            + (f": {reason}" if reason else "")
        )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT  = pathlib.Path(__file__).resolve().parent.parent
_RUN_LOG_PATH  = _PROJECT_ROOT / "data" / "master_loop_runs.jsonl"
_SCRAPE_LOG    = _PROJECT_ROOT / "data" / "scrape_status.json"

# ---------------------------------------------------------------------------
# Scraper registry — maps domain name → (module_path, class_name)
# Each class must accept town_slug as its first constructor argument.
# ---------------------------------------------------------------------------
SCRAPER_REGISTRY: List[Dict[str, str]] = [
    # Domain 01 — Physical Foundation
    {"domain": "property",        "module": "scrapers.universal_property",
     "class": "ArlingtonPropertyScraper",       "output_domain": "property"},
    # Domain 02 — Zoning
    {"domain": "zoning",          "module": "scrapers.universal_zoning",
     "class": "ArlingtonZoningScraper",          "output_domain": "zoning"},
    # Domain 03 — Market Dynamics
    {"domain": "market-trends",   "module": "scrapers.universal_market",
     "class": "ArlingtonMarketIngestor",         "output_domain": "market-trends"},
    # Domain 04 — Infra Friction
    {"domain": "infra-projects",  "module": "scrapers.universal_dpw",
     "class": "ArlingtonDPWScraper",             "output_domain": "infra-projects"},
    # Domain 05 — Permit Velocity
    {"domain": "permits",         "module": "scrapers.universal_permits",
     "class": "ArlingtonPermitScraper",          "output_domain": "permits"},
    # Domain 06 — Connectivity
    {"domain": "broadband",       "module": "scrapers.universal_broadband",
     "class": "ArlingtonBroadbandIngestor",      "output_domain": "broadband"},
    # Domain 07 — Climate Resilience
    {"domain": "climate-zones",   "module": "scrapers.universal_climate",
     "class": "ArlingtonClimateIngestor",        "output_domain": "climate-zones"},
    # Domain 08 — Town Pulse / MBTA Transit Alerts
    {"domain": "transit",         "module": "scrapers.universal_transit",
     "class": "ArlingtonTransitScraper",         "output_domain": "transit"},
    # Domain 09a — Economic Pulse / SeeClickFix 311
    {"domain": "311",             "module": "scrapers.universal_311",
     "class": "Arlington311Scraper",             "output_domain": "311"},
    # Domain 09b — Economic Pulse / School Calendar
    {"domain": "school-calendar", "module": "scrapers.universal_schools",
     "class": "ArlingtonSchoolCalendarIngestor", "output_domain": "school-calendar"},
    # Domain 10 — Social Equity
    {"domain": "equity-index",    "module": "scrapers.universal_equity",
     "class": "ArlingtonEquityIngestor",         "output_domain": "equity-index"},
    # Domain 11 — Town Profile
    {"domain": "town-profile",    "module": "scrapers.universal_town_profile",
     "class": "ArlingtonTownProfileIngestor",    "output_domain": "town-profile"},
    # Domain 12 — STR Dynamics
    {"domain": "str-dynamics",    "module": "scrapers.universal_str",
     "class": "ArlingtonStrDynamicsIngestor",    "output_domain": "str-dynamics"},
    # Domain 14 — Parcel Geometry (GIS polygons + computed lot dimensions)
    {"domain": "parcel",          "module": "scrapers.universal_parcel",
     "class": "ArlingtonParcelScraper",          "output_domain": "parcel"},
    # Domain 15 — Zoning Overlay Polygons (spatial counterpart to TeZoning)
    {"domain": "zoning-overlay",  "module": "scrapers.universal_zoning_overlay",
     "class": "ArlingtonZoningOverlayScraper",   "output_domain": "zoning-overlay"},
    # Domain 16 — MACRIS Historic Resources (statewide, town-filtered)
    {"domain": "macris",          "module": "scrapers.universal_macris",
     "class": "ArlingtonMacrisScraper",           "output_domain": "macris"},
    # Domain 17 — Land-Use / Zoning Non-Compliance polygons (descriptive)
    {"domain": "noncompliance",   "module": "scrapers.universal_noncompliance",
     "class": "ArlingtonNonComplianceScraper",    "output_domain": "noncompliance"},
    # Domain 18 — Local Historic Resources (multi-FS aggregator: LHD/NHD/Overlay/AHC)
    {"domain": "local-historic",  "module": "scrapers.universal_local_historic",
     "class": "ArlingtonLocalHistoricScraper",    "output_domain": "local-historic"},
    # Domain 19 — Environmental Overlay (wetlands + flood-effective + flood-preliminary)
    {"domain": "environmental-overlay", "module": "scrapers.universal_environmental_overlay",
     "class": "ArlingtonEnvironmentalOverlayScraper", "output_domain": "environmental-overlay"},
]

# Domains that run entirely from config fixtures / LLM and never need live URLs —
# these are always considered "safe to scrape" even when discovery returns UNKNOWN.
_DISCOVERY_INDEPENDENT_DOMAINS = {
    "market-trends", "equity-index", "town-profile", "str-dynamics",
}


# ---------------------------------------------------------------------------
# Scrape-status log helpers
# ---------------------------------------------------------------------------

def _load_scrape_log() -> Dict[str, Any]:
    """Return the scrape-status dict, keyed by town_slug."""
    if _SCRAPE_LOG.exists():
        with open(_SCRAPE_LOG) as f:
            return json.load(f)
    return {}


def _save_scrape_log(log: Dict[str, Any]) -> None:
    _SCRAPE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_SCRAPE_LOG, "w") as f:
        json.dump(log, f, indent=2)


def _append_run_log(entry: Dict[str, Any]) -> None:
    """Append one run record to the JSONL run log (append-only)."""
    _RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUN_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Patch #187 — Direct-onboard helpers
# ---------------------------------------------------------------------------

def _parse_town_input(raw: str) -> tuple[str, str]:
    """
    Parse a human-readable town string into ``(town_name, state)`` parts.

    Accepts formats like ``"Somerville MA"``, ``"Somerville, MA"``,
    ``"somerville-ma"`` (kebab slug, split on last dash).

    Returns
    -------
    tuple[str, str]
        ``(town_name, state)`` — both title-cased / upper-cased as appropriate.

    Examples
    --------
    >>> _parse_town_input("Somerville MA")
    ('Somerville', 'MA')
    >>> _parse_town_input("New Bedford, MA")
    ('New Bedford', 'MA')
    >>> _parse_town_input("somerville-ma")
    ('Somerville', 'MA')
    """
    raw = raw.strip()

    # Already a kebab slug? e.g. "somerville-ma"
    if raw.replace("-", "").replace(" ", "").isalnum() and "-" in raw and " " not in raw:
        parts = raw.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) == 2:
            town_name = parts[0].replace("-", " ").title()
            state = parts[1].upper()
            return town_name, state

    # Strip optional comma separator: "Somerville, MA" → "Somerville MA"
    raw = raw.replace(",", " ")
    tokens = raw.split()
    if len(tokens) >= 2 and len(tokens[-1]) == 2:
        state = tokens[-1].upper()
        town_name = " ".join(tokens[:-1]).title()
        return town_name, state

    # Fallback: treat entire string as town name, state unknown
    logger.warning(
        "master_loop | Could not parse state from %r — using 'XX' as placeholder.",
        raw,
    )
    return raw.title(), "XX"


def _ensure_town_onboarded(
    town_name: str,
    state: str,
    llm_model: str = "direct-onboard",
    dry_run: bool = False,
) -> str:
    """
    Guarantee that a town has a scaffolded config and a registry entry.

    If the config does not exist it is created from the expansion-agent
    template using the provided ``town_name`` and ``state`` (lat/lon are
    set to 0.0; the DiscoveryAgent will fill real URLs in the next step).
    If the town is already in the registry it is left untouched.

    Parameters
    ----------
    town_name : str
        Proper town name, e.g. ``"Somerville"``.
    state : str
        Two-letter state abbreviation, e.g. ``"MA"``.
    llm_model : str
        Label stamped into ``expansion_metadata.llm_model``.
    dry_run : bool
        When True, scaffold is printed but not written.

    Returns
    -------
    str
        The derived ``town_slug`` (e.g. ``"somerville-ma"``).
    """
    town_slug = _make_slug(town_name, state)
    registry = _load_registry()

    config_path = _PROJECT_ROOT / "configs" / town_slug / "config.yaml"

    if not config_path.exists():
        logger.info(
            "master_loop | No config for %s — scaffolding from template.", town_slug
        )
        _scaffold_config(
            town={
                "town_name": town_name,
                "state":     state,
                "county":    "",
                "fips_code": "",
                "lat":       0.0,
                "lon":       0.0,
                "population_tier": "unknown",
                "rationale": f"Direct-onboarded via --towns flag (Patch #187)",
            },
            seed_source="--towns CLI flag",
            llm_model=llm_model,
            dry_run=dry_run,
        )
    else:
        logger.info(
            "master_loop | Config already exists for %s — skipping scaffold.", town_slug
        )

    # Ensure registry entry exists
    existing_slugs = _onboarded_slugs(registry)
    if town_slug not in existing_slugs and not dry_run:
        from core.expansion_agent import _compute_geohash
        registry.setdefault("onboarded", []).append({
            "town_slug":   town_slug,
            "town_name":   town_name,
            "state":       state,
            "lat":         0.0,
            "lon":         0.0,
            "geo_hash":    _compute_geohash(0.0, 0.0),
            "config_path": str(config_path),
            "rationale":   "Direct-onboarded via --towns flag (Patch #187)",
        })
        from core.expansion_agent import _save_registry
        _save_registry(registry)
        logger.info("master_loop | Added %s to expansion registry.", town_slug)
    elif town_slug in existing_slugs:
        logger.info("master_loop | %s already in registry — skipping.", town_slug)

    return town_slug


def _onboard_one(
    town_slug: str,
    scrape_log: Dict[str, Any],
    session_stats: Dict[str, Any],
    skip_discovery: bool = False,
    skip_scraping: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    """
    Run the full discovery → scrape pipeline for a single already-scaffolded town.

    Parameters
    ----------
    town_slug : str
        Kebab-case identifier for a town whose config already exists.
    scrape_log : dict
        Mutable scrape-status dict; updated in-place.
    session_stats : dict
        Mutable session counter dict; updated in-place.
    skip_discovery : bool
        Skip the DiscoveryAgent URL-injection step.
    skip_scraping : bool
        Skip the scraper execution step.
    provider : str, optional
        LLM provider override passed to DiscoveryAgent.
    model : str, optional
        LLM model override passed to DiscoveryAgent.
    """
    # ── Discovery ────────────────────────────────────────────────────────
    if not skip_discovery:
        logger.info("master_loop | [%s] Running DiscoveryAgent …", town_slug)
        try:
            agent = DiscoveryAgent(
                town_slug=town_slug,
                provider=provider,
                model=model,
                dry_run=False,
            )
            found = agent.discover_urls()
            discovered_count = sum(1 for v in found.values() if v != "UNKNOWN")
            session_stats["discovered"] += discovered_count
            logger.info(
                "master_loop | [%s] Discovery complete — %d/%d URLs found.",
                town_slug, discovered_count, len(found),
            )
        except Exception:
            logger.error(
                "master_loop | [%s] Discovery failed:\n%s",
                town_slug, traceback.format_exc(),
            )
    else:
        logger.info("master_loop | [%s] URL discovery skipped (--skip-discovery).", town_slug)

    # ── Scraping ─────────────────────────────────────────────────────────
    if not skip_scraping:
        _scrape_one(town_slug, scrape_log, session_stats, skip_scraping=False)
        _save_scrape_log(scrape_log)
    else:
        logger.info("master_loop | [%s] Scraping skipped (--skip-scraping).", town_slug)


# ---------------------------------------------------------------------------
# Scraper runner
# ---------------------------------------------------------------------------

def _run_scrapers_for_town(
    town_slug: str,
    enabled_domains: Optional[List[str]] = None,
    output_dir: str = "data/gold",
) -> Dict[str, Any]:
    """
    Import and execute each registered scraper for *town_slug*.

    Parameters
    ----------
    town_slug : str
        The target municipality.
    enabled_domains : list[str], optional
        Subset of domain names to run.  All domains run when omitted.
    output_dir : str
        Gold Parquet output directory.

    Returns
    -------
    dict
        ``{domain: {"status": "ok"|"fail", "rows": int, "error": str|None}}``
    """
    linker = get_linker()
    results: Dict[str, Any] = {}

    for entry in SCRAPER_REGISTRY:
        domain = entry["domain"]
        if enabled_domains and domain not in enabled_domains:
            continue

        module_path = entry["module"]
        class_name  = entry["class"]

        logger.info(
            "master_loop | [%s] Running domain=%s via %s.%s",
            town_slug, domain, module_path, class_name,
        )
        t0 = time.perf_counter()

        try:
            mod      = importlib.import_module(module_path)
            cls      = getattr(mod, class_name)
            scraper  = cls(town_slug=town_slug, linker=linker)
            out_path = scraper.run(output_dir=output_dir)

            import pandas as pd
            df   = pd.read_parquet(out_path)
            rows = len(df)

            elapsed = time.perf_counter() - t0
            logger.info(
                "master_loop | [%s] domain=%s → %d row(s) in %.2fs",
                town_slug, domain, rows, elapsed,
            )
            results[domain] = {
                "status":  "ok",
                "rows":    rows,
                "path":    str(out_path),
                "elapsed": round(elapsed, 2),
                "error":   None,
            }

        except DomainNotApplicableError as exc:
            elapsed = time.perf_counter() - t0
            logger.info(
                "master_loop | [%s] domain=%s SKIPPED after %.2fs (%s)",
                town_slug, domain, elapsed, exc.reason or "no source configured",
            )
            results[domain] = {
                "status":  "skipped",
                "rows":    0,
                "path":    None,
                "elapsed": round(elapsed, 2),
                "error":   None,
                "reason":  exc.reason or "no source configured for this town",
            }

        except Exception:
            elapsed = time.perf_counter() - t0
            tb = traceback.format_exc()
            logger.error(
                "master_loop | [%s] domain=%s FAILED after %.2fs:\n%s",
                town_slug, domain, elapsed, tb,
            )
            results[domain] = {
                "status":  "fail",
                "rows":    0,
                "path":    None,
                "elapsed": round(elapsed, 2),
                "error":   tb,
            }

    return results


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_master_loop(
    target: int = 500,
    per_round: int = 10,
    seed_towns: Optional[List[str]] = None,
    direct_towns: Optional[List[str]] = None,
    skip_expansion: bool = False,
    skip_discovery: bool = False,
    skip_scraping: bool = False,
    dry_run: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    scrape_pending: bool = False,
) -> None:
    """
    Run the fully autonomous expansion + discovery + scraping loop.

    Parameters
    ----------
    target : int
        Total number of towns to have in the registry when finished.
        Set to 0 with ``scrape_pending=True`` to only scrape already-
        scaffolded towns that haven't been scraped yet.
    per_round : int
        Towns to expand per LLM call (default 10).
    seed_towns : list[str], optional
        Seed towns for the Expansion Engine.
    direct_towns : list[str], optional
        Explicit list of ``"Town State"`` strings to onboard directly,
        bypassing the LLM expansion step (Patch #187).
        e.g. ``["Somerville MA", "Waltham MA"]``
    skip_expansion : bool
        Skip the LLM expansion step entirely.  Implicit when
        ``direct_towns`` is provided.
    skip_discovery : bool
        Skip the URL-discovery step (use configs as-is).
    skip_scraping : bool
        Skip the scraping step (expand + discover only).
    dry_run : bool
        Passed through to ExpansionAgent and DiscoveryAgent; no files written.
    provider : str, optional
        LLM provider override.
    model : str, optional
        LLM model override.
    scrape_pending : bool
        If True, scan the registry for towns with no scrape record and
        scrape them, then exit (ignores target/expansion).
    """
    _seed = seed_towns or [
        "Arlington MA", "Somerville MA", "Burlington MA",
        "Lexington MA", "Bedford MA",
    ]

    scrape_log   = _load_scrape_log()
    session_start = datetime.now(tz=timezone.utc).isoformat()
    session_stats: Dict[str, Any] = {
        "started_at":   session_start,
        "target":       target,
        "expanded":     0,
        "discovered":   0,
        "scraped":      0,
        "domain_ok":    0,
        "domain_fail":  0,
    }

    logger.info("master_loop | ══ Session start ══")
    logger.info("master_loop | Target=%d  per_round=%d  skip_discovery=%s  skip_scraping=%s",
                target, per_round, skip_discovery, skip_scraping)

    # ------------------------------------------------------------------
    # Mode: direct-onboard named towns (Patch #187, --towns flag)
    # ------------------------------------------------------------------
    if direct_towns or skip_expansion:
        towns_to_onboard = direct_towns or []
        if not towns_to_onboard:
            logger.warning(
                "master_loop | --skip-expansion set but no --towns provided. "
                "Falling back to --scrape-pending mode."
            )
            scrape_pending = True
        else:
            logger.info(
                "master_loop | Direct-onboard mode — %d town(s): %s",
                len(towns_to_onboard), towns_to_onboard,
            )
            for raw_town in towns_to_onboard:
                town_name, state = _parse_town_input(raw_town)
                town_slug = _ensure_town_onboarded(
                    town_name=town_name,
                    state=state,
                    dry_run=dry_run,
                )
                session_stats["expanded"] += 1
                _onboard_one(
                    town_slug=town_slug,
                    scrape_log=scrape_log,
                    session_stats=session_stats,
                    skip_discovery=skip_discovery,
                    skip_scraping=skip_scraping,
                    provider=provider,
                    model=model,
                )
            _finish_session(session_stats, session_start)
            return

    # ------------------------------------------------------------------
    # Mode: scrape towns already in registry that have no scrape record
    # ------------------------------------------------------------------
    if scrape_pending:
        registry = _load_registry()
        pending = [
            e["town_slug"]
            for e in registry.get("onboarded", [])
            if e["town_slug"] not in scrape_log
        ]
        logger.info("master_loop | scrape_pending mode — %d town(s) have no scrape record.", len(pending))
        for slug in pending:
            _scrape_one(slug, scrape_log, session_stats, skip_scraping)
        _save_scrape_log(scrape_log)
        _finish_session(session_stats, session_start)
        return

    # ------------------------------------------------------------------
    # Main expand → discover → scrape loop
    # ------------------------------------------------------------------
    while True:
        registry = _load_registry()
        current_count = len(registry.get("onboarded", []))

        if current_count >= target and target > 0:
            logger.info(
                "master_loop | Registry already has %d/%d town(s) — target reached.",
                current_count, target,
            )
            break

        remaining   = (target - current_count) if target > 0 else per_round
        this_round  = min(per_round, remaining)

        logger.info(
            "master_loop | Registry: %d/%d towns. Expanding by %d …",
            current_count, target, this_round,
        )

        # ── Step 1: Expansion ────────────────────────────────────────
        slugs_before = set(_onboarded_slugs(_load_registry()))

        run_expansion(
            seed_towns=_seed,
            batch_total=this_round,
            per_round=this_round,
            dry_run=dry_run,
            provider=provider,
            model=model,
        )
        session_stats["expanded"] += this_round

        slugs_after  = set(_onboarded_slugs(_load_registry()))
        new_slugs    = list(slugs_after - slugs_before)

        logger.info("master_loop | %d new town(s) scaffolded: %s", len(new_slugs), new_slugs)

        # ── Step 2: Discovery ────────────────────────────────────────
        if not skip_discovery and not dry_run:
            for slug in new_slugs:
                logger.info("master_loop | Discovering URLs for %s …", slug)
                try:
                    agent = DiscoveryAgent(
                        town_slug=slug,
                        provider=provider,
                        model=model,
                        dry_run=False,
                    )
                    found = agent.discover_urls()
                    discovered_count = sum(1 for v in found.values() if v != "UNKNOWN")
                    session_stats["discovered"] += discovered_count
                    logger.info(
                        "master_loop | %s: %d/%d URLs discovered.",
                        slug, discovered_count, len(found),
                    )
                except Exception:
                    logger.error(
                        "master_loop | Discovery failed for %s:\n%s",
                        slug, traceback.format_exc(),
                    )
        elif skip_discovery:
            logger.info("master_loop | URL discovery skipped (--skip-discovery).")

        # ── Step 3: Scraping ─────────────────────────────────────────
        if not skip_scraping and not dry_run:
            for slug in new_slugs:
                _scrape_one(slug, scrape_log, session_stats, skip_scraping=False)
            _save_scrape_log(scrape_log)
        elif skip_scraping:
            logger.info("master_loop | Scraping skipped (--skip-scraping).")

        # ── Loop termination check ───────────────────────────────────
        new_count = len(_load_registry().get("onboarded", []))
        if target > 0 and new_count >= target:
            logger.info("master_loop | Target of %d reached — loop complete.", target)
            break

        if not new_slugs:
            logger.warning(
                "master_loop | Expansion returned 0 new towns — "
                "LLM may have exhausted candidates. Stopping."
            )
            break

    _finish_session(session_stats, session_start)


def _scrape_one(
    town_slug: str,
    scrape_log: Dict[str, Any],
    session_stats: Dict[str, Any],
    skip_scraping: bool,
) -> None:
    """Run all scrapers for *town_slug* and update *scrape_log* in-place."""
    if skip_scraping:
        return

    logger.info("master_loop | Scraping %s …", town_slug)
    t0 = time.perf_counter()
    domain_results = _run_scrapers_for_town(town_slug)
    elapsed = round(time.perf_counter() - t0, 2)

    ok      = sum(1 for r in domain_results.values() if r["status"] == "ok")
    fail    = sum(1 for r in domain_results.values() if r["status"] == "fail")
    skipped = sum(1 for r in domain_results.values() if r["status"] == "skipped")

    session_stats["scraped"]        += 1
    session_stats["domain_ok"]      += ok
    session_stats["domain_fail"]    += fail
    session_stats.setdefault("domain_skipped", 0)
    session_stats["domain_skipped"] += skipped

    scrape_log[town_slug] = {
        "scraped_at":      datetime.now(tz=timezone.utc).isoformat(),
        "elapsed_s":       elapsed,
        "domains_ok":      ok,
        "domains_fail":    fail,
        "domains_skipped": skipped,
        "results":         domain_results,
    }

    logger.info(
        "master_loop | %s scraped — %d ok / %d failed / %d skipped (%.2fs total)",
        town_slug, ok, fail, skipped, elapsed,
    )

    _append_run_log({
        "town_slug":       town_slug,
        "scraped_at":      scrape_log[town_slug]["scraped_at"],
        "elapsed_s":       elapsed,
        "domains_ok":      ok,
        "domains_fail":    fail,
        "domains_skipped": skipped,
    })


def _finish_session(stats: Dict[str, Any], started_at: str) -> None:
    stats["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
    registry = _load_registry()
    stats["registry_total"] = len(registry.get("onboarded", []))

    print(f"\n{'═'*62}")
    print("  MASTER LOOP SESSION COMPLETE")
    print(f"{'═'*62}")
    print(f"  Started         :  {started_at}")
    print(f"  Finished        :  {stats['finished_at']}")
    print(f"  Towns in registry:  {stats['registry_total']}")
    print(f"  Expanded        :  {stats['expanded']}")
    print(f"  URLs discovered :  {stats['discovered']}")
    print(f"  Towns scraped   :  {stats['scraped']}")
    print(f"  Domain runs OK  :  {stats['domain_ok']}")
    print(f"  Domain failures :  {stats['domain_fail']}")
    print(f"  Domain skipped  :  {stats.get('domain_skipped', 0)}")
    print(f"{'═'*62}\n")

    _append_run_log({"session_summary": stats})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    p = argparse.ArgumentParser(
        description="TownEye UMF — Master Loop Orchestrator (Patch #187)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Onboard a specific town directly — no LLM expansion needed:
  python core/master_loop.py --towns "Somerville MA" --skip-expansion

  # Onboard multiple towns at once:
  python core/master_loop.py --towns "Somerville MA,Waltham MA" --skip-expansion

  # Skip discovery and only run scrapers (config URLs already set):
  python core/master_loop.py --towns "Somerville MA" --skip-expansion --skip-discovery

  # Full LLM-driven run to 500 towns:
  python core/master_loop.py --target 500

  # Expand + discover, skip scraping (fast test):
  python core/master_loop.py --target 10 --skip-scraping

  # Dry run — no files written:
  python core/master_loop.py --target 5 --dry-run

  # Scrape all towns already in registry with no scrape record:
  python core/master_loop.py --target 0 --scrape-pending
""",
    )
    p.add_argument("--towns",           type=str, default=None,
                   help="Comma-separated town strings to onboard directly, e.g. 'Somerville MA,Waltham MA'")
    p.add_argument("--skip-expansion",  action="store_true",
                   help="Bypass LLM expansion; use --towns or --scrape-pending instead")
    p.add_argument("--target",          type=int, default=500,
                   help="Target total towns in registry (default: 500)")
    p.add_argument("--per-round",       type=int, default=10,
                   help="Towns to expand per LLM call (default: 10)")
    p.add_argument("--seed",            type=str, default=None,
                   help="Comma-separated seed towns (optional)")
    p.add_argument("--skip-discovery",  action="store_true",
                   help="Skip URL discovery (use configs as scaffolded)")
    p.add_argument("--skip-scraping",   action="store_true",
                   help="Skip scraping (expand + discover only)")
    p.add_argument("--dry-run",         action="store_true",
                   help="Expand and discover in dry-run mode; never write files")
    p.add_argument("--scrape-pending",  action="store_true",
                   help="Scrape already-scaffolded towns with no scrape record, then exit")
    p.add_argument("--provider",        choices=["gemini", "openai", "anthropic"], default=None)
    p.add_argument("--model",           default=None, help="Override LLM model name")
    args = p.parse_args()

    seeds        = [s.strip() for s in args.seed.split(",")]   if args.seed   else None
    direct_towns = [t.strip() for t in args.towns.split(",")]  if args.towns  else None

    run_master_loop(
        target=args.target,
        per_round=args.per_round,
        seed_towns=seeds,
        direct_towns=direct_towns,
        skip_expansion=args.skip_expansion,
        skip_discovery=args.skip_discovery,
        skip_scraping=args.skip_scraping,
        dry_run=args.dry_run,
        provider=args.provider,
        model=args.model,
        scrape_pending=args.scrape_pending,
    )

# core/master_loop.py
# End of Patch #187
