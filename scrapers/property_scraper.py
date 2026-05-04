# [FILE PATH]: scrapers/property_scraper.py
# Patch #199 (migrated from Patch #185)
# Execution Mode: Bronze -> Gold Property Assessor Scraper
"""
ArlingtonPropertyScraper
========================
Fetches raw property records from the municipality's public assessor
portal and runs them through the full UMF Bronze -> Gold pipeline.

Data source priority
--------------------
1. Live Patriot Properties HTML (SearchResults.asp) — if URL is live
2. LLM synthesis (Gemini) — for towns using VGSI Silverlight portals
   that are not machine-readable
3. Synthetic hardcoded fallback

Zero-Hardcoding contract
------------------------
* The base URL, te_source, geo_hash, town_slug, town_name, state, and
  HTML column mappings are read exclusively from
  ``configs/{town_slug}/config.yaml`` via ConfigLoader.
* MedallionFactory and PartyLinker are injectable at construction time.
* To target a different municipality, instantiate with its slug.
"""

import sys
import json
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.llm_client import call_llm
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_PAGE_SIZE: int = 100
_REQUEST_TIMEOUT_S: int = 30

_SYSTEM_PROMPT = (
    "You are a municipal property assessor data expert. "
    "Return ONLY a compact JSON array of exactly 5 realistic residential property "
    "assessment records. Each object must have these exact keys: "
    "parcel_id (string like '10-1-0'), address (string), owner (string, LAST FIRST format), "
    "total_value (string like '$550,000'), year_built (string like '1985'), "
    "building_type (string like 'Colonial' or 'Ranch'), luc (string like '101'), "
    "luc_description (string like 'One Family'), lot_size (string in sqft like '15000'), "
    "beds (string), baths (string). "
    "NO markdown fences. NO prose. NO spaces after colons or commas. "
    "Short strings only. Output must be valid JSON."
)


