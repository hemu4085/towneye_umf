#!/usr/bin/env python3
"""
Convert an existing buildability brief HTML file to PDF.

Optionally replace the header recipient name and date before rendering.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from reports.html_to_pdf import convert_html_to_pdf, pdf_output_path  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a buildability brief HTML file to PDF.",
    )
    parser.add_argument("html", help="Input HTML path.")
    parser.add_argument(
        "-o", "--output",
        default=None,
        help=(
            "Output PDF path.  Default: same name as HTML with .pdf, or "
            "{html_stem}_{first_name}.pdf when --prepared-for is set."
        ),
    )
    parser.add_argument(
        "--prepared-for",
        default=None,
        help="Replace the header recipient name (e.g. 'Jane Smith').",
    )
    parser.add_argument(
        "--prepared-on",
        default=None,
        help="Replace the header date (YYYY-MM-DD). Defaults to today when --prepared-for is set.",
    )
    parser.add_argument(
        "--no-prepared-for",
        action="store_true",
        help="Remove the 'Prepared for …' line from the header.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    html_path = Path(args.html)
    if not html_path.is_absolute():
        html_path = REPO_ROOT / html_path

    pdf_path = Path(args.output) if args.output else pdf_output_path(
        html_path,
        prepared_for=None if args.no_prepared_for else args.prepared_for,
    )
    if not pdf_path.is_absolute():
        pdf_path = REPO_ROOT / pdf_path

    prepared_on: date | None = None
    if args.prepared_on:
        prepared_on = date.fromisoformat(args.prepared_on)
    elif args.prepared_for and not args.no_prepared_for:
        prepared_on = date.today()

    try:
        convert_html_to_pdf(
            html_path,
            pdf_path,
            prepared_for=args.prepared_for,
            prepared_on=prepared_on,
            remove_prepared_for=args.no_prepared_for,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    try:
        display = pdf_path.relative_to(REPO_ROOT)
    except ValueError:
        display = pdf_path
    if args.prepared_for and not args.no_prepared_for:
        print(f"Prepared for: {args.prepared_for.strip()}")
    print(f"PDF saved → {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
