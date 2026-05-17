# [FILE PATH]: scrapers/universal_macris.py
# Patch #200
# Execution Mode: Universal Scraper — Domain 16: MACRIS Historic Resources
# Date: 2026-05-07
"""
Universal CLI entry-point for the MACRIS Historic Resources pipeline (Domain 16).

The actual ingestor lives in ``scrapers.macris_scraper``;
this module only provides the argparse CLI and the registry-friendly
``Arlington…`` alias.

Usage
-----
    python scrapers/universal_macris.py --town arlington-ma
    python scrapers/universal_macris.py --town somerville-ma --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.identity_linker import get_linker
from scrapers.macris_scraper import ArlingtonMacrisScraper

MacrisScraper = ArlingtonMacrisScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 16: MACRIS Historic Resources")
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

    out = ArlingtonMacrisScraper(
        town_slug=args.town, linker=get_linker()
    ).run(output_dir=args.output_dir)
    print(f"[universal_macris] OK  {out}")


if __name__ == "__main__":
    main()
