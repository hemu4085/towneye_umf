# [FILE PATH]: core/storage.py
# Patch #184
# Execution Mode: Refactor — Partitioned Data Lake Layout
# Date: 2026-03-03
"""
TownEye UMF — Storage Router
==============================
Single dispatch point for persisting Parquet data across environments.

Data lake layout (Patch #184)
------------------------------
All tiers now use a **town-partitioned** directory structure::

    data/{tier}/{town_slug}/{domain}.parquet

Examples::

    data/gold/arlington-ma/zoning.parquet
    data/gold/arlington-ma/market-trends.parquet
    data/bronze/arlington-ma/property.parquet
    data/gold/waltham-ma/zoning.parquet

The previous flat layout (``data/gold/{town_slug}-{domain}.parquet``) is
superseded.  Run ``python scripts/clean_flat_parquet.py`` to remove the old
unpartitioned files.

Public API
----------
``get_parquet_path(tier, town_slug, domain)``
    Returns (and creates) the canonical path for any tier/town/domain
    combination.  Use this whenever you need the path without writing.

``save_gold_data(df, town_slug, domain_name, *, output_dir=None)``
    Writes a Gold-tier DataFrame to the partitioned local layout (dev) or
    a GCS key (production).  ``output_dir`` overrides the tier root only;
    the ``{town_slug}/{domain}.parquet`` suffix is always appended.

Environment switches
--------------------
``TOWNEYE_ENV=production``  — routes writes to GCS (stub until bucket is wired).
``TOWNEYE_GCS_BUCKET``      — override GCS bucket name (default: towneye-umf-gold).

Zero-Hardcoding contract
------------------------
No bucket name, path separator, or environment label is hardcoded in scraper
code.  All path decisions flow through this module.
"""

import logging
import os as _os
import pathlib
from typing import Optional

from .config_loader import ConfigLoader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_GCS_BUCKET     = "towneye-umf-gold"
_DEFAULT_LOCAL_GOLD_DIR = "data/gold"


def _gcs_bucket() -> str:
    return _os.environ.get("TOWNEYE_GCS_BUCKET", _DEFAULT_GCS_BUCKET)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_parquet_path(tier: str, town_slug: str, domain: str) -> pathlib.Path:
    """
    Return the canonical local Parquet path for a tier / town / domain triple.

    The path follows the partitioned data-lake layout::

        data/{tier}/{town_slug}/{domain}.parquet

    The parent directory is created if it does not already exist, so callers
    can immediately open the path for writing.

    Parameters
    ----------
    tier : str
        Storage tier name, e.g. ``"gold"``, ``"bronze"``, ``"silver"``.
    town_slug : str
        Kebab-case municipality identifier, e.g. ``"arlington-ma"``.
    domain : str
        Domain label, e.g. ``"zoning"``, ``"market-trends"``, ``"property"``.

    Returns
    -------
    pathlib.Path
        ``data/{tier}/{town_slug}/{domain}.parquet``

    Examples
    --------
    >>> get_parquet_path("gold", "arlington-ma", "zoning")
    PosixPath('data/gold/arlington-ma/zoning.parquet')
    >>> get_parquet_path("bronze", "waltham-ma", "property")
    PosixPath('data/bronze/waltham-ma/property.parquet')
    """
    path = pathlib.Path("data") / tier / town_slug / f"{domain}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_gold_data(
    dataframe,
    town_slug: str,
    domain_name: str,
    *,
    output_dir: Optional[str] = None,
) -> pathlib.Path:
    """
    Persist a Gold-tier DataFrame to the appropriate storage backend.

    Parameters
    ----------
    dataframe : pandas.DataFrame
        The validated Gold records to persist.
    town_slug : str
        Kebab-case municipality identifier (e.g. ``"arlington-ma"``).
    domain_name : str
        Kebab-case domain label (e.g. ``"zoning"``, ``"equity-index"``).
    output_dir : str, optional
        Override the tier root directory.  The ``{town_slug}/{domain}.parquet``
        suffix is always appended.  Ignored in production mode.
        Defaults to ``data/gold``.

    Returns
    -------
    pathlib.Path
        In development mode: the absolute path to the written Parquet file,
        e.g. ``data/gold/arlington-ma/zoning.parquet``.
        In production mode: a placeholder ``pathlib.Path`` representing
        the GCS URI (``gs://bucket/gold/town_slug/domain_name.parquet``).

    Notes
    -----
    The ``TOWNEYE_ENV=production`` switch triggers production mode.
    Any other value (or an unset variable) is treated as development.
    """
    if ConfigLoader.is_production():
        return _save_gcs(dataframe, town_slug, domain_name)

    tier_root = output_dir or _DEFAULT_LOCAL_GOLD_DIR
    return _save_local(dataframe, tier_root, town_slug, domain_name)


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _save_local(
    dataframe,
    tier_root: str,
    town_slug: str,
    domain_name: str,
) -> pathlib.Path:
    """
    Write *dataframe* to ``{tier_root}/{town_slug}/{domain_name}.parquet``.

    ``tier_root`` is always normalised to a relative path rooted at ``data/``
    so that absolute paths passed via ``--output-dir`` (e.g. from the CLI) do
    not accidentally produce nested paths like
    ``data/gold/home/user/.../arlington-ma/``.
    """
    # Normalise: keep only the path components after (and including) "data"
    # so that both "data/gold" and "/abs/path/data/gold" resolve to the same
    # relative tree.  If "data" is not in the path parts, use tier_root as-is
    # but strip any leading slash to stay relative.
    parts = pathlib.PurePosixPath(tier_root.replace("\\", "/")).parts
    try:
        data_idx = next(i for i, p in enumerate(parts) if p == "data")
        relative_root = pathlib.Path(*parts[data_idx:])
    except StopIteration:
        # tier_root doesn't contain "data"; use it as a relative path
        relative_root = pathlib.Path(tier_root)
        if relative_root.is_absolute():
            # Last resort: fall back to the default layout
            relative_root = pathlib.Path(_DEFAULT_LOCAL_GOLD_DIR)

    out_dir = relative_root / town_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{domain_name}.parquet"

    dataframe.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info("storage | DEV  | Wrote %d row(s) → %s", len(dataframe), out_path)
    return out_path


def _save_gcs(dataframe, town_slug: str, domain_name: str) -> pathlib.Path:
    """
    Upload *dataframe* to GCS.

    Currently a **stub** — logs the intended destination and returns a
    placeholder path.  Replace the body with a real ``google-cloud-storage``
    upload once the bucket and service-account credentials are provisioned.

    GCS key layout mirrors the local layout::

        {bucket}/gold/{town_slug}/{domain_name}.parquet
    """
    bucket  = _gcs_bucket()
    gcs_key = f"gold/{town_slug}/{domain_name}.parquet"
    gcs_uri = f"gs://{bucket}/{gcs_key}"

    # TODO: replace this stub with the real upload once GCS credentials are provisioned:
    #
    #   import io
    #   from google.cloud import storage as gcs
    #   buf = io.BytesIO()
    #   dataframe.to_parquet(buf, index=False, engine="pyarrow")
    #   buf.seek(0)
    #   client = gcs.Client()
    #   blob   = client.bucket(bucket).blob(gcs_key)
    #   blob.upload_from_file(buf, content_type="application/octet-stream")

    logger.info(
        "storage | PROD | Would upload %d row(s) → %s  (GCS stub — not yet wired)",
        len(dataframe),
        gcs_uri,
    )
    print(f"PROD MODE: Would upload to {gcs_uri}")
    return pathlib.Path(gcs_uri)
