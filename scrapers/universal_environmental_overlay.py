# [FILE PATH]: scrapers/universal_environmental_overlay.py
# Patch #203
# Execution Mode: Universal Scraper — Domain 19: Environmental Overlay
# Date: 2026-05-07
"""Universal CLI for Domain 19 (Environmental Overlay — wetlands + flood)."""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.identity_linker import get_linker
from scrapers.environmental_overlay_scraper import ArlingtonEnvironmentalOverlayScraper

EnvironmentalOverlayScraper = ArlingtonEnvironmentalOverlayScraper

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(
        description="TownEye — Domain 19: Environmental Overlay (wetlands + flood)",
    )
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

    out = ArlingtonEnvironmentalOverlayScraper(
        town_slug=args.town, linker=get_linker()
    ).run(output_dir=args.output_dir)
    print(f"[universal_environmental_overlay] OK  {out}")


if __name__ == "__main__":
    main()
