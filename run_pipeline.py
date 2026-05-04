# [FILE PATH]: run_pipeline.py
# Patch #178
# Execution Mode: Master Pipeline Orchestrator
# Date: 2026-03-02
"""
TownEye UMF — Master Pipeline Orchestrator
===========================================
Runs all 12 data domains for one or every onboarded town.

Usage
-----
Single town::

    python run_pipeline.py --town arlington-ma

All onboarded towns in configs/::

    python run_pipeline.py --all

Specific domains only (comma-separated domain IDs)::

    python run_pipeline.py --town arlington-ma --domains 01,03,05

Dry-run — print what would execute without running anything::

    python run_pipeline.py --all --dry-run

Parallel execution (N workers, --all mode only)::

    python run_pipeline.py --all --workers 4

Architecture
------------
Each domain maps to one or more ``ingest_*.py`` CLI wrapper scripts in
``scrapers/``.  The orchestrator invokes each via ``subprocess.run()`` so
domains are isolated: a crash in Domain 04 (DPW) never blocks Domain 05
(Permits).  All results are recorded in a manifest written to
``data/pipeline_run_{town_slug}.json``.

Zero-Hardcoding: the only town-specific reference is the slug passed via
``--town`` or discovered from ``configs/`` directory names.
"""

import argparse
import json
import logging
import pathlib
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
_CONFIGS_DIR  = _PROJECT_ROOT / "configs"
_DATA_DIR     = _PROJECT_ROOT / "data"
_PYTHON       = sys.executable   # reuse the venv's interpreter

