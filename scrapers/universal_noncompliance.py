# [FILE PATH]: scrapers/universal_noncompliance.py
# Patch #201
# Execution Mode: Universal Scraper — Domain 17: Land-Use Non-Compliance
# Date: 2026-05-07
"""
Universal CLI for the Land-Use / Zoning Non-Compliance pipeline (Domain 17).
Logic lives in ``scrapers.noncompliance_scraper``; this file only provides
argparse + the registry-friendly ``Arlington…`` alias.
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.identity_linker import get_linker
from scrapers.noncompliance_scraper import ArlingtonNonComplianceScraper

NonComplianceScraper = ArlingtonNonComplianceScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 17: Land-Use Non-Compliance")
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

    out = ArlingtonNonComplianceScraper(
        town_slug=args.town, linker=get_linker()
    ).run(output_dir=args.output_dir)
    print(f"[universal_noncompliance] OK  {out}")


if __name__ == "__main__":
    main()