class ArlingtonPropertyScraper:
    """
    Full Bronze -> Gold scraper for a municipality's property assessor portal.

    Parameters
    ----------
    town_slug : str
        Kebab-case municipality identifier (e.g. ``"arlington-ma"``).
    config_base_dir : str, optional
        Root directory that holds per-town config folders.
    session : requests.Session, optional
        Pre-built HTTP session.  A fresh session is created when omitted.
    linker : PartyLinker, optional
        Identity-resolution client.
    factory : MedallionFactory, optional
        Bronze -> Gold transform engine.
    """

    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
        session: Optional[requests.Session] = None,
        linker: Optional[PartyLinker] = None,
        factory: Optional[MedallionFactory] = None,
    ) -> None:
        loader = ConfigLoader(base_dir=config_base_dir)
        self._config: Dict[str, Any] = loader.get_town_config(town_slug)

        self._town_slug: str = self._config["town_slug"]
        self._geo_hash: str = self._config.get("geo_hash", "")
        self._te_source: str = self._config["source_mappings"]["tax-assessor"]
        self._base_url: str = self._config["scraper_urls"]["property_assessor"]
        self._town_name: str = self._config.get("town_name", self._town_slug)
        self._state: str = self._config.get("state", "MA")

        col_map: Dict[str, Any] = self._config["scraper_column_map"]
        self._source_id_col: str = col_map["source_id_col"]
        self._legal_name_col: str = col_map["legal_name_col"]
        self._data_table_idx: int = int(col_map.get("data_table_idx", 0))
        self._header_col_offset: int = int(col_map.get("header_col_offset", 0))
        _idx = col_map.get("source_id_col_idx")
        self._source_id_col_idx: Optional[int] = int(_idx) if _idx is not None else None

        self._search_params: Dict[str, Any] = dict(
            self._config.get("scraper_search_params", {})
        )
        self._page_param: str = self._config.get("scraper_page_param", "Page")

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            logger.warning(
                "ArlingtonPropertyScraper | SSL verification DISABLED "
                "(http.ssl_verify=false in config). "
                "Do not use this setting in production."
            )
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session: requests.Session = session or requests.Session()
        self._session.verify = _ssl_verify

        _max_pages = self._config.get("scraper_max_pages")
        self._max_pages: Optional[int] = int(_max_pages) if _max_pages is not None else None

        self._factory: MedallionFactory = (
            factory or MedallionFactory(town_slug, config_base_dir)
        )
        self._linker: Optional[PartyLinker] = linker

        self._org_keywords: List[str] = [
            kw.upper()
            for kw in self._config.get("party_type_org_keywords", [])
        ]

    # ------------------------------------------------------------------
    # Bronze layer
    # ------------------------------------------------------------------

    def fetch_page(self, page: int = 1) -> str:
        params: Dict[str, Any] = {**self._search_params, self._page_param: page}
        logger.info("ArlingtonPropertyScraper | GET %s page=%d", self._base_url, page)
        resp = self._session.get(self._base_url, params=params, timeout=_REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.text

    def parse_records(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        all_tables = soup.find_all("table")
        if len(all_tables) <= self._data_table_idx:
            logger.warning(
                "ArlingtonPropertyScraper | Expected table at index %d but only "
                "%d table(s) found", self._data_table_idx, len(all_tables)
            )
            return []

        table = all_tables[self._data_table_idx]
        rows = table.find_all("tr")
        if len(rows) < 2:
            logger.warning("ArlingtonPropertyScraper | Data table has fewer than 2 rows")
            return []

        raw_headers = [
            th.get_text(" ", strip=True).lower().replace(" ", "_")
            for th in rows[0].find_all(["th", "td"])
        ]
        headers: List[str] = list(raw_headers[self._header_col_offset:])

        if (
            self._source_id_col_idx is not None
            and self._source_id_col_idx < len(headers)
        ):
            headers[self._source_id_col_idx] = self._source_id_col

        records: List[Dict[str, Any]] = []
        for tr in rows[1:]:
            cells = tr.find_all("td")
            if not cells:
                continue
            record: Dict[str, Any] = dict(
                zip(headers, [td.get_text(" ", strip=True) for td in cells])
            )
            record["te_source"] = self._te_source
            record["te_geo_hash"] = self._geo_hash
            records.append(record)

        logger.debug("ArlingtonPropertyScraper | Parsed %d records from page", len(records))
        return records

    def _has_next_page(self, html: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        return bool(soup.find_all("a", string=lambda t: t and "next" in t.lower()))

    # ------------------------------------------------------------------
    # Gold layer
    # ------------------------------------------------------------------

    # Column names that are promoted to first-class Gold fields.
    # Any Bronze key in this set is NOT repeated inside metadata.
    _FIRST_CLASS_COLS: frozenset = frozenset({
        "address", "location", "total_value", "assessed_value", "total_assessed_value",
        "year_built", "building_type", "built_type",
        "luc", "luc_description",
        "lot_size", "lot_size_sqft", "lot_size_fin_area",
        "beds", "baths", "beds_baths",
        "owner", "zone_code", "nhood",
        "te_source", "te_geo_hash",
    })

    @staticmethod
    def _parse_built_type(raw: Optional[str]) -> tuple:
        """
        Patriot Properties packs year and style into one column, e.g. '1930 Store'.
        Returns (year_built: str|None, building_type: str|None).
        """
        if not raw:
            return None, None
        import re
        m = re.match(r"(\d{4})\s*(.*)", str(raw).strip())
        if m:
            return m.group(1) or None, m.group(2).strip() or None
        return None, str(raw).strip() or None

    @staticmethod
    def _parse_beds_baths(raw: Optional[str]) -> tuple:
        """
        Patriot Properties stores beds and baths as '3 2' or '3 1.5'.
        Returns (beds: str|None, baths: str|None).
        """
        if not raw:
            return None, None
        parts = str(raw).strip().split()
        beds = parts[0] if len(parts) > 0 else None
        baths = parts[1] if len(parts) > 1 else None
        return beds, baths

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        source_id: str = bronze.get(self._source_id_col, "")
        te_property_pk: int = linker.resolve(self._te_source, source_id)

        owner_name: str = bronze.get(self._legal_name_col, "") or bronze.get("owner", "")

        # Handle Patriot Properties HTML column aliases
        address = bronze.get("address") or bronze.get("location", "")
        assessed_value = (
            bronze.get("total_value")
            or bronze.get("assessed_value")
            or bronze.get("total_assessed_value")
        )

        # Patriot Properties packs year+style into one column ('1930 Store')
        raw_built_type = bronze.get("built_type") or bronze.get("building_type")
        year_built_raw = bronze.get("year_built")
        building_type_raw = None
        if not year_built_raw and raw_built_type:
            year_built_raw, building_type_raw = self._parse_built_type(raw_built_type)
        else:
            building_type_raw = bronze.get("building_type")

        # Patriot Properties packs beds+baths into one column ('3 2')
        beds_raw = bronze.get("beds")
        baths_raw = bronze.get("baths")
        if not beds_raw and bronze.get("beds_baths"):
            beds_raw, baths_raw = self._parse_beds_baths(bronze.get("beds_baths"))

        # Lot size — Patriot Properties: 'lot_size_fin_area' contains 'lotSqft finAreaSqft'
        lot_size_raw = bronze.get("lot_size") or bronze.get("lot_size_sqft")
        if not lot_size_raw and bronze.get("lot_size_fin_area"):
            lot_size_raw = str(bronze["lot_size_fin_area"]).split()[0]

        # Columns consumed as named fields — not duplicated in metadata
        consumed = (
            self._FIRST_CLASS_COLS
            | {self._source_id_col, self._legal_name_col}
        )

        extra_meta = {k: v for k, v in bronze.items() if k not in consumed}
        # PyArrow cannot write an empty struct column — always include at least one key
        if not extra_meta:
            extra_meta = {"_source": self._te_source}

        raw_for_factory: Dict[str, Any] = {
            "te_property_pk":  te_property_pk,
            "parcel_id":       source_id,
            "address":         address,
            "zone_code":       bronze.get("zone_code") or bronze.get("nhood"),
            "assessed_value":  assessed_value,
            "year_built":      year_built_raw,
            "building_type":   building_type_raw,
            "lot_size_sqft":   lot_size_raw,
            "luc":             bronze.get("luc"),
            "luc_description": bronze.get("luc_description"),
            "beds":            beds_raw,
            "baths":           baths_raw,
            "owner_name":      owner_name,
            "te_party_pk":     te_property_pk,
            "te_source":       self._te_source,
            "te_geo_hash":     self._geo_hash,
            "metadata":        extra_meta,
        }

        logger.debug(
            "ArlingtonPropertyScraper | Promoting te_property_pk=%d parcel_id='%s'",
            te_property_pk, source_id,
        )
        return self._factory.map_to_property_assessment(raw_for_factory)

    def _is_placeholder_url(self) -> bool:
        return (
            "PLACEHOLDER" in self._base_url
            or "VGSI_SILVERLIGHT_DEAD" in self._base_url
            or not self._base_url.startswith("http")
        )

    def _fetch_llm(self) -> List[Dict[str, Any]]:
        """Call Gemini to synthesise realistic property assessment records."""
        user_prompt = (
            f"5 realistic residential property assessment records for "
            f"{self._town_name},{self._state}. "
            "Use real street names. Short strings. Compact JSON only."
        )
        for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            try:
                raw = call_llm(
                    system=_SYSTEM_PROMPT,
                    user=user_prompt,
                    model=model,
                    n_tokens=1024,
                )
                if not raw:
                    continue
                text = raw.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1]
                    text = text.rsplit("```", 1)[0].strip()
                start = text.find("[")
                end = text.rfind("]")
                if start == -1 or end == -1:
                    logger.warning(
                        "ArlingtonPropertyScraper | LLM returned no JSON array "
                        "(model=%s). Raw: %.120s", model, raw
                    )
                    continue
                text = text[start : end + 1]
                if text.endswith(","):
                    text = text[:-1] + "]"
                records = json.loads(text)
                if not isinstance(records, list) or not records:
                    continue
                for r in records:
                    r.setdefault("te_source", self._te_source)
                    r.setdefault("te_geo_hash", self._geo_hash)
                logger.info(
                    "ArlingtonPropertyScraper | LLM returned %d property "
                    "records for '%s'.", len(records), self._town_slug
                )
                return records
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                if "RESOURCE_EXHAUSTED" in err or "429" in err:
                    logger.warning(
                        "ArlingtonPropertyScraper | LLM quota hit (model=%s): %s",
                        model, err[:120]
                    )
                    continue
                logger.warning(
                    "ArlingtonPropertyScraper | LLM call failed (model=%s): %s",
                    model, err[:200]
                )
        return []

    def _generate_synthetic_bronze(self) -> List[Dict[str, Any]]:
        """Return placeholder property records for towns whose assessor URL is not yet discovered."""
        return [
            {
                self._source_id_col:  f"{self._town_slug.upper()[:6]}-000001",
                self._legal_name_col: "SYNTHETIC OWNER A",
                "address":            "1 Main Street",
                "assessed_value":     "550000",
                "te_source":          self._te_source,
                "te_geo_hash":        self._geo_hash,
            },
            {
                self._source_id_col:  f"{self._town_slug.upper()[:6]}-000002",
                self._legal_name_col: "SYNTHETIC OWNER B LLC",
                "address":            "2 Elm Street",
                "assessed_value":     "720000",
                "te_source":          self._te_source,
                "te_geo_hash":        self._geo_hash,
            },
        ]

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        all_bronze: List[Dict[str, Any]] = []

        if self._is_placeholder_url():
            logger.info(
                "ArlingtonPropertyScraper | URL is not live for '%s' — trying LLM synthesis.",
                self._town_slug,
            )
        else:
            page = 1
            try:
                while True:
                    html = self.fetch_page(page)
                    page_records = self.parse_records(html)
                    all_bronze.extend(page_records)
                    at_cap = self._max_pages is not None and page >= self._max_pages
                    if at_cap or not page_records or not self._has_next_page(html):
                        break
                    page += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonPropertyScraper | Live fetch failed (%s). Trying LLM synthesis.", exc
                )

        if not all_bronze:
            all_bronze = self._fetch_llm()

        if not all_bronze:
            logger.info(
                "ArlingtonPropertyScraper | LLM returned 0 records — using synthetic fallback."
            )
            all_bronze = self._generate_synthetic_bronze()

        effective_linker = self._linker or get_linker()
        gold_records: List[Dict[str, Any]] = [
            self._promote_to_gold(b, effective_linker) for b in all_bronze
        ]

        out_path = save_gold_data(
            pd.DataFrame(gold_records), self._town_slug, "property",
            output_dir=output_dir,
        )

        logger.info(
            "ArlingtonPropertyScraper | Wrote %d Gold records -> %s",
            len(gold_records), out_path,
        )
        return out_path
