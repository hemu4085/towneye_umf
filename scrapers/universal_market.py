# [FILE PATH]: scrapers/universal_market.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 03: Market Dynamics / MLS Trends
# Date: 2026-03-03
"""
Universal CLI entry-point for the Market Dynamics pipeline (Domain 03).

Usage
-----
    python scrapers/universal_market.py --town arlington-ma
    python scrapers/universal_market.py --town waltham-ma --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.market_ingestor import ArlingtonMarketIngestor
from core.identity_linker import get_linker

MarketIngestor = ArlingtonMarketIngestor

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 03: Market Dynamics")
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

    out = ArlingtonMarketIngestor(town_slug=args.town, linker=get_linker()).run(
        output_dir=args.output_dir
    )
    print(f"[universal_market] ✓  {out}")


if __name__ == "__main__":
    main()
