# [FILE PATH]: scripts/load_redfin_to_bq.py
# Patch #190
# Execution Mode: Load Real Market Data (Redfin to BigQuery)
# Date: 2026-03-04
"""
Downloads Redfin's public Zip Code Market Tracker dataset, filters it to
Massachusetts, and loads it into the BigQuery table
``towneye-umf.market_dynamics.mls_trends``.

After this script runs successfully, ``universal_market.py`` will serve
100% real Redfin data instead of synthetic fallback data.

Usage
-----
    # From project root, with .env sourced:
    set -a && source .env && set +a
    python scripts/load_redfin_to_bq.py

    # Dry-run — download and clean but skip the BQ upload:
    python scripts/load_redfin_to_bq.py --dry-run

    # Reload — truncate the table and re-upload (useful for monthly refresh):
    python scripts/load_redfin_to_bq.py --reload

Notes
-----
* The Redfin file is ~200 MB compressed / ~6.6 M rows total.
  The Massachusetts slice is ~93% smaller (~50 K rows).
* The script streams the file directly from S3 — no local disk write.
* Re-running without --reload appends new rows.  Use --reload for a clean
  monthly refresh.
* Column mapping is defined in _REDFIN_COLUMN_MAP — update it here if
  Redfin ever renames their headers.
"""

import argparse
import logging
import os
import pathlib
import sys
from typing import Any

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault(
    "GOOGLE_APPLICATION_CREDENTIALS",
    str(_PROJECT_ROOT / "gcp-key.json"),
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — zero hardcoding: all BQ coordinates live here, not in logic code
# ---------------------------------------------------------------------------
_GCP_PROJECT   = "towneye-umf"
_BQ_DATASET    = "market_dynamics"
_BQ_TABLE      = "mls_trends"
_STATE_FILTER  = "MA"
_REDFIN_URL    = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com"
    "/redfin_market_tracker/zip_code_market_tracker.tsv000.gz"
)

# ---------------------------------------------------------------------------
# Column mapping: Redfin TSV name  →  our mls_trends BQ column name
#
# Redfin uses ALL-CAPS column headers. Only these columns are kept from the
# 58-column file. The BQ schema is derived directly from this map.
# ---------------------------------------------------------------------------
_REDFIN_COLUMN_MAP: dict[str, str] = {
    "REGION":              "region",
    "STATE_CODE":          "state_code",        # two-letter code e.g. "MA" — used for filtering
    "STATE":               "state_name",        # full name e.g. "Massachusetts"
    "PERIOD_BEGIN":        "period_begin",
    "PERIOD_END":          "period_end",
    "MEDIAN_SALE_PRICE":   "median_sale_price",
    "MEDIAN_LIST_PRICE":   "median_list_price",
    "MEDIAN_PPSF":         "median_ppsf",
    "HOMES_SOLD":          "homes_sold",
    "PENDING_SALES":       "pending_sales",
    "NEW_LISTINGS":        "new_listings",
    "INVENTORY":           "inventory",
    "MONTHS_OF_SUPPLY":    "months_of_supply",
    "MEDIAN_DOM":          "median_dom",
    "AVG_SALE_TO_LIST":    "avg_sale_to_list",
    "SOLD_ABOVE_LIST":     "sold_above_list",
    "PRICE_DROPS":         "price_drops",
    "OFF_MARKET_IN_TWO_WEEKS": "off_market_in_two_weeks",
    "PROPERTY_TYPE":       "property_type",
}

# BigQuery schema — types must align with _REDFIN_COLUMN_MAP values
_BQ_SCHEMA_FIELDS: list[dict[str, str]] = [
    {"name": "region",                   "type": "STRING",  "mode": "NULLABLE"},
    {"name": "state_code",               "type": "STRING",  "mode": "NULLABLE"},
    {"name": "state_name",               "type": "STRING",  "mode": "NULLABLE"},
    {"name": "period_begin",             "type": "DATE",    "mode": "NULLABLE"},
    {"name": "period_end",               "type": "DATE",    "mode": "NULLABLE"},
    {"name": "property_type",            "type": "STRING",  "mode": "NULLABLE"},
    {"name": "median_sale_price",        "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "median_list_price",        "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "median_ppsf",              "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "homes_sold",               "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "pending_sales",            "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "new_listings",             "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "inventory",                "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "months_of_supply",         "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "median_dom",               "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "avg_sale_to_list",         "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "sold_above_list",          "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "price_drops",              "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "off_market_in_two_weeks",  "type": "FLOAT",   "mode": "NULLABLE"},
    {"name": "zipcode",                  "type": "STRING",  "mode": "NULLABLE"},
]

