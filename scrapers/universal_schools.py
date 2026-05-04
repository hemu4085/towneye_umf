# [FILE PATH]: scrapers/universal_schools.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 09: Economic Pulse / School Calendar ICS
# Date: 2026-03-03
"""
Universal CLI entry-point for the School Calendar ICS pipeline (Domain 09).

Usage
-----
    python scrapers/universal_schools.py --town arlington-ma
    python scrapers/universal_schools.py --town waltham-ma --output-dir data/gold
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.schools_ingestor import ArlingtonSchoolCalendarIngestor
from core.identity_linker import get_linker

SchoolCalendarIngestor = ArlingtonSchoolCalendarIngestor

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 09: School Calendar ICS")
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

    out = ArlingtonSchoolCalendarIngestor(town_slug=args.town, linker=get_linker()).run(
        output_dir=args.output_dir
    )
    print(f"[universal_schools] ✓  {out}")


if __name__ == "__main__":
    main()
