"""
scripts/download_ejscreen_csv.py
=================================
Downloads a preserved environmental-justice dataset, filters it to
Massachusetts, and caches it as a Parquet file at:

    data/bronze/ejscreen/ma_block_groups.parquet

Data source
-----------
Primary:  CDC Environmental Justice Index (EJI) 2024 — national CSV archived
          on Zenodo by EDGI after CDC removed public access in 2025.
          URL: https://zenodo.org/api/records/14675861/files/EJI_2024_United_States.csv/content
          ~80 MB uncompressed CSV, tract-level GEOID, environmental burden scores.

Why not EJScreen?
-----------------
The EPA permanently removed ejscreen.epa.gov (and all gaftp.epa.gov/EJScreen/
files) on 2025-02-05 when the Trump administration eliminated EJ programs.
The domain no longer resolves in DNS globally.

Usage:
    python scripts/download_ejscreen_csv.py [--force]

Options:
    --force   Re-download even if the cached file already exists.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

import pandas as pd
import requests

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | [download_ejscreen] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

# CDC EJI 2024 — preserved on Zenodo by EDGI (CC0 licence)
_EJI_CSV_URL = (
    "https://zenodo.org/api/records/14675861/files/"
    "EJI_2024_United_States.csv/content"
)

_OUT_PATH = pathlib.Path("data/bronze/ejscreen/ma_block_groups.parquet")

# Massachusetts FIPS state prefix = "25"
_MA_STATE_PREFIX = "25"

# CDC EJI uses "GEOID" (11-char census tract FIPS) and "StateAbbr"
_STATE_COL_CANDIDATES = ("STATEABBR", "StateAbbr", "STATE", "state", "ST")
_GEOID_COL_CANDIDATES  = ("GEOID", "ID", "FIPS", "fips", "geoid")

# ── helpers ──────────────────────────────────────────────────────────────────


def _download_csv(url: str) -> pd.DataFrame:
    """Stream the CSV and return an in-memory DataFrame filtered to MA."""
    logger.info("Downloading CDC EJI 2024 national CSV …")
    logger.info("URL: %s", url)
    logger.info("(~80 MB — this will take 1–3 minutes)")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TownEye/1.0; +https://towneye.com/bot)"
        )
    }

    with requests.get(url, headers=headers, timeout=300, stream=True) as resp:
        resp.raise_for_status()

        # --- probe first 5 rows to discover column names -----------------
        probe_chunks: list[bytes] = []
        downloaded = 0
        for chunk in resp.iter_content(chunk_size=1 << 20):
            probe_chunks.append(chunk)
            downloaded += len(chunk)
            if downloaded >= 5 << 20:  # 5 MB is enough to get headers
                break

        probe_data = b"".join(probe_chunks)
        import io
        probe_df = pd.read_csv(io.BytesIO(probe_data), nrows=5, encoding="latin-1",
                                on_bad_lines="skip")
        logger.info("Columns (first 20): %s", list(probe_df.columns[:20]))

        state_col = next((c for c in _STATE_COL_CANDIDATES if c in probe_df.columns), None)
        geoid_col = next((c for c in _GEOID_COL_CANDIDATES if c in probe_df.columns), None)

        logger.info("State column: %s | GEOID column: %s", state_col, geoid_col)

    # --- full re-download in chunks, filtering to MA ---------------------
    logger.info("Re-downloading and filtering to Massachusetts …")
    ma_chunks: list[pd.DataFrame] = []
    total_rows = 0

    with requests.get(url, headers=headers, timeout=300, stream=True) as resp:
        resp.raise_for_status()
        content = resp.content

    full_df_iter = pd.read_csv(
        io.BytesIO(content),
        dtype=str,
        chunksize=50_000,
        encoding="latin-1",
        on_bad_lines="skip",
    )

    for chunk in full_df_iter:
        total_rows += len(chunk)
        if state_col and state_col in chunk.columns:
            ma_chunk = chunk[chunk[state_col].str.strip().str.upper() == "MA"]
        elif geoid_col and geoid_col in chunk.columns:
            ma_chunk = chunk[chunk[geoid_col].astype(str).str.startswith(_MA_STATE_PREFIX, na=False)]
        else:
            # last resort: try any column that looks like a GEOID
            id_col = next((c for c in chunk.columns if "GEOID" in c.upper() or c.upper() == "ID"), None)
            if id_col:
                ma_chunk = chunk[chunk[id_col].astype(str).str.startswith(_MA_STATE_PREFIX, na=False)]
            else:
                ma_chunk = pd.DataFrame()

        if not ma_chunk.empty:
            ma_chunks.append(ma_chunk)

    logger.info("Scanned %d total rows.", total_rows)

    if not ma_chunks:
        raise ValueError(
            "No Massachusetts rows found.  "
            f"Expected state column '{state_col}' with value 'MA', "
            f"or GEOID column starting with '{_MA_STATE_PREFIX}'."
        )

    df = pd.concat(ma_chunks, ignore_index=True)
    logger.info("MA tracts: %d rows, %d columns", len(df), len(df.columns))
    return df


def _coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    """Convert obviously numeric columns from str to float."""
    skip = {"GEOID", "ID", "FIPS", "StateAbbr", "STATEABBR", "STATE", "County", "CountyFIPS"}
    for col in df.columns:
        if col in skip:
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        # Only replace the column if at least half the non-null values converted successfully
        if converted.notna().sum() >= df[col].notna().sum() * 0.5:
            df[col] = converted
    return df


def _save(df: pd.DataFrame, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info("Saved → %s  (%d rows, %d cols)", out_path, len(df), len(df.columns))


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the cached Parquet already exists.",
    )
    args = parser.parse_args()

    if _OUT_PATH.exists() and not args.force:
        logger.info(
            "Cache hit: %s already exists. Use --force to refresh.", _OUT_PATH
        )
        df = pd.read_parquet(_OUT_PATH)
        logger.info("Cached file has %d rows, %d columns.", len(df), len(df.columns))
        # show GEOID / ID column so the user can verify
        for candidate in _GEOID_COL_CANDIDATES:
            if candidate in df.columns:
                logger.info("Sample GEOIDs: %s", df[candidate].head(3).tolist())
                break
        return

    df = _download_csv(_EJI_CSV_URL)
    df = _coerce_numerics(df)
    _save(df, _OUT_PATH)

    print()
    print("=" * 60)
    print("EJI MA cache built")
    print("=" * 60)
    print(f"  File   : {_OUT_PATH}")
    print(f"  Rows   : {len(df):,}")
    print(f"  Cols   : {len(df.columns)}")
    print(f"  Source : CDC EJI 2024 (Zenodo / EDGI)")
    print("=" * 60)


if __name__ == "__main__":
    main()
