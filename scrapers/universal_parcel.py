# [FILE PATH]: scrapers/universal_parcel.py
# Patch #198
# Execution Mode: Universal Scraper — Domain 14: Parcel Geometry
# Date: 2026-05-07
"""
Universal CLI entry-point for the Parcel Geometry pipeline (Domain 14).

The actual ingestor logic lives in ``scrapers.parcel_scraper``;
this module only provides the argparse CLI and re-exports the class
under the registry-expected ``Arlington…`` alias.

Usage
-----
    python scrapers/universal_parcel.py --town arlington-ma
    python scrapers/universal_parcel.py --town somerville-ma --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.identity_linker import get_linker
from scrapers.parcel_scraper import ArlingtonParcelScraper

ParcelScraper = ArlingtonParcelScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 14: Parcel Geometry")
    p.add_argument("--town", required=True, help="Kebab-case town slug")
    p.add_argument("--output-dir", default="data/gold")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    out = ArlingtonParcelScraper(
        town_slug=args.town, linker=get_linker()
    ).run(output_dir=args.output_dir)
    print(f"[universal_parcel] OK  {out}")


if __name__ == "__main__":
    main()
