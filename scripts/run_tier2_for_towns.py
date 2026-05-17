# [FILE PATH]: scripts/run_tier2_for_towns.py
# Tier 5 — re-run only the Tier 2 (Domain 14-19) scrapers for one or more towns.
# Date: 2026-05-07
"""
Targeted runner that exercises only the six Tier-2 (Domain 14-19) scrapers
without re-running the upstream LLM expansion / discovery / Tier-1 ingest.

Invoked during Tier 5 to:
  * Re-scrape Arlington against the new MassGIS L3 parcel source.
  * First-scrape Lexington with its newly-populated Tier 2 config.

Verifies the DomainNotApplicableError "skipped" classification by counting
ok / fail / skipped per town and reporting it.

Run:
    .venv/bin/python scripts/run_tier2_for_towns.py arlington-ma lexington-ma
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.master_loop import _run_scrapers_for_town

TIER2_DOMAINS = [
    "parcel",
    "zoning-overlay",
    "macris",
    "noncompliance",
    "local-historic",
    "environmental-overlay",
]


def main(town_slugs: List[str]) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    print("=" * 78)
    print("  Tier 5 — re-running Tier 2 ingestors for selected towns")
    print(f"  towns:  {', '.join(town_slugs)}")
    print(f"  domains: {', '.join(TIER2_DOMAINS)}")
    print("=" * 78)

    t_total_0 = time.perf_counter()
    summaries = []

    for slug in town_slugs:
        print(f"\n--- {slug} ---")
        t_town_0 = time.perf_counter()
        results = _run_scrapers_for_town(
            town_slug=slug,
            enabled_domains=TIER2_DOMAINS,
        )
        t_town = time.perf_counter() - t_town_0

        ok      = sum(1 for r in results.values() if r["status"] == "ok")
        fail    = sum(1 for r in results.values() if r["status"] == "fail")
        skipped = sum(1 for r in results.values() if r["status"] == "skipped")

        print(f"\n  {slug} summary: {ok} ok / {fail} fail / {skipped} skipped"
              f"  (in {t_town:.1f}s)")
        for d, r in results.items():
            tag = {"ok": "OK ", "fail": "ERR", "skipped": "SKP"}[r["status"]]
            rows = r.get("rows", 0)
            elapsed = r.get("elapsed", 0)
            extra = ""
            if r["status"] == "skipped":
                extra = f"  ({r.get('reason', '')})"
            elif r["status"] == "fail":
                extra = "  (see master_loop log)"
            print(f"    [{tag}] {d:<22} rows={rows:>6}  elapsed={elapsed:>6.1f}s{extra}")
        summaries.append((slug, ok, fail, skipped, t_town))

    t_total = time.perf_counter() - t_total_0
    print(f"\n{'=' * 78}")
    print("  ALL TOWNS — Tier 2 summary")
    print(f"{'=' * 78}")
    for slug, ok, fail, skipped, dt in summaries:
        print(f"  {slug:<20s}  {ok} ok / {fail} fail / {skipped} skipped"
              f"  ({dt:.1f}s)")
    print(f"  total elapsed: {t_total:.1f}s")
    return 0 if all(f == 0 for _, _, f, _, _ in summaries) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: run_tier2_for_towns.py <town_slug> [<town_slug> ...]")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
