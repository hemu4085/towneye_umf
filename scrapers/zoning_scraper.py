# [FILE PATH]: scrapers/zoning_scraper.py
# Patch #185 (migrated from arlington_ma_zoning.py)
# Patch #194 (LLM-backed zoning extraction)
"""
ArlingtonZoningScraper -- Domain 02: Regulatory Layer / Zoning Bylaws.

Data-source priority
--------------------
1. Live JSON endpoint (``zoning_bylaws_json`` config URL, if not PLACEHOLDER)
2. Config mock fixture  (``zoning_bylaws_mock_data``)
3. LLM extraction       (Gemini / OpenAI / Anthropic via ``core.llm_client``)
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json
import logging
import re
import textwrap
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.llm_client import call_llm
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 15

_SYSTEM_PROMPT = textwrap.dedent("""
    You are a municipal zoning expert.  Return ONLY a JSON array
    (no markdown fences, no explanation) of the 2 most important zoning
    districts for the given US municipality — one residential, one commercial.

    Each element must have exactly these fields:
    {
      "zone_code":        "<official abbreviation, e.g. R-1>",
      "zone_description": "<official name, 4 words max>",
      "allowed_uses":     ["<use1>", "<use2>", "<use3>"],
      "max_height_ft":    <integer or null>,
      "metadata":         {"source_note": "<10 words max>"}
    }

    Use the town's actual official zone codes. Output nothing except the JSON array.
""").strip()


class ArlingtonZoningScraper:

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
        self._town_name: str = self._config.get("town_name", town_slug)
        self._state: str = self._config.get("state", "")
        self._geo_hash: str = self._config.get("geo_hash", "")
        self._te_source: str = self._config["source_mappings"]["zoning_bylaws"]
        self._bylaws_url: str = self._config["scraper_urls"]["zoning_bylaws_json"]
        self._mock_data: List[Dict[str, Any]] = self._config.get("zoning_bylaws_mock_data", [])

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session: requests.Session = session or requests.Session()
        self._session.verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    # ------------------------------------------------------------------
    # Data-fetch methods (priority order)
    # ------------------------------------------------------------------

    def _fetch_live(self) -> Optional[List[Dict[str, Any]]]:
        """Attempt to fetch zoning JSON from the configured live URL."""
        if "PLACEHOLDER" in self._bylaws_url:
            return None
        logger.info("ArlingtonZoningScraper | GET %s", self._bylaws_url)
        try:
            resp = self._session.get(self._bylaws_url, timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                logger.info(
                    "ArlingtonZoningScraper | Live URL returned %d districts.", len(data)
                )
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonZoningScraper | Live URL failed (%s). Trying next source.", exc
            )
        return None

    def _fetch_llm(self) -> Optional[List[Dict[str, Any]]]:
        """Ask the LLM to extract zoning districts from its training knowledge."""
        user_prompt = (
            f"Return the top zoning districts for {self._town_name}, {self._state}, USA. "
            f"Use the official zone codes and descriptions from {self._town_name}'s "
            f"adopted zoning bylaw."
        )
        logger.info(
            "ArlingtonZoningScraper | Calling LLM for zoning data: '%s, %s'",
            self._town_name, self._state,
        )
        try:
            # gemini-2.5-flash is a thinking model — ask for just 2 districts so
            # the visible JSON output stays well under the effective output limit.
            raw = call_llm(
                system=_SYSTEM_PROMPT,
                user=user_prompt,
                n_tokens=2048,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArlingtonZoningScraper | LLM call failed (%s).", exc)
            return None

        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        # If the response was truncated mid-JSON, attempt to recover complete
        # objects by finding the last well-formed closing brace before the cut.
        if not raw.rstrip().endswith("]"):
            last_brace = raw.rfind("}")
            if last_brace != -1:
                raw = raw[: last_brace + 1] + "\n]"
                logger.debug(
                    "ArlingtonZoningScraper | LLM output truncated — salvaged up to last '}'."
                )

        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            logger.warning(
                "ArlingtonZoningScraper | LLM response is not valid JSON (%s). "
                "Raw (first 300 chars): %s",
                exc, raw[:300],
            )
            return None

        if not isinstance(parsed, list) or not parsed:
            logger.warning(
                "ArlingtonZoningScraper | LLM returned unexpected structure: %s",
                type(parsed),
            )
            return None

        logger.info(
            "ArlingtonZoningScraper | LLM returned %d zoning districts for '%s'.",
            len(parsed), self._town_slug,
        )
        return parsed

    def fetch_bylaws(self) -> List[Dict[str, Any]]:
        """
        Return zoning districts from the highest-priority available source.

        Priority: live JSON endpoint → config mock fixture → LLM extraction.
        """
        data = self._fetch_live()
        if data:
            return data

        if self._mock_data:
            logger.info(
                "ArlingtonZoningScraper | Using config mock fixture (%d districts).",
                len(self._mock_data),
            )
            return list(self._mock_data)

        data = self._fetch_llm()
        if data:
            return data

        # Should never reach here — LLM fallback is the last resort
        raise RuntimeError(
            f"ArlingtonZoningScraper | All data sources exhausted for '{self._town_slug}'. "
            "Set GEMINI_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY) to enable LLM extraction."
        )

    # ------------------------------------------------------------------
    # Bronze → Gold pipeline (unchanged)
    # ------------------------------------------------------------------

    def parse_districts(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bronze: List[Dict[str, Any]] = []
        for item in raw:
            bronze.append({
                "zone_code":        str(item["zone_code"]).strip().upper(),
                "zone_description": str(item.get("zone_description", "")).strip(),
                "allowed_uses":     list(item.get("allowed_uses", [])),
                "max_height_ft":    item.get("max_height_ft"),
                "metadata":         dict(item.get("metadata", {})),
                "te_source":        self._te_source,
                "te_geo_hash":      self._geo_hash,
            })
        return bronze

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        source_id: str = bronze["zone_code"]
        te_zoning_pk: int = linker.resolve(self._te_source, source_id)
        raw_for_factory: Dict[str, Any] = {
            "te_zoning_pk":     te_zoning_pk,
            "zone_code":        bronze["zone_code"],
            "zone_description": bronze["zone_description"],
            "allowed_uses":     bronze["allowed_uses"],
            "max_height_ft":    bronze.get("max_height_ft"),
            "metadata":         bronze.get("metadata", {}),
            "te_source":        self._te_source,
            "te_geo_hash":      self._geo_hash,
        }
        return self._factory.map_to_zoning(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        raw = self.fetch_bylaws()
        bronze_records = self.parse_districts(raw)

        if not bronze_records:
            raise ValueError(f"ArlingtonZoningScraper | 0 records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df = pd.DataFrame(gold_records)
        df["allowed_uses"] = df["allowed_uses"].apply(_json.dumps)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "zoning", output_dir=output_dir)
        logger.info(
            "ArlingtonZoningScraper | Wrote %d Gold records -> %s", len(gold_records), out_path
        )
        return out_path

