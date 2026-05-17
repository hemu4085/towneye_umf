#!/usr/bin/env python3
# [FILE PATH]: scripts/promote_property_from_l3.py
# Tier 5 / Path A — CLI driver for PropertyL3Promoter.
# Date: 2026-05-07
"""
Promote MassGIS L3 CAMA data carried in parcel.parquet.metadata.raw_attributes
into property.parquet for one or more towns.

Run after the master loop has populated parcel.parquet via the L3 ingest:

    .venv/bin/python scripts/promote_property_from_l3.py arlington-ma lexington-ma

For each town the script prints the number of parcels with L3 data,
the rows promoted, and how many existing rows (sidecar/Patriot) were
preserved.  By default existing property.parquet rows take precedence
over L3 rows for the same parcel_id (sidecar wins) — pass
``--replace-existing`` to flip that.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scrapers.property_l3_promoter import PropertyL3Promoter


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Promote MassGIS L3 CAMA -> property.parquet for one or more towns.",
    )
    parser.add_argument(
        "town_slugs", nargs="+",
        help="One or more kebab-case town slugs (e.g. arlington-ma lexington-ma)",
    )
    parser.add_argument(
        "--replace-existing", action="store_true",
        help="Let L3 rows OVERWRITE existing property.parquet rows for the same "
             "parcel_id.  Default is to preserve existing rows (Patriot/sidecar wins).",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Reduce log verbosity to warnings only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    print("=" * 78)
    print("  Tier 5 Path A — L3 CAMA -> property.parquet")
    print(f"  towns            : {', '.join(args.town_slugs)}")
    print(f"  preserve_existing: {not args.replace_existing}")
    print("=" * 78)

    summary_rows = []
    for slug in args.town_slugs:
        print(f"\n--- {slug} ---")
        t0 = time.perf_counter()
        promoter = PropertyL3Promoter(
            town_slug=slug,
            preserve_existing=not args.replace_existing,
        )
        result = promoter.run()
        elapsed = time.perf_counter() - t0

        print(f"  parcels with L3 data : {result['parcels_with_l3']:>7,}")
        print(f"  rows promoted        : {result['rows_promoted']:>7,}")
        print(f"  rows kept (existing) : {result['rows_kept_from_existing']:>7,}")
        print(f"  -> {result['output_path']}")
        print(f"  ({elapsed:.1f}s)")
        summary_rows.append((slug, result["parcels_with_l3"],
                             result["rows_promoted"],
                             result["rows_kept_from_existing"], elapsed))

    print(f"\n{'=' * 78}")
    print("  ALL TOWNS — Path A summary")
    print(f"{'=' * 78}")
    print(f"  {'town':<20s} {'L3 parcels':>12s} {'promoted':>12s} {'kept':>8s} {'elapsed':>8s}")
    for slug, lc, pc, kc, dt in summary_rows:
        print(f"  {slug:<20s} {lc:>12,} {pc:>12,} {kc:>8,} {dt:>7.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
