#!/usr/bin/env python3
"""
Generate one agent PDF from the 29 Walnut buildability brief.

Usage:
    .venv/bin/python scripts/export_agent_brief.py "Jane Smith"

Creates:
    reports/output/29_walnut_buildability_brief_for_jane_smith.pdf
    with header: Prepared for Jane Smith
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HTML = REPO_ROOT / "reports" / "output" / "29_walnut_buildability_brief.html"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "output"

sys.path.insert(0, str(REPO_ROOT))

from reports.html_to_pdf import agent_brief_pdf_path, export_agent_brief  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Generate 29_walnut_buildability_brief_for_<name>.pdf for one agent.',
        usage='%(prog)s "Jane Smith"',
    )
    parser.add_argument(
        "name",
        help='Agent name, e.g. "Jane Smith"',
    )
    parser.add_argument(
        "--prepared-on",
        default=None,
        help="Header date YYYY-MM-DD (default: today).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    agent_name = args.name.strip()
    prepared_on = date.fromisoformat(args.prepared_on) if args.prepared_on else None

    if not DEFAULT_HTML.is_file():
        print(f"[ERROR] Brief HTML not found: {DEFAULT_HTML}", file=sys.stderr)
        return 1

    try:
        written = export_agent_brief(
            DEFAULT_HTML,
            agent_name,
            prepared_on=prepared_on,
            output_dir=DEFAULT_OUTPUT_DIR,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    expected = agent_brief_pdf_path(agent_name, DEFAULT_OUTPUT_DIR)
    if written != expected:
        print(f"[WARN] Unexpected output path: {written}", file=sys.stderr)

    try:
        display = written.relative_to(REPO_ROOT)
    except ValueError:
        display = written

    print(f"Prepared for: {agent_name}")
    print(f"PDF saved → {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
