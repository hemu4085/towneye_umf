# [FILE PATH]: scrapers/universal_property.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 01: Physical Foundation / Property Assessment
# Date: 2026-03-03
"""
Universal CLI entry-point for the Property Assessment pipeline (Domain 01).

The scraper class ``PropertyScraper`` lives in this module and delegates all
logic to the town-agnostic ``ArlingtonPropertyScraper`` implementation, which
reads every configuration value from ``configs/{town_slug}/config.yaml``.

Usage
-----
    python scrapers/universal_property.py --town arlington-ma
    python scrapers/universal_property.py --town waltham-ma --output-dir data/gold
    python scrapers/universal_property.py --town lexington-ma --max-pages 3

Zero-Hardcoding contract
------------------------
``town_slug`` is the only town-specific input. Everything else flows from config.
"""

import argparse
import json
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd

from scrapers.property_scraper import ArlingtonPropertyScraper
from core.identity_linker import get_linker

# Stable public alias used by master_loop.py
PropertyScraper = ArlingtonPropertyScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(
        description="TownEye — Domain 01: Property Assessment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python scrapers/universal_property.py --town arlington-ma",
    )
    p.add_argument("--town", required=True, help="Kebab-case town slug")
    p.add_argument("--output-dir", default="data/gold")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    scraper = ArlingtonPropertyScraper(town_slug=args.town, linker=get_linker())
    if args.max_pages is not None:
        scraper._max_pages = args.max_pages

    out = scraper.run(output_dir=args.output_dir)
    df = pd.read_parquet(out)
    print(f"\n── {len(df)} Gold TeParty record(s) → {out} ──")
    summary = [c for c in ["te_party_pk", "party_type", "legal_name", "te_source"]
               if c in df.columns]
    if summary:
        print(df[summary].head(5).to_string(index=False))
    if not df.empty:
        print("\n── First record ──")
        print(json.dumps(df.iloc[0].to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
