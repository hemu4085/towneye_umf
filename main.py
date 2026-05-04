# [FILE PATH]: main.py
# Patch #174 (Option C)
# Execution Mode: Full Pipeline Runner — all 10 domain ingestors + manifest
# Date: 2026-03-02
#
# Orchestrates all 10 domain ingestors in dependency order, using a
# hash-based VerificationLinker (no database required). Writes a pipeline
# manifest to data/pipeline_run.json: run timestamp, record counts,
# Parquet paths, and per-step duration for observability and CI gating.
#
# Forbidden City: set TOWN_SLUG below to re-target the entire pipeline.

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

# ---------------------------------------------------------------------------
# Logging — configure before any scraper boots
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ★  THE ONE VARIABLE THAT DEFINES THE TOWN  ★
# ---------------------------------------------------------------------------
TOWN_SLUG = "arlington-ma"

# ---------------------------------------------------------------------------
# Verification linker — stable BigInt PKs without a live database
# ---------------------------------------------------------------------------
class _VerificationLinker:
    """Hash-based mock linker for pipeline runs without DATABASE_URL."""
    def resolve(self, te_source: str, source_id: str) -> int:
        return abs(hash(f"{te_source}:{source_id}")) % 2_000_000_000


def _run_step(
    name: str,
    run_fn: Callable[[], Path],
) -> Dict[str, Any]:
    """Run a single ingestor and return path, count, and duration."""
    start = time.perf_counter()
    try:
        out_path = run_fn()
        elapsed = time.perf_counter() - start
        try:
            import pandas as pd
            df = pd.read_parquet(out_path)
            count = int(len(df))
        except Exception:
            count = -1
        return {
            "domain": name,
            "path": str(Path(out_path).resolve()),
            "record_count": count,
            "duration_seconds": round(elapsed, 3),
            "status": "ok",
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.exception("Pipeline step %s failed: %s", name, e)
        return {
            "domain": name,
            "path": None,
            "record_count": None,
            "duration_seconds": round(elapsed, 3),
            "status": "error",
            "error": str(e),
        }


def run_pipeline(town_slug: str) -> Dict[str, Any]:
    """
    Run all 10 domain ingestors in order and return a manifest.

    Order: Property → 311 → Transit → Zoning → Market → DPW → Permits →
           Broadband → Climate → Equity → Schools.
    """
    linker = _VerificationLinker()
    steps: List[Dict[str, Any]] = []
    run_start = time.perf_counter()

    # Lazy imports so scrapers only load when needed
    from scrapers import arlington_ma_property
    from scrapers import arlington_ma_311
    from scrapers import arlington_ma_transit
    from scrapers import arlington_ma_zoning
    from scrapers import arlington_ma_market
    from scrapers import arlington_ma_dpw
    from scrapers import arlington_ma_permits
    from scrapers import arlington_ma_broadband
    from scrapers import arlington_ma_climate
    from scrapers import arlington_ma_equity
    from scrapers import arlington_ma_schools

    ingestors = [
        ("01_property", lambda: arlington_ma_property.ArlingtonPropertyScraper(town_slug=town_slug, linker=linker).run()),
        ("02_311", lambda: arlington_ma_311.Arlington311Scraper(town_slug=town_slug, linker=linker).run()),
        ("03_transit", lambda: arlington_ma_transit.ArlingtonTransitScraper(town_slug=town_slug, linker=linker).run()),
        ("04_zoning", lambda: arlington_ma_zoning.ArlingtonZoningScraper(town_slug=town_slug, linker=linker).run()),
        ("05_market", lambda: arlington_ma_market.ArlingtonMarketIngestor(town_slug=town_slug, linker=linker).run()),
        ("06_dpw", lambda: arlington_ma_dpw.ArlingtonDPWScraper(town_slug=town_slug, linker=linker).run()),
        ("07_permits", lambda: arlington_ma_permits.ArlingtonPermitScraper(town_slug=town_slug, linker=linker).run()),
        ("08_broadband", lambda: arlington_ma_broadband.ArlingtonBroadbandIngestor(town_slug=town_slug, linker=linker).run()),
        ("09_climate", lambda: arlington_ma_climate.ArlingtonClimateIngestor(town_slug=town_slug, linker=linker).run()),
        ("10_equity", lambda: arlington_ma_equity.ArlingtonEquityIngestor(town_slug=town_slug, linker=linker).run()),
        ("11_schools", lambda: arlington_ma_schools.ArlingtonSchoolCalendarIngestor(town_slug=town_slug, linker=linker).run()),
    ]

    for name, run_fn in ingestors:
        logger.info("Pipeline | Running %s ...", name)
        steps.append(_run_step(name, run_fn))

    total_elapsed = time.perf_counter() - run_start
    total_records = sum(s.get("record_count") or 0 for s in steps if s.get("status") == "ok")
    failed = [s["domain"] for s in steps if s.get("status") == "error"]

    manifest = {
        "town_slug": town_slug,
        "run_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": round(total_elapsed, 3),
        "total_records": total_records,
        "steps": steps,
        "failed_domains": failed,
    }
    return manifest


def main() -> None:
    logger.info("=" * 60)
    logger.info("UMF Full Pipeline | town_slug='%s' | 10 domain ingestors", TOWN_SLUG)
    logger.info("=" * 60)

    manifest = run_pipeline(TOWN_SLUG)

    # Persist manifest
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "pipeline_run.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    logger.info("Pipeline manifest written → %s", manifest_path.resolve())

    # Summary
    logger.info("-" * 60)
    logger.info("Pipeline complete | duration=%.2fs | total_records=%s", manifest["duration_seconds"], manifest["total_records"])
    if manifest["failed_domains"]:
        logger.warning("Failed domains: %s", manifest["failed_domains"])
    logger.info("-" * 60)

    for step in manifest["steps"]:
        status = step["status"]
        rec = step.get("record_count")
        rec_str = str(rec) if rec is not None else "—"
        logger.info("  %s | %s | %s records | %.2fs", step["domain"], status, rec_str, step["duration_seconds"])

    print("\n--- Pipeline manifest (excerpt) ---")
    print(json.dumps({k: v for k, v in manifest.items() if k != "steps"}, indent=2, default=str))
    print("--- End ---\n")


if __name__ == "__main__":
    main()

# main.py
# End of Patch #174
