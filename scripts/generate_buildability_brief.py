# [FILE PATH]: scripts/generate_buildability_brief.py
# Patch #205
# Execution Mode: Tier 4 — Buildability Brief CLI Driver
# Date: 2026-05-07
"""
CLI driver for ``reports.buildability_brief.BuildabilityBriefGenerator``.

Examples
--------
    # 29 Walnut St, Arlington MA (the reference parcel from Tier 0):
    .venv/bin/python scripts/generate_buildability_brief.py \\
        --town arlington-ma \\
        --parcel-id 128.0-0003-0012.0 \\
        --prepared-for "Julie Gibson" \\
        --output reports/output/29_walnut_buildability_brief_v2.html

    # Any other Arlington parcel — same command, new --parcel-id:
    .venv/bin/python scripts/generate_buildability_brief.py \\
        --town arlington-ma \\
        --parcel-id 141.0-0002-0011.0 \\
        --output reports/output/29_walnut_terr_buildability_brief.html

The driver resolves output paths under the repo root; pass ``--print`` to
dump the HTML to stdout instead of writing to disk.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a parcel buildability brief from the Tier 2 Gold lake.",
    )
    parser.add_argument("--town", required=True, help="Town slug (e.g. arlington-ma).")
    parser.add_argument("--parcel-id", required=True, help="Parcel natural key.")
    parser.add_argument("--prepared-for", default=None, help="Recipient name for the header.")
    parser.add_argument(
        "--prepared-on",
        default=None,
        help="ISO date (YYYY-MM-DD) for the header.  Defaults to today.",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output HTML path.  Defaults to reports/output/<slug>_buildability_brief.html.",
    )
    parser.add_argument(
        "--print", dest="print_html", action="store_true",
        help="Print the rendered HTML to stdout instead of writing a file.",
    )
    parser.add_argument(
        "--data-dir", default="data/gold",
        help="Root of the Gold parquet lake (default: data/gold).",
    )
    return parser.parse_args()


def _default_output(parcel_id: str) -> Path:
    """Stable filename derived from the parcel id."""
    safe = parcel_id.replace("/", "_").replace(" ", "_")
    return REPO_ROOT / "reports" / "output" / f"{safe}_buildability_brief.html"


def main() -> int:
    args = _parse_args()
    prepared_on = date.fromisoformat(args.prepared_on) if args.prepared_on else None

    generator = BuildabilityBriefGenerator(
        town_slug=args.town,
        data_dir=args.data_dir,
    )
    inputs = BriefInputs(
        town_slug=args.town,
        parcel_id=args.parcel_id,
        prepared_for=args.prepared_for,
        prepared_on=prepared_on,
    )
    html = generator.generate(inputs)

    if args.print_html:
        print(html)
        return 0

    out_path = Path(args.output) if args.output else _default_output(args.parcel_id)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    data = generator.collect_data(inputs)
    summary = data.raw_stack.summary_one_liner()
    print(f"[OK] Wrote {out_path.relative_to(REPO_ROOT)} ({len(html):,} bytes)")
    print(f"     Stack summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
