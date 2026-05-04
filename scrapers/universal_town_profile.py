# [FILE PATH]: scrapers/universal_town_profile.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 11: Town Profile (LLM-synthesised)
# Date: 2026-03-03
"""
Universal CLI entry-point for the Town Profile pipeline (Domain 11).

Usage
-----
    python scrapers/universal_town_profile.py --town arlington-ma
    python scrapers/universal_town_profile.py --town waltham-ma --provider gemini
    python scrapers/universal_town_profile.py --town lexington-ma --provider openai --model gpt-4o
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.town_profile_ingestor import ArlingtonTownProfileIngestor
from core.identity_linker import get_linker

TownProfileIngestor = ArlingtonTownProfileIngestor

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 11: Town Profile")
    p.add_argument("--town", required=True, help="Kebab-case town slug")
    p.add_argument("--output-dir", default="data/gold")
    p.add_argument("--provider", choices=["gemini", "openai", "anthropic"], default=None,
                   help="LLM backend (auto-detected from env vars when omitted)")
    p.add_argument("--model", default=None, help="Override LLM model name")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    out = ArlingtonTownProfileIngestor(
        town_slug=args.town,
        linker=get_linker(),
        provider=args.provider,
        model=args.model,
    ).run(output_dir=args.output_dir)
    print(f"[universal_town_profile] ✓  {out}")


if __name__ == "__main__":
    main()
