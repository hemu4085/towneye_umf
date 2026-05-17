# [FILE PATH]: scrapers/property_l3_promoter.py
# Tier 5 / Path A
# Execution Mode: Promote MassGIS L3 CAMA -> property.parquet
# Date: 2026-05-07
"""
PropertyL3Promoter — promote the CAMA assessor record carried in
``parcel.parquet.metadata.raw_attributes`` (sourced from MassGIS L3) into
``property.parquet``.

Why this module exists
----------------------
Tier 5 switched the parcel scraper to MassGIS L3 (``Massachusetts_Property_
Tax_Parcels`` FeatureServer), which carries a full CAMA snapshot per parcel:

  OWNER1, YEAR_BUILT, TOTAL_VAL, BLDG_VAL, LAND_VAL, OTHER_VAL, FY,
  LS_DATE, LS_PRICE, LS_BOOK, LS_PAGE, LOT_SIZE, LOT_UNITS,
  USE_CODE, ZONING, STYLE, STORIES, NUM_ROOMS, BLD_AREA, RES_AREA,
  SITE_ADDR, ADDR_NUM, FULL_STR

That data lives inside ``parcel.metadata.raw_attributes`` after the parcel
ingestor runs.  This promoter lifts it into ``property.parquet`` so the
Tier 4 buildability-brief generator (which reads from property.parquet for
the assessor section) can render fully populated briefs for **every**
parcel a town's L3 ingest covered — not just the two parcels for which we
manually curated a Patriot Properties JSON sidecar.

Relationship to PropertySidecarPromoter (Tier 4.5)
--------------------------------------------------
PropertySidecarPromoter is preserved for the cases where a sidecar JSON
genuinely carries fields L3 lacks (Patriot mid-cycle changes, beds/baths,
neighborhood codes, etc.).  When both run, sidecar rows take precedence
over L3 rows for the same parcel_id — sidecar is the higher-fidelity
single-record path; L3 is the high-coverage bulk path.

Design choices
--------------
* We feed each L3 record through the existing
  ``ArlingtonPropertyScraper._promote_to_gold`` so that all field
  parsing / metadata stashing / Pydantic validation runs the same way
  as the live Patriot scrape.  No parallel codepath.
* L3 stores LOT_SIZE in ACRES (with LOT_UNITS = "Acres" — but we treat
  the unit consistently as acres for L3).  Convert to sqft so the
  existing brief math (which expects sqft) works unchanged.
* L3 stores LS_DATE as ``"YYYYMMDD"`` and LS_PRICE as integer.
  Re-pack as ``"M/D/YYYY $PRICE"`` so the property scraper's existing
  ``_parse_sale_date_price`` regex handles them — no new parser needed.
* L3 has no beds/baths fields.  Leave them as None; the brief gracefully
  omits the bedroom/bathroom columns when missing.
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.identity_linker import PartyLinker, get_linker
from core.storage import save_gold_data
from scrapers.property_scraper import ArlingtonPropertyScraper

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# L3 -> Patriot-Properties-shaped field map.
#
# Keys are L3 raw_attribute field names; values are the bronze-dict keys
# that ArlingtonPropertyScraper._promote_to_gold consumes.  Values that
# require numeric/format conversion are handled in _l3_to_bronze().
# ----------------------------------------------------------------------
_L3_TO_BRONZE: Dict[str, str] = {
    "OWNER1":      "owner",
    "SITE_ADDR":   "address",
    "TOTAL_VAL":   "total_value",
    "YEAR_BUILT":  "year_built",
    "STYLE":       "building_type",
    "USE_CODE":    "luc",
    "ZONING":      "zone_code",
}

# Square feet per acre (US survey acre, exact: 1 acre = 43,560 sqft).
_SQFT_PER_ACRE: float = 43560.0


def _l3_lot_size_sqft(raw: Dict[str, Any]) -> Optional[float]:
    """
    L3 stores ``LOT_SIZE`` in acres (with ``LOT_UNITS = "Acres"``).
    Convert to square feet for the property scraper's lot_size_sqft column.
    Returns None when the value is missing, zero, or unparseable.
    """
    v = raw.get("LOT_SIZE")
    if v is None or v == "" or v == 0:
        return None
    try:
        acres = float(v)
    except (TypeError, ValueError):
        return None
    if acres <= 0:
        return None
    return round(acres * _SQFT_PER_ACRE, 2)


def _l3_sale_date_price_string(raw: Dict[str, Any]) -> Optional[str]:
    """
    Build the Patriot-Properties ``sale_date_sale_price`` string
    (e.g. ``"6/13/2017 $750,000"``) from L3's separate
    ``LS_DATE`` (``"YYYYMMDD"``) and ``LS_PRICE`` (integer) fields.

    Returns ``None`` when neither component is present.  When only one
    component exists, the resulting string still parses cleanly via
    ``ArlingtonPropertyScraper._parse_sale_date_price``.
    """
    date_raw = raw.get("LS_DATE")
    price_raw = raw.get("LS_PRICE")
    parts: List[str] = []

    if date_raw and len(str(date_raw)) == 8 and str(date_raw).isdigit():
        s = str(date_raw)
        yyyy, mm, dd = s[0:4], s[4:6], s[6:8]
        try:
            parts.append(f"{int(mm)}/{int(dd)}/{int(yyyy)}")
        except ValueError:
            pass

    if price_raw is not None and price_raw != 0:
        try:
            parts.append(f"${int(price_raw):,}")
        except (TypeError, ValueError):
            pass

    if not parts:
        return None
    return " ".join(parts)


def _l3_book_page(raw: Dict[str, Any]) -> Optional[str]:
    """
    L3 publishes ``LS_BOOK`` and ``LS_PAGE`` as separate strings.
    Concatenate them with a forward slash so the brief generator can
    render the deed-reference line directly.

    Leading-zero padding from the assessor (e.g. LS_BOOK="01287",
    LS_PAGE="0190") is preserved verbatim — it carries provenance.
    """
    book = (raw.get("LS_BOOK") or "").strip() if raw.get("LS_BOOK") else ""
    page = (raw.get("LS_PAGE") or "").strip() if raw.get("LS_PAGE") else ""
    if not book and not page:
        return None
    return f"{book}/{page}".strip("/")


def _l3_to_bronze(parcel_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn one L3 raw_attributes dict into a Patriot-Properties-shaped
    bronze dict ready for ``ArlingtonPropertyScraper._promote_to_gold``.

    Parameters
    ----------
    parcel_id : str
        The canonical parcel id (carried from the parcel scraper, not
        re-derived from L3 — preserves identity-linker continuity).
    raw : dict
        L3's ``raw_attributes`` for this parcel.
    """
    bronze: Dict[str, Any] = {"parcel_id": parcel_id}

    for l3_key, bronze_key in _L3_TO_BRONZE.items():
        v = raw.get(l3_key)
        if v is None or v == "":
            continue
        bronze[bronze_key] = v

    lot_sqft = _l3_lot_size_sqft(raw)
    if lot_sqft is not None:
        bronze["lot_size_sqft"] = lot_sqft

    sale_str = _l3_sale_date_price_string(raw)
    if sale_str is not None:
        bronze["sale_date_sale_price"] = sale_str

    bp = _l3_book_page(raw)
    if bp is not None:
        bronze["book_page"] = bp

    # Carry these L3-only fields through under names the property
    # scraper's metadata-passthrough will preserve.  They surface in
    # property.parquet's metadata column.
    if raw.get("RES_AREA"):
        bronze["finished_area_sqft_l3"] = raw["RES_AREA"]
    if raw.get("BLD_AREA"):
        bronze["building_footprint_sqft"] = raw["BLD_AREA"]
    if raw.get("STORIES"):
        bronze["stories"] = raw["STORIES"]
    if raw.get("NUM_ROOMS"):
        bronze["num_rooms"] = raw["NUM_ROOMS"]
    if raw.get("BLDG_VAL"):
        bronze["bldg_val"] = raw["BLDG_VAL"]
    if raw.get("LAND_VAL"):
        bronze["land_val"] = raw["LAND_VAL"]
    if raw.get("FY"):
        bronze["fiscal_year"] = raw["FY"]
    if raw.get("LOC_ID"):
        bronze["massgis_loc_id"] = raw["LOC_ID"]

    bronze["data_provenance"] = "massgis-l3"
    return bronze


