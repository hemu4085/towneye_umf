# [FILE PATH]: scrapers/universal_str.py
# Patch #185
# Execution Mode: Universal Scraper — Domain 12: STR Dynamics (LLM-synthesised)
# Date: 2026-03-03
"""
Universal CLI entry-point for the STR Dynamics pipeline (Domain 12).

Usage
-----
    python scrapers/universal_str.py --town arlington-ma
    python scrapers/universal_str.py --town waltham-ma --provider gemini
    python scrapers/universal_str.py --town arlington-ma --month 2026-03
"""

import argparse
import logging
import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scrapers.str_ingestor import ArlingtonStrDynamicsIngestor
from core.identity_linker import get_linker

StrDynamicsIngestor = ArlingtonStrDynamicsIngestor

logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="TownEye — Domain 12: STR Dynamics")
    p.add_argument("--town", required=True, help="Kebab-case town slug")
    p.add_argument("--output-dir", default="data/gold")
    p.add_argument("--provider", choices=["gemini", "openai", "anthropic"], default=None,
                   help="LLM backend (auto-detected from env vars when omitted)")
    p.add_argument("--model", default=None, help="Override LLM model name")
    p.add_argument("--month", default=None,
                   help="Observation month YYYY-MM (defaults to current month)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    out = ArlingtonStrDynamicsIngestor(
        town_slug=args.town,
        linker=get_linker(),
        provider=args.provider,
        model=args.model,
    ).run(observation_month=args.month, output_dir=args.output_dir)
    print(f"[universal_str] ✓  {out}")


if __name__ == "__main__":
    main()