# Integer columns — coerced to nullable Int64 before upload to avoid float
# representation of whole numbers (e.g. 42.0 → 42)
_INT_COLS = {
    "homes_sold", "pending_sales", "new_listings",
    "inventory", "price_drops", "off_market_in_two_weeks",
}


# ---------------------------------------------------------------------------
# Step 1 — Create or verify the BQ table
# ---------------------------------------------------------------------------

def ensure_bq_table(client: Any, reload: bool) -> None:
    """Create ``mls_trends`` if it doesn't exist; truncate if --reload."""
    from google.cloud import bigquery
    from google.api_core.exceptions import NotFound

    table_ref = f"{client.project}.{_BQ_DATASET}.{_BQ_TABLE}"
    schema = [
        bigquery.SchemaField(f["name"], f["type"], mode=f["mode"])
        for f in _BQ_SCHEMA_FIELDS
    ]

    try:
        table = client.get_table(table_ref)
        if reload:
            # TRUNCATE TABLE is DML and requires billing — delete + recreate
            # instead, which works on the free tier.
            logger.info("[load_redfin] --reload: deleting and recreating %s …", table_ref)
            client.delete_table(table_ref)
            logger.info("[load_redfin] Table deleted.")
        else:
            logger.info("[load_redfin] Table %s already exists (%d rows).",
                        table_ref, table.num_rows)
            return
    except NotFound:
        logger.info("[load_redfin] Creating table %s …", table_ref)
        table = bigquery.Table(table_ref, schema=schema)
        # Partition by period_begin for efficient date-range queries
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.MONTH,
            field="period_begin",
        )
        table.clustering_fields = ["state_code", "zipcode"]
        client.create_table(table)
        logger.info("[load_redfin] Table created with monthly partitioning on period_begin.")


# ---------------------------------------------------------------------------
# Step 2 — Download, filter, and clean the Redfin data
# ---------------------------------------------------------------------------

def download_and_clean(state_filter: str = _STATE_FILTER):
    """
    Stream the Redfin TSV.gz directly from S3, filter to *state_filter*,
    keep only the columns in _REDFIN_COLUMN_MAP, and return a clean DataFrame.

    This avoids writing the full ~200 MB file to disk.
    """
    import pandas as pd

    logger.info("[load_redfin] Downloading Redfin data from S3 (chunked streaming) …")
    logger.info("[load_redfin] URL: %s", _REDFIN_URL)
    logger.info(
        "[load_redfin] Reading in 50k-row chunks and filtering to '%s' before accumulating. "
        "This avoids loading the full ~200 MB / 6.6 M row file into memory at once.",
        state_filter,
    )

    keep_cols = list(_REDFIN_COLUMN_MAP.keys())
    _CHUNK_SIZE = 50_000

    # STATE_CODE contains the two-letter abbreviation (e.g. "MA") used for filtering
    state_col = "STATE_CODE"

    filtered_chunks: list = []
    original_rows = 0
    chunk_num = 0

    reader = pd.read_csv(
        _REDFIN_URL,
        sep="\t",
        compression="infer",
        usecols=lambda c: c in keep_cols,
        low_memory=False,
        chunksize=_CHUNK_SIZE,
    )

    for chunk in reader:
        original_rows += len(chunk)
        chunk_num += 1
        ma_chunk = chunk[chunk[state_col] == state_filter]
        if not ma_chunk.empty:
            filtered_chunks.append(ma_chunk)
        if chunk_num % 20 == 0:
            logger.info(
                "[load_redfin] ... processed %d rows so far, kept %d %s rows.",
                original_rows,
                sum(len(c) for c in filtered_chunks),
                state_filter,
            )

    logger.info("[load_redfin] Scan complete — processed %d total rows.", original_rows)

    if not filtered_chunks:
        logger.error("[load_redfin] No rows found for state_code='%s'. Aborting.", state_filter)
        sys.exit(1)

    df = pd.concat(filtered_chunks, ignore_index=True)
    logger.info(
        "[load_redfin] Filtered to state_code='%s': %d rows (%.1f%% of total).",
        state_filter, len(df), 100 * len(df) / original_rows if original_rows else 0,
    )

    # Rename columns to BQ names (currently identical, but map ensures
    # forward-compatibility if Redfin ever renames a column)
    df = df.rename(columns=_REDFIN_COLUMN_MAP)
    # Extract 5-digit zipcode from the region string e.g. "Zip Code: 02474"
    df["zipcode"] = (
        df["region"]
        .str.extract(r"(\d{5})", expand=False)
        .fillna("")
    )

    # Coerce date columns
    for date_col in ("period_begin", "period_end"):
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # Coerce integer columns — use float64 with NaN (BQ load handles the
    # INTEGER schema cast server-side; avoids pandas nullable Int64 cast issues)
    for col in _INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce remaining numeric columns to float
    float_cols = {
        "median_sale_price", "median_list_price", "median_ppsf",
        "months_of_supply", "median_dom", "avg_sale_to_list", "sold_above_list",
    }
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows with no zipcode or no period_begin — they can't be queried usefully
    before = len(df)
    df = df[df["zipcode"].str.len() == 5]
    df = df[df["period_begin"].notna()]
    dropped = before - len(df)
    if dropped:
        logger.info("[load_redfin] Dropped %d rows with missing zipcode/period_begin.", dropped)

    logger.info("[load_redfin] Clean dataset: %d rows, %d columns.", len(df), len(df.columns))
    return df