class PropertyL3Promoter:
    """
    Promote MassGIS L3 CAMA records (already ingested into parcel.parquet)
    into property.parquet.

    Parameters
    ----------
    town_slug : str
        Kebab-case municipality id.
    config_base_dir : str, optional
        Per-town config root.  Defaults to ``"configs"``.
    gold_dir : str | os.PathLike, optional
        Root of the Gold data lake.  Defaults to ``"data/gold"``.
    linker : PartyLinker, optional
        Identity-resolution client; the offline ``HashLinker`` is used
        when omitted.
    preserve_existing : bool, optional
        When True (default), rows already present in ``property.parquet``
        are preserved over L3-derived rows for the same parcel_id.  Use
        this to keep richer Patriot/sidecar data when both paths have
        run for the same parcel.
    """

    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
        gold_dir: str | pathlib.Path = "data/gold",
        linker: Optional[PartyLinker] = None,
        preserve_existing: bool = True,
    ) -> None:
        self.town_slug = town_slug
        self._gold_dir = pathlib.Path(gold_dir)
        self._linker = linker or get_linker()
        self._preserve_existing = preserve_existing

        # Borrow the property scraper's column map / te_source / factory
        # without ever issuing an HTTP request.  Constructing the scraper
        # is pure local work as long as run() / fetch_page() are not called.
        self._scraper = ArlingtonPropertyScraper(
            town_slug=town_slug,
            config_base_dir=config_base_dir,
            linker=self._linker,
        )
        self._te_source = self._scraper._te_source  # noqa: SLF001 (intentional)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_parcel_attributes(self) -> List[Dict[str, Any]]:
        """
        Read ``data/gold/{slug}/parcel.parquet`` and return one record
        per parcel of the form::

            { "parcel_id": "...", "raw_attributes": {...} }

        Rows whose metadata is missing or whose raw_attributes blob is
        empty are dropped.
        """
        parcel_path = self._gold_dir / self.town_slug / "parcel.parquet"
        if not parcel_path.exists():
            raise FileNotFoundError(
                f"PropertyL3Promoter | parcel.parquet missing for {self.town_slug}: {parcel_path}"
            )

        df = pd.read_parquet(parcel_path)
        out: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            md = row.get("metadata")
            if isinstance(md, str):
                try:
                    md = json.loads(md)
                except json.JSONDecodeError:
                    continue
            if not isinstance(md, dict):
                continue
            raw_attrs = md.get("raw_attributes") or {}
            if not isinstance(raw_attrs, dict) or not raw_attrs:
                continue
            out.append({
                "parcel_id":      str(row["parcel_id"]),
                "raw_attributes": raw_attrs,
            })
        logger.info(
            "PropertyL3Promoter | %s: %d parcel(s) carry L3 raw_attributes.",
            self.town_slug, len(out),
        )
        return out

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def promote_records(
        self, records: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Run each ``{parcel_id, raw_attributes}`` record through the
        shared property-scraper Bronze->Gold path.

        Returns the list of Gold-shaped dicts ready for parquet write.
        """
        gold_rows: List[Dict[str, Any]] = []
        skipped = 0
        for r in records:
            parcel_id = r["parcel_id"]
            bronze = _l3_to_bronze(parcel_id, r["raw_attributes"])
            # The property scraper expects the natural id under the
            # configured ``source_id_col`` *and* under ``parcel_id``.
            bronze[self._scraper._source_id_col] = parcel_id  # noqa: SLF001
            try:
                gold_rows.append(
                    self._scraper._promote_to_gold(bronze, self._linker)  # noqa: SLF001
                )
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                logger.warning(
                    "PropertyL3Promoter | _promote_to_gold failed for %s: %s",
                    parcel_id, exc,
                )
        if skipped:
            logger.warning(
                "PropertyL3Promoter | %d / %d record(s) skipped due to promotion failures.",
                skipped, sum(1 for _ in records) if isinstance(records, list) else "?",
            )
        return gold_rows

    # ------------------------------------------------------------------
    # Merge + persist
    # ------------------------------------------------------------------

    def merge_into_gold(self, new_rows: List[Dict[str, Any]]) -> pathlib.Path:
        """
        Replace-or-append *new_rows* into ``{gold_dir}/{slug}/property.parquet``.

        When ``preserve_existing=True`` (default), a parcel_id already
        present in the gold parquet is **kept** and the L3 row is
        dropped.  This way a pre-existing Patriot / sidecar record is
        not overwritten by a (possibly less detailed) L3 row.

        When ``preserve_existing=False`` the new L3 rows replace any
        colliding existing rows.
        """
        gold_path = self._gold_dir / self.town_slug / "property.parquet"
        new_df = pd.DataFrame(new_rows) if new_rows else pd.DataFrame()
        if gold_path.exists():
            existing = pd.read_parquet(gold_path)
            if "parcel_id" in existing.columns and not new_df.empty:
                existing_ids = set(existing["parcel_id"].astype(str).tolist())
                if self._preserve_existing:
                    new_df = new_df[~new_df["parcel_id"].astype(str).isin(existing_ids)]
                    merged = pd.concat([existing, new_df], ignore_index=True) if not new_df.empty else existing
                else:
                    new_ids = set(new_df["parcel_id"].astype(str).tolist())
                    keep_mask = ~existing["parcel_id"].astype(str).isin(new_ids)
                    merged = pd.concat([existing[keep_mask], new_df], ignore_index=True)
            else:
                merged = pd.concat([existing, new_df], ignore_index=True) if not new_df.empty else existing
        else:
            merged = new_df
        return save_gold_data(merged, self.town_slug, "property", output_dir=str(self._gold_dir))

    # ------------------------------------------------------------------
    # One-shot orchestrator
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """
        Load parcel.metadata.raw_attributes -> shape -> promote -> merge.

        Returns
        -------
        dict
            ``{ "parcels_with_l3": int, "rows_promoted": int,
                "rows_kept_from_existing": int, "output_path": pathlib.Path }``
        """
        records = self.load_parcel_attributes()
        gold_rows = self.promote_records(records)
        out_path = self.merge_into_gold(gold_rows)

        kept_existing = 0
        try:
            df_after = pd.read_parquet(out_path)
            kept_existing = max(0, len(df_after) - len(gold_rows))
        except Exception:  # noqa: BLE001
            pass

        return {
            "parcels_with_l3":         len(records),
            "rows_promoted":           len(gold_rows),
            "rows_kept_from_existing": kept_existing,
            "output_path":             out_path,
        }


__all__ = ["PropertyL3Promoter"]
