# [FILE PATH]: scrapers/universal_permits.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 05: Permit Velocity / Building Permits
# Date: 2026-03-03
"""
Universal CLI entry-point for the Building Permits pipeline (Domain 05).

Usage
-----
    python scrapers/universal_permits.py --town arlington-ma
    python scrapers/universal_permits.py --town waltham-ma --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.permits_scraper import ArlingtonPermitScraper
from core.identity_linker import get_linker

PermitScraper = ArlingtonPermitScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 05: Permit Velocity")
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

    out = ArlingtonPermitScraper(town_slug=args.town, linker=get_linker()).run(
        output_dir=args.output_dir
    )
    print(f"[universal_permits] ✓  {out}")


if __name__ == "__main__":
    main()