# ---------------------------------------------------------------------------
# Step 3 — Upload to BigQuery
# ---------------------------------------------------------------------------

def upload_to_bq(client: Any, df, reload: bool) -> int:
    """
    Load *df* into ``mls_trends``.  Returns the number of rows uploaded.
    Uses WRITE_TRUNCATE when --reload, WRITE_APPEND otherwise.
    """
    from google.cloud import bigquery

    table_ref = f"{client.project}.{_BQ_DATASET}.{_BQ_TABLE}"
    write_disposition = "WRITE_TRUNCATE" if reload else "WRITE_APPEND"

    schema = [
        bigquery.SchemaField(f["name"], f["type"], mode=f["mode"])
        for f in _BQ_SCHEMA_FIELDS
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=write_disposition,
        source_format=bigquery.SourceFormat.PARQUET,
    )

    logger.info(
        "[load_redfin] Uploading %d rows to %s (disposition=%s) …",
        len(df), table_ref, write_disposition,
    )

    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()  # wait for completion

    final_table = client.get_table(table_ref)
    logger.info(
        "[load_redfin] Upload complete. Table now has %d rows.",
        final_table.num_rows,
    )
    return len(df)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Patch #190 — Load Redfin MA market data into BigQuery mls_trends table."
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Download and clean data but skip the BigQuery upload.",
    )
    p.add_argument(
        "--reload", action="store_true",
        help="Truncate the table before uploading (clean monthly refresh).",
    )
    p.add_argument(
        "--state", default=_STATE_FILTER,
        help=f"Two-letter state code to filter (default: {_STATE_FILTER}).",
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    logger.info("[load_redfin] Credentials : %s", creds)
    logger.info("[load_redfin] Project     : %s", _GCP_PROJECT)
    logger.info("[load_redfin] Target table: %s.%s.%s", _GCP_PROJECT, _BQ_DATASET, _BQ_TABLE)
    logger.info("[load_redfin] State filter: %s", args.state)
    if args.dry_run:
        logger.info("[load_redfin] DRY-RUN mode — BQ upload will be skipped.")

    # -- Authenticate ----------------------------------------------------------
    try:
        from google.cloud import bigquery  # type: ignore[import]
    except ImportError:
        logger.error("[load_redfin] google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery pyarrow")
        sys.exit(1)

    try:
        client = bigquery.Client(project=_GCP_PROJECT)
        logger.info("[load_redfin] Auth OK — project: %s", client.project)
    except Exception as exc:
        logger.error("[load_redfin] Auth failed: %s", exc)
        sys.exit(1)

    # -- Ensure table exists ---------------------------------------------------
    if not args.dry_run:
        ensure_bq_table(client, reload=args.reload)

    # -- Download + clean ------------------------------------------------------
    df = download_and_clean(state_filter=args.state)

    if args.dry_run:
        logger.info("[load_redfin] DRY-RUN: skipping upload. Sample rows:")
        print(df.head(5).to_string())
        print(f"\nColumns: {list(df.columns)}")
        print(f"Shape:   {df.shape}")
        return

    # -- Upload ----------------------------------------------------------------
    rows_uploaded = upload_to_bq(client, df, reload=args.reload)

    print(f"\n{'═'*60}")
    print(f"  Redfin → BigQuery load complete")
    print(f"{'═'*60}")
    print(f"  Table  : {_GCP_PROJECT}.{_BQ_DATASET}.{_BQ_TABLE}")
    print(f"  State  : {args.state}")
    print(f"  Rows   : {rows_uploaded:,}")
    print(f"  Status : ✓ market-trends domain is now REAL data")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
