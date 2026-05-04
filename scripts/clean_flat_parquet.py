# [FILE PATH]: scripts/clean_flat_parquet.py
# Patch #184
# Execution Mode: Clean up pre-partitioning flat Parquet files
# Date: 2026-03-03
"""
Remove the old, unpartitioned Parquet files that were produced before
Patch #184 introduced the town-partitioned data lake layout.

Old layout (deleted by this script)
-------------------------------------
    data/gold/{town_slug}-{domain}.parquet       e.g. arlington-ma-zoning.parquet
    data/bronze/{town_slug}-{domain}.parquet     e.g. arlington-ma-equity-bronze.parquet

New layout (kept untouched)
-----------------------------
    data/gold/{town_slug}/{domain}.parquet       e.g. arlington-ma/zoning.parquet
    data/bronze/{town_slug}/{domain}.parquet     e.g. arlington-ma/equity-bronze.parquet

Usage
-----
    python scripts/clean_flat_parquet.py              # dry-run (safe, no deletion)
    python scripts/clean_flat_parquet.py --delete     # actually delete the files
"""

import argparse
import pathlib
import sys


def _collect_flat_parquets(tier_root: pathlib.Path) -> list[pathlib.Path]:
    """
    Collect all *.parquet files sitting directly inside *tier_root*
    (i.e. the old flat layout), ignoring files inside sub-directories
    (which are the new partitioned layout).
    """
    if not tier_root.exists():
        return []
    return [p for p in tier_root.glob("*.parquet") if p.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove old flat Parquet files from data/gold and data/bronze."
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        default=False,
        help="Actually delete files (default: dry-run — only lists them).",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        default=["gold", "bronze"],
        help="Tiers to clean (default: gold bronze).",
    )
    args = parser.parse_args()

    targets: list[pathlib.Path] = []
    for tier in args.tiers:
        tier_root = pathlib.Path("data") / tier
        flat_files = _collect_flat_parquets(tier_root)
        targets.extend(flat_files)

    if not targets:
        print("No flat Parquet files found — nothing to clean.")
        return

    print(f"{'DRY RUN — ' if not args.delete else ''}Found {len(targets)} flat Parquet file(s):\n")
    for path in sorted(targets):
        print(f"  {'[DELETE]' if args.delete else '[would delete]'}  {path}")

    if not args.delete:
        print(
            "\nRun with --delete to remove these files.\n"
            "New partitioned files live at data/{tier}/{town_slug}/{domain}.parquet"
        )
        return

    deleted = 0
    errors  = 0
    for path in targets:
        try:
            path.unlink()
            deleted += 1
        except OSError as exc:
            print(f"  ERROR deleting {path}: {exc}", file=sys.stderr)
            errors += 1

    print(f"\nDeleted {deleted} file(s). Errors: {errors}.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
