# [FILE PATH]: scrapers/ingest_civic_minutes.py
import argparse
import logging
import sys

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.civic_minutes_scraper import CivicMinutesScraper

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    parser = argparse.ArgumentParser(description="Ingest Domain 13: Civic Minutes / LLM Extraction")
    parser.add_argument("--town", required=True, help="Town slug (e.g. arlington-ma)")
    args = parser.parse_args()

    scraper = CivicMinutesScraper(town_slug=args.town)
    scraper.run()

if __name__ == "__main__":
    sys.exit(main())
