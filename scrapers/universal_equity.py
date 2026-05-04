# [FILE PATH]: scrapers/universal_equity.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 10: Social Equity / EJ Burden Indices
# Date: 2026-03-03
"""
Universal CLI entry-point for the Social Equity / EJScreen pipeline (Domain 10).

Usage
-----
    python scrapers/universal_equity.py --town arlington-ma
    python scrapers/universal_equity.py --town waltham-ma --bronze-dir data/bronze --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.equity_ingestor import ArlingtonEquityIngestor
from core.identity_linker import get_linker

EquityIngestor = ArlingtonEquityIngestor

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 10: Social Equity / EJ Index")
    p.add_argument("--town", required=True, help="Kebab-case town slug")
    p.add_argument("--bronze-dir", default="data/bronze")
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

    out = ArlingtonEquityIngestor(town_slug=args.town, linker=get_linker()).run(
        bronze_dir=args.bronze_dir,
        output_dir=args.output_dir,
    )
    print(f"[universal_equity] ✓  {out}")


if __name__ == "__main__":
    main()
