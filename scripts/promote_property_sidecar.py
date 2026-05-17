# [FILE PATH]: scripts/promote_property_sidecar.py
# Patch #206
# Execution Mode: Tier 4.5 — CLI Driver for the Property Sidecar Promoter
# Date: 2026-05-07
"""
CLI driver for ``scrapers.property_sidecar.PropertySidecarPromoter``.

Examples
--------
    # Promote every assessor.json file under data/ for Arlington:
    .venv/bin/python scripts/promote_property_sidecar.py --town arlington-ma

    # Promote a specific sidecar file (skips the discovery walk):
    .venv/bin/python scripts/promote_property_sidecar.py \\
        --town arlington-ma \\
        --file data/29_walnut/assessor.json

    # Dry run — show what would be promoted without writing the parquet:
    .venv/bin/python scripts/promote_property_sidecar.py \\
        --town arlington-ma --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scrapers.property_sidecar import PropertySidecarPromoter  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Promote pre-scraped assessor JSON sidecars into the town's "
            "Gold-tier property.parquet."
        ),
    )
    parser.add_argument("--town", required=True, help="Town slug (e.g. arlington-ma).")
    parser.add_argument(
        "--file", action="append", dest="explicit_files", default=[],
        help="Specific sidecar file to consume.  Repeat for multiple.",
    )
    parser.add_argument(
        "--glob", default="*/assessor.json",
        help="Discovery glob under --data-dir (default: */assessor.json).",
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="Bronze data root (default: data).",
    )
    parser.add_argument(
        "--gold-dir", default="data/gold",
        help="Gold parquet root (default: data/gold).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Discover + promote in memory but skip the parquet write.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable INFO-level logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        )

    explicit = [Path(p) for p in args.explicit_files] or None

    promoter = PropertySidecarPromoter(
        town_slug=args.town,
        data_dir=args.data_dir,
        gold_dir=args.gold_dir,
    )

    if args.dry_run:
        files = promoter.discover_sidecar_files(
            sidecar_glob=args.glob, explicit_paths=explicit,
        )
        records = []
        for f in files:
            records.extend(promoter.filter_by_source(promoter.load_records_from_file(f)))
        gold = promoter.promote_records(records)
        print(f"[DRY-RUN] files scanned : {len(files)}")
        print(f"[DRY-RUN] records found : {len(records)}")
        print(f"[DRY-RUN] would promote : {len(gold)} row(s)")
        for row in gold:
            md = row.get("metadata") or {}
            md_extras = ", ".join(
                f"{k}={md[k]!r}" for k in ("finished_area_sqft", "last_sale_date",
                                            "last_sale_price", "book_page")
                if k in md
            )
            print(
                f"  - parcel_id={row.get('parcel_id')!r}  "
                f"address={row.get('address')!r}  "
                f"owner={row.get('owner_name')!r}  "
                f"year={row.get('year_built')}  "
                f"lot={row.get('lot_size_sqft')}  "
                f"value={row.get('assessed_value')}  "
                f"[{md_extras}]"
            )
        return 0

    summary = promoter.run(sidecar_glob=args.glob, explicit_paths=explicit)
    print(f"[OK] files scanned   : {summary['files_scanned']}")
    print(f"     records promoted : {summary['records_promoted']}")
    if summary["parcel_ids"]:
        print(f"     parcel ids       : {summary['parcel_ids']}")
    out_path = summary["output_path"]
    rel = out_path.relative_to(REPO_ROOT) if str(out_path).startswith(str(REPO_ROOT)) else out_path
    print(f"     wrote            : {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
