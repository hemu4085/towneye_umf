# [FILE PATH]: scrapers/universal_zoning.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 02: Regulatory Layer / Zoning Bylaws
# Date: 2026-03-03
"""
Universal CLI entry-point for the Zoning Bylaws pipeline (Domain 02).

Usage
-----
    python scrapers/universal_zoning.py --town arlington-ma
    python scrapers/universal_zoning.py --town waltham-ma --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.zoning_scraper import ArlingtonZoningScraper
from core.identity_linker import get_linker

ZoningScraper = ArlingtonZoningScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 02: Zoning Bylaws")
    p.add_argument("--town", required=True, help="Kebab-case town slug")
    p.add_argument("--output-dir", default="data/gold")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    out = ArlingtonZoningScraper(town_slug=args.town, linker=get_linker()).run(
        output_dir=args.output_dir
    )
    print(f"[universal_zoning] ✓  {out}")


if __name__ == "__main__":
    main()