# ---------------------------------------------------------------------------
# Domain registry — ordered list of (domain_id, label, script_path)
# Domains 11 and 12 (LLM synthesis) are registered but will log "pending"
# until their scraper scripts exist.
# ---------------------------------------------------------------------------
_DOMAINS: List[Tuple[str, str, str]] = [
    ("01", "Physical Foundation / Property Assessment",  "scrapers/ingest_property.py"),
    ("02", "Regulatory Layer / Zoning Bylaws",           "scrapers/ingest_zoning.py"),
    ("03", "Market Dynamics / MLS Trends",               "scrapers/ingest_market.py"),
    ("04", "Infra Friction / DPW Capital Plans",         "scrapers/ingest_dpw.py"),
    ("05", "Permit Velocity / Building Permits",         "scrapers/ingest_permits.py"),
    ("06", "Connectivity / FCC Broadband",               "scrapers/ingest_broadband.py"),
    ("07", "Climate Resilience / FEMA Flood Maps",       "scrapers/ingest_climate.py"),
    # Domain 08 (Predictive Maintenance) reuses the Permits data layer;
    # a dedicated SQL-view ingestor is pending (Patch #179).
    ("08", "Predictive Maintenance / Permit Age",        "scrapers/ingest_permits.py"),
    ("09a", "Economic Pulse / MBTA Transit Alerts",      "scrapers/ingest_transit.py"),
    ("09b", "Economic Pulse / SeeClickFix 311",          "scrapers/ingest_311.py"),
    ("09c", "Economic Pulse / School Calendar ICS",      "scrapers/ingest_schools.py"),
    ("10", "Social Equity / EJ Burden Indices",          "scrapers/ingest_equity.py"),
    ("11", "Town Profile / LLM Synthesis",               "scrapers/ingest_town_profile.py"),   # pending Patch #176
    ("12", "STR Dynamics / LLM Synthesis",               "scrapers/ingest_str.py"),             # pending Patch #177
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discover_towns() -> List[str]:
    """
    Return sorted list of all town slugs that have a config.yaml under configs/.
    Skips non-directory entries and hidden files (e.g. expansion_registry.json).
    """
    towns = []
    for entry in sorted(_CONFIGS_DIR.iterdir()):
        if entry.is_dir() and (entry / "config.yaml").exists():
            towns.append(entry.name)
    if not towns:
        raise RuntimeError(
            f"run_pipeline | No onboarded towns found in {_CONFIGS_DIR}. "
            "Run the Expansion Engine first: python core/expansion_agent.py"
        )
    return towns


def _run_domain(
    town_slug: str,
    domain_id: str,
    label: str,
    script: str,
    dry_run: bool = False,
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute one domain ingestor for a given town via subprocess.

    Returns a result dict with status, duration, stdout tail, and any error.
    """
    script_path = _PROJECT_ROOT / script
    result: Dict[str, Any] = {
        "domain":    domain_id,
        "label":     label,
        "script":    script,
        "town_slug": town_slug,
        "status":    None,
        "duration_seconds": None,
        "stdout_tail": None,
        "error": None,
    }

    # --- Script missing (pending domain) ---
    if not script_path.exists():
        result["status"] = "pending"
        result["error"]  = f"Script not found: {script} — domain not yet implemented."
        logger.warning(
            "run_pipeline | [%s] %s → PENDING (script missing: %s)",
            domain_id, label, script,
        )
        return result

    # --- Dry-run ---
    if dry_run:
        result["status"] = "dry_run"
        logger.info(
            "run_pipeline | [%s] DRY-RUN would execute: %s --town %s",
            domain_id, script, town_slug,
        )
        return result

    # --- Execute ---
    cmd = [_PYTHON, str(script_path), "--town", town_slug]
    if extra_args:
        cmd.extend(extra_args)

    logger.info(
        "run_pipeline | [%s] %-55s  → %s",
        domain_id, label, town_slug,
    )
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,        # 5-minute per-domain timeout
            cwd=str(_PROJECT_ROOT),
        )
        elapsed = time.perf_counter() - t0
        # Keep the last 10 lines of stdout for the manifest
        stdout_lines = (proc.stdout or "").strip().splitlines()
        result["stdout_tail"] = "\n".join(stdout_lines[-10:])

        if proc.returncode == 0:
            result["status"]           = "ok"
            result["duration_seconds"] = round(elapsed, 3)
            logger.info(
                "run_pipeline | [%s] ✓  %.2fs  %s",
                domain_id, elapsed,
                stdout_lines[-1] if stdout_lines else "",
            )
        else:
            result["status"]           = "error"
            result["duration_seconds"] = round(elapsed, 3)
            result["error"]            = (proc.stderr or "").strip()[-1000:]
            logger.error(
                "run_pipeline | [%s] ✗  rc=%d  %s",
                domain_id, proc.returncode,
                result["error"][:200],
            )
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - t0
        result["status"]           = "timeout"
        result["duration_seconds"] = round(elapsed, 3)
        result["error"]            = f"Domain timed out after {elapsed:.0f}s."
        logger.error("run_pipeline | [%s] ✗  TIMEOUT after %.0fs", domain_id, elapsed)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        result["status"]           = "error"
        result["duration_seconds"] = round(elapsed, 3)
        result["error"]            = str(exc)
        logger.error("run_pipeline | [%s] ✗  %s", domain_id, exc)

    return result


def _run_town(
    town_slug: str,
    selected_domains: Optional[List[str]],
    dry_run: bool,
) -> Dict[str, Any]:
    """
    Run all (or selected) domains for a single town.
    Returns a per-town manifest dict.
    """
    domains_to_run = [
        (did, label, script)
        for did, label, script in _DOMAINS
        if selected_domains is None or did in selected_domains
    ]

    logger.info("run_pipeline | ══ Town: %-30s (%d domain(s)) ══", town_slug, len(domains_to_run))
    t0    = time.perf_counter()
    steps = []

    for domain_id, label, script in domains_to_run:
        step = _run_domain(
            town_slug=town_slug,
            domain_id=domain_id,
            label=label,
            script=script,
            dry_run=dry_run,
        )
        steps.append(step)
        # Never abort the loop — next domain must always run

    total_elapsed = time.perf_counter() - t0
    ok_count      = sum(1 for s in steps if s["status"] == "ok")
    failed        = [s["domain"] for s in steps if s["status"] == "error"]
    pending       = [s["domain"] for s in steps if s["status"] == "pending"]

    manifest: Dict[str, Any] = {
        "town_slug":        town_slug,
        "run_start_utc":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": round(total_elapsed, 3),
        "domains_ok":       ok_count,
        "domains_failed":   failed,
        "domains_pending":  pending,
        "dry_run":          dry_run,
        "steps":            steps,
    }

    # Persist manifest
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = _DATA_DIR / f"pipeline_run_{town_slug}.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    logger.info("run_pipeline | Manifest → %s", manifest_path)

    return manifest


def _print_summary(manifests: List[Dict[str, Any]]) -> None:
    """Print a compact multi-town summary table to stdout."""
    print("\n" + "═" * 72)
    print(f"  {'TOWN':<30}  {'OK':>4}  {'FAIL':>4}  {'PEND':>4}  {'TIME':>7}")
    print("─" * 72)
    for m in manifests:
        ok   = m.get("domains_ok", 0)
        fail = len(m.get("domains_failed", []))
        pend = len(m.get("domains_pending", []))
        dur  = m.get("duration_seconds", 0)
        flag = " ✗" if fail else (" ⏳" if pend else " ✓")
        print(f"  {m['town_slug']:<30}  {ok:>4}  {fail:>4}  {pend:>4}  {dur:>6.1f}s{flag}")
    print("═" * 72 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_pipeline",
        description="TownEye UMF — Master Pipeline Orchestrator (Patch #178)",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--town",
        metavar="SLUG",
        help="Single town slug to process (e.g. arlington-ma)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Process every town that has a configs/{slug}/config.yaml",
    )
    p.add_argument(
        "--domains",
        metavar="LIST",
        help="Comma-separated domain IDs to run (e.g. 01,03,05,09a). Default: all.",
        default=None,
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would execute; do not run any subprocesses",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Parallel workers for --all mode (default: 1 = sequential)",
    )
    p.add_argument(
        "--list-domains",
        action="store_true",
        help="Print the domain registry and exit",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    args = _parse_args(argv)

    if args.list_domains:
        print(f"\n{'ID':<6}  {'Script':<45}  {'Label'}")
        print("─" * 90)
        for did, label, script in _DOMAINS:
            exists = "✓" if (_PROJECT_ROOT / script).exists() else "⏳"
            print(f"  {did:<5}  {script:<45}  {exists}  {label}")
        print()
        return

    selected_domains = (
        [d.strip() for d in args.domains.split(",")]
        if args.domains else None
    )

    towns = [args.town] if args.town else _discover_towns()

    logger.info("run_pipeline | ══════════════════════════════════════════════════")
    logger.info("run_pipeline | Master Orchestrator | %d town(s) | dry_run=%s",
                len(towns), args.dry_run)
    logger.info("run_pipeline | ══════════════════════════════════════════════════")

    manifests: List[Dict[str, Any]] = []

    if args.workers > 1 and len(towns) > 1:
        # Parallel per-town (domains within a town remain sequential)
        logger.info("run_pipeline | Parallel mode: %d workers", args.workers)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(_run_town, slug, selected_domains, args.dry_run): slug
                for slug in towns
            }
            for future in as_completed(futures):
                try:
                    manifests.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.error("run_pipeline | Worker error for %s: %s",
                                 futures[future], exc)
        manifests.sort(key=lambda m: m["town_slug"])
    else:
        for slug in towns:
            manifests.append(_run_town(slug, selected_domains, args.dry_run))

    _print_summary(manifests)

    # Top-level exit code: non-zero if any town had failures
    any_failed = any(m.get("domains_failed") for m in manifests)
    if any_failed:
        logger.warning("run_pipeline | One or more domains failed — see manifests above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

# run_pipeline.py
# End of Patch #178
