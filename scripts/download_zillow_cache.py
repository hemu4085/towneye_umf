#!/usr/bin/env python3
"""
scripts/download_zillow_cache.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
One-time download of the Zillow ZHVI (Home Value Index) CSV for a given town.

Streams the national Zillow CSV, filters rows whose zip code appears in the
town's config ``market_dynamics.zip_codes``, and writes a compact cache to
``data/cache/{town_slug}/zillow_zhvi.csv``.

Usage
-----
    python scripts/download_zillow_cache.py --town arlington-ma
    python scripts/download_zillow_cache.py --town arlington-ma --months 36

The cached CSV has three columns:
    zip_code, observation_date, median_home_value

Run this script whenever you want to refresh the Zillow data (e.g. monthly).
The market ingestor (scrapers/market_ingestor.py) reads this cache
automatically before falling back to synthetic data.
"""
import argparse
import csv
import io
import logging
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config_loader import ConfigLoader

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_MONTHS = 60   # 5 years — enough for historical timeline + 3-yr projection
_CHUNK_SIZE = 65536  # 64 KB


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Zillow ZHVI cache for a town.")
    parser.add_argument("--town", required=True, help="Town slug, e.g. arlington-ma")
    parser.add_argument(
        "--months", type=int, default=_DEFAULT_MONTHS,
        help=f"How many trailing months to keep (default: {_DEFAULT_MONTHS})",
    )
    parser.add_argument("--config-dir", default="configs", help="Path to configs/ directory")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    loader = ConfigLoader(base_dir=args.config_dir)
    cfg = loader.get_town_config(args.town)

    zip_codes: list[str] = cfg.get("market_dynamics", {}).get("zip_codes", [])
    if not zip_codes:
        logger.error("No zip_codes configured under market_dynamics for '%s'. Aborting.", args.town)
        sys.exit(1)

    zhvi_url: str = cfg.get("scraper_urls", {}).get("zillow_zhvi_csv", "")
    if not zhvi_url:
        logger.error("No zillow_zhvi_csv URL in scraper_urls for '%s'. Aborting.", args.town)
        sys.exit(1)

    out_dir = _ROOT / "data" / "cache" / args.town
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "zillow_zhvi.csv"

    logger.info("Town   : %s", args.town)
    logger.info("Zips   : %s", zip_codes)
    logger.info("URL    : %s", zhvi_url)
    logger.info("Output : %s", out_path)
    logger.info("Months : %d", args.months)
    logger.info("Streaming Zillow ZHVI CSV (national file, ~60 MB — this may take 30–60 s)...")

    import requests

    zip_codes_set = set(zip_codes)
    found: dict[str, list[str]] = {}   # zip → list of (date, value) pairs
    header: list[str] | None = None
    date_cols: list[tuple[int, str]] = []  # (col_index, date_str)
    bytes_read = 0

    with requests.get(zhvi_url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        partial_line = b""

        for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
            bytes_read += len(chunk)
            data = partial_line + chunk
            lines = data.split(b"\n")
            partial_line = lines.pop()  # last (possibly incomplete) line

            for raw_line in lines:
                line_str = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                if not line_str:
                    continue

                row = next(csv.reader(io.StringIO(line_str)))

                if header is None:
                    header = row
                    # Identify date columns (format: YYYY-MM-DD) starting at index 9
                    for idx, col in enumerate(header):
                        if idx >= 9 and len(col) == 10 and col[4] == "-":
                            date_cols.append((idx, col))
                    if args.months > 0:
                        date_cols = date_cols[-args.months:]
                    logger.info("CSV header parsed. %d date columns kept.", len(date_cols))
                    continue

                # RegionName (index 2) = zip code
                if len(row) > 2 and row[2] in zip_codes_set:
                    zip_code = row[2]
                    pairs: list[tuple[str, str]] = []
                    for col_idx, date_str in date_cols:
                        if col_idx < len(row) and row[col_idx]:
                            pairs.append((date_str, row[col_idx]))
                    found[zip_code] = pairs
                    logger.info("  ✅ Found zip %s — %d monthly values", zip_code, len(pairs))

                    if len(found) == len(zip_codes_set):
                        logger.info("All target zip codes found after %.1f MB.", bytes_read / 1e6)
                        break

            if len(found) == len(zip_codes_set):
                break

    if not found:
        logger.error(
            "No matching zip codes found in Zillow CSV after reading %.1f MB. "
            "Check that zip codes %s are correct.",
            bytes_read / 1e6, zip_codes,
        )
        sys.exit(1)

    missing = zip_codes_set - set(found)
    if missing:
        logger.warning("Zip code(s) not found in Zillow data: %s", sorted(missing))

    # Write compact cache
    rows_written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["zip_code", "observation_date", "median_home_value"])
        for zip_code, pairs in sorted(found.items()):
            for date_str, value in pairs:
                writer.writerow([zip_code, date_str, value])
                rows_written += 1

    logger.info("Wrote %d rows → %s", rows_written, out_path)
    logger.info("Done. Re-run scrapers/universal_market.py to update market-trends.parquet.")


if __name__ == "__main__":
    main()
