# [FILE PATH]: scrapers/universal_local_historic.py
# Patch #202
# Execution Mode: Universal Scraper — Domain 18: Local Historic Resources
# Date: 2026-05-07
"""Universal CLI for Domain 18 (Local Historic — multi-FS aggregator)."""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.identity_linker import get_linker
from scrapers.local_historic_scraper import ArlingtonLocalHistoricScraper

LocalHistoricScraper = ArlingtonLocalHistoricScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 18: Local Historic Resources")
    p.add_argument("--town", required=True)
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

    out = ArlingtonLocalHistoricScraper(
        town_slug=args.town, linker=get_linker()
    ).run(output_dir=args.output_dir)
    print(f"[universal_local_historic] OK  {out}")


if __name__ == "__main__":
    main()
