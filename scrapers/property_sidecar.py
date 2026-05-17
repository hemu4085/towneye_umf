# [FILE PATH]: scrapers/property_sidecar.py
# Patch #206
# Execution Mode: Tier 4.5 — Property-Scrape Sidecar Promoter
# Date: 2026-05-07
"""
PropertySidecarPromoter — promote pre-scraped assessor JSON files into
the Tier 1 ``property.parquet`` Gold table.

Why this module exists
----------------------
The live Patriot Properties HTML scraper in
``scrapers/property_scraper.py::ArlingtonPropertyScraper`` requires a
session cookie / cross-site POST that the synchronous ``requests``
client cannot reliably reproduce.  When the live URL fails, the
scraper falls back to LLM synthesis (no API key in dev) and finally to
two synthetic placeholder rows — leaving Tier 4's buildability brief
without real owner / year-built / GFA / sale data.

Tier 4.5 closes the gap by recognising that we **already have** the
real data for every parcel an analyst has examined: each ad-hoc query
session writes a ``data/{some_dir}/assessor.json`` file with the raw
Patriot Properties parse.  The sidecar promoter:

  1. Walks the ``data/`` tree looking for assessor JSON files.
  2. Pulls every record whose ``te_source`` matches the town's
     configured assessor source.
  3. Re-uses ``ArlingtonPropertyScraper._promote_to_gold`` so the same
     parsing rules (built_type / beds_baths / lot_size_fin_area /
     sale_date_sale_price / luc_description / book_page) drive both
     paths.
  4. Merges the new Gold rows into ``data/gold/{slug}/property.parquet``
     by ``parcel_id`` (existing rows are replaced, novel rows appended,
     all other parcels are preserved).

The result is that Tier 4's brief renders the assessor section for
any parcel an analyst has touched, without anyone needing to maintain
a separate property pipeline.

Sidecar JSON shape
------------------
The promoter accepts two layouts:

  * **Wrapped** (used by ``scripts/29_walnut_queries.py``):

        {
          "status": 200,
          "saved_html": "...",
          "parsed_29_records": [{...}, {...}],
        }

    Any list-valued key whose name starts with ``parsed_`` is treated
    as the records list; the wrapper metadata is ignored.

  * **Flat list**:

        [{...}, {...}]

Each record must contain the assessor source's natural ``parcel_id``
column (configured in ``scraper_column_map.source_id_col``) and
should carry as many of the Patriot Properties columns as available.
Missing columns are simply absent from the resulting Gold row;
they are not invented.
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


class PropertySidecarPromoter:
    """
    Promote pre-scraped assessor JSON sidecar files into property.parquet.

    Parameters
    ----------
    town_slug : str
        Kebab-case municipality id; the promoter only consumes records
        whose ``te_source`` matches the town's configured assessor source.
    config_base_dir : str, optional
        Per-town config root.  Defaults to ``"configs"``.
    data_dir : str | os.PathLike, optional
        Root of the Bronze data lake.  Defaults to ``"data"``.
    gold_dir : str | os.PathLike, optional
        Root of the Gold data lake.  Defaults to ``"data/gold"``.
    linker : PartyLinker, optional
        Identity-resolution client; the offline ``HashLinker`` is used
        when omitted (chosen by ``core.identity_linker.get_linker()``).
    """

    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
        data_dir: str | pathlib.Path = "data",
        gold_dir: str | pathlib.Path = "data/gold",
        linker: Optional[PartyLinker] = None,
    ) -> None:
        self.town_slug = town_slug
        self._data_dir = pathlib.Path(data_dir)
        self._gold_dir = pathlib.Path(gold_dir)
        self._linker = linker or get_linker()

        # We piggyback on the live HTTP scraper's column maps and
        # _promote_to_gold path; constructing it does no network I/O
        # because we never call .run() / .fetch_page().
        self._scraper = ArlingtonPropertyScraper(
            town_slug=town_slug,
            config_base_dir=config_base_dir,
            linker=self._linker,
        )
        self._te_source = self._scraper._te_source  # noqa: SLF001 (intentional)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sidecar_files(
        self,
        sidecar_glob: str = "*/assessor.json",
        explicit_paths: Optional[Iterable[pathlib.Path]] = None,
    ) -> List[pathlib.Path]:
        """
        Return the list of sidecar JSON files to consume.

        By default this walks the Bronze data root with the pattern
        ``data/*/assessor.json`` (the convention used by
        ``scripts/29_walnut_queries.py``).  When *explicit_paths* is
        supplied it is used verbatim — useful for unit tests and the
        CLI driver.
        """
        if explicit_paths is not None:
            return [pathlib.Path(p) for p in explicit_paths]
        return sorted(self._data_dir.glob(sidecar_glob))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @staticmethod
    def load_records_from_file(path: pathlib.Path) -> List[Dict[str, Any]]:
        """
        Read *path* and return the contained list of assessor records.

        Accepts either a flat list or the wrapped ``{ "parsed_xxx_records": [...] }``
        layout used by the ad-hoc query scripts.  Returns an empty list
        for files that contain no recognisable record array.
        """
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "PropertySidecarPromoter | could not parse %s: %s — skipping.",
                path, exc,
            )
            return []
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key.startswith("parsed_") and isinstance(value, list):
                    return [r for r in value if isinstance(r, dict)]
        return []

    def filter_by_source(
        self, records: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Keep only records whose ``te_source`` matches the configured assessor."""
        out: List[Dict[str, Any]] = []
        for r in records:
            src = r.get("te_source")
            if src is None or src == self._te_source:
                out.append({**r, "te_source": self._te_source})
        return out

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def promote_records(
        self, records: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Run each record through the shared ``_promote_to_gold`` path.

        Skips records that lack the configured natural-id column (the
        scraper would otherwise produce a row keyed on the empty string).
        """
        gold_rows: List[Dict[str, Any]] = []
        for raw in records:
            # The Patriot Properties parser names the parcel id column
            # 'location' or whatever is configured; the assessor sidecar
            # files emit a 'parcel_id' alias too, so accept both.
            if not raw.get(self._scraper._source_id_col) and raw.get("parcel_id"):
                raw = {**raw, self._scraper._source_id_col: raw["parcel_id"]}
            if not raw.get(self._scraper._source_id_col):
                logger.warning(
                    "PropertySidecarPromoter | record missing '%s' / 'parcel_id' — skipping: %s",
                    self._scraper._source_id_col, list(raw.keys()),
                )
                continue
            try:
                gold_rows.append(self._scraper._promote_to_gold(raw, self._linker))  # noqa: SLF001
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "PropertySidecarPromoter | _promote_to_gold failed for %s: %s",
                    raw.get("parcel_id"), exc,
                )
        return gold_rows

    # ------------------------------------------------------------------
    # Merge + persist
    # ------------------------------------------------------------------

    def merge_into_gold(self, new_rows: List[Dict[str, Any]]) -> pathlib.Path:
        """
        Replace-or-append *new_rows* into ``{gold_dir}/{slug}/property.parquet``.

        Existing rows whose ``parcel_id`` collides with a new row are
        dropped; all other rows are preserved.  When the gold parquet
        does not exist, it is created from *new_rows* alone.
        """
        gold_path = self._gold_dir / self.town_slug / "property.parquet"
        new_df = pd.DataFrame(new_rows) if new_rows else pd.DataFrame()
        if gold_path.exists():
            existing = pd.read_parquet(gold_path)
            if "parcel_id" in existing.columns and not new_df.empty:
                replaced_ids = set(new_df["parcel_id"].astype(str).tolist())
                keep_mask = ~existing["parcel_id"].astype(str).isin(replaced_ids)
                preserved = existing[keep_mask]
            else:
                preserved = existing
            merged = pd.concat([preserved, new_df], ignore_index=True) if not new_df.empty else preserved
        else:
            merged = new_df
        return save_gold_data(merged, self.town_slug, "property", output_dir=str(self._gold_dir))

    # ------------------------------------------------------------------
    # One-shot orchestrator
    # ------------------------------------------------------------------

    def run(
        self,
        sidecar_glob: str = "*/assessor.json",
        explicit_paths: Optional[Iterable[pathlib.Path]] = None,
    ) -> Dict[str, Any]:
        """
        Discover → load → filter → promote → merge in one call.

        Returns
        -------
        dict
            ``{ "files_scanned": int, "records_promoted": int,
                "parcel_ids": [...], "output_path": pathlib.Path }``
        """
        files = self.discover_sidecar_files(sidecar_glob=sidecar_glob, explicit_paths=explicit_paths)
        all_records: List[Dict[str, Any]] = []
        for f in files:
            recs = self.load_records_from_file(f)
            kept = self.filter_by_source(recs)
            logger.info(
                "PropertySidecarPromoter | %s: %d record(s), %d match te_source=%r.",
                f, len(recs), len(kept), self._te_source,
            )
            all_records.extend(kept)

        gold_rows = self.promote_records(all_records)
        out_path = self.merge_into_gold(gold_rows)
        return {
            "files_scanned":     len(files),
            "records_promoted":  len(gold_rows),
            "parcel_ids":        [r.get("parcel_id") for r in gold_rows],
            "output_path":       out_path,
        }


__all__ = ["PropertySidecarPromoter"]
