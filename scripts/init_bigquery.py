# [FILE PATH]: scripts/init_bigquery.py
# Patch #189
# Execution Mode: Initialize BigQuery Datasets
# Date: 2026-03-04
"""
One-shot initializer for the TownEye BigQuery data warehouse.

Creates two top-level datasets in the `towneye-umf` GCP project:
  - market_dynamics  : raw and aggregated MLS / market-trend tables
  - gold_tier        : mirrored Gold-tier Parquet uploads per town/domain

Usage
-----
    # From project root, with .env sourced:
    set -a && source .env && set +a
    python scripts/init_bigquery.py

    # Or pass credentials explicitly:
    GOOGLE_APPLICATION_CREDENTIALS=gcp-key.json python scripts/init_bigquery.py

Idempotent: existing datasets are left untouched; the script reports their
current state rather than raising an error.
"""

import os
import pathlib
import sys

# ---------------------------------------------------------------------------
# Path bootstrap so the script works whether run from project root or scripts/
# ---------------------------------------------------------------------------
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault(
    "GOOGLE_APPLICATION_CREDENTIALS",
    str(_PROJECT_ROOT / "gcp-key.json"),
)

# ---------------------------------------------------------------------------
# Config — all values driven from constants, nothing hardcoded per-town
# ---------------------------------------------------------------------------
_GCP_PROJECT    = "towneye-umf"
_DATASET_REGION = "US"

_DATASETS: dict[str, str] = {
    "market_dynamics": (
        "Raw and aggregated MLS / market-trend data. "
        "Partitioned by town_slug and observation_date."
    ),
    "gold_tier": (
        "Mirrored Gold-tier Parquet uploads per town and domain. "
        "Populated by scripts/upload_gold_to_bq.py (future)."
    ),
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _create_dataset(
    client,
    dataset_id: str,
    description: str,
    location: str,
) -> tuple[bool, str]:
    """Create *dataset_id* if it does not already exist.

    Returns (created: bool, status_message: str).
    """
    from google.cloud import bigquery
    from google.api_core.exceptions import Conflict  # type: ignore[import]

    full_id = f"{client.project}.{dataset_id}"
    dataset  = bigquery.Dataset(full_id)
    dataset.location    = location
    dataset.description = description

    try:
        client.create_dataset(dataset, timeout=30)
        return True, f"CREATED  {full_id}  ({location})"
    except Conflict:
        existing = client.get_dataset(full_id)
        return False, (
            f"EXISTS   {full_id}  "
            f"(location={existing.location}, "
            f"created={existing.created.date() if existing.created else '?'})"
        )


def main() -> None:
    try:
        from google.cloud import bigquery  # type: ignore[import]
    except ImportError:
        print("[init_bigquery] ERROR: google-cloud-bigquery not installed.")
        print("  Run: pip install google-cloud-bigquery")
        sys.exit(1)

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    print(f"[init_bigquery] Credentials : {creds_path}")
    print(f"[init_bigquery] Project     : {_GCP_PROJECT}")
    print(f"[init_bigquery] Region      : {_DATASET_REGION}")
    print()

    try:
        client = bigquery.Client(project=_GCP_PROJECT)
        print(f"[init_bigquery] Auth OK — connected to project '{client.project}'\n")
    except Exception as exc:
        print(f"[init_bigquery] AUTH FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)

    # -- Create datasets -------------------------------------------------------
    print("[init_bigquery] Creating datasets ...")
    for ds_id, ds_desc in _DATASETS.items():
        created, msg = _create_dataset(client, ds_id, ds_desc, _DATASET_REGION)
        prefix = "  +" if created else "  ~"
        print(f"{prefix} {msg}")

    # -- Verification pass ------------------------------------------------------
    print()
    print("[init_bigquery] Verifying — listing all datasets in project ...")
    datasets = list(client.list_datasets())
    if not datasets:
        print("  (none found — unexpected)")
    else:
        for ds in datasets:
            info = client.get_dataset(ds.dataset_id)
            tables = list(client.list_tables(ds.dataset_id))
            table_summary = f"{len(tables)} table(s)" if tables else "no tables yet"
            print(
                f"  DATASET  {ds.dataset_id:<25}"
                f"  location={info.location:<6}"
                f"  {table_summary}"
            )

    print()
    print("[init_bigquery] Done.")


if __name__ == "__main__":
    main()
