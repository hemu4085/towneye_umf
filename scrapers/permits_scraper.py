# [FILE PATH]: scrapers/permits_scraper.py
# Patch #185 (migrated from arlington_ma_permits.py)
# Patch #196 (LLM-backed permit synthesis when no live API)
"""
ArlingtonPermitScraper -- Domain 05: Permit Velocity / Building Permits.

Data-source priority
--------------------
1. Live API        (``permits_api`` config URL via requests)
2. Config fixture  (``permit_mock_data``)
3. LLM synthesis   (Gemini / OpenAI / Anthropic via ``core.llm_client``)
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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.llm_client import call_llm
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 20

_SYSTEM_PROMPT = textwrap.dedent("""
    You are a municipal building department expert.  Return ONLY a JSON array
    (no markdown fences, no explanation) of 3 realistic recent building permit
    records for the given US municipality.

    Each element must have exactly these fields:
    {
      "permit_number":    "<TOWN-YYYY-NNNN>",
      "permit_type":      "<one of: RESIDENTIAL_NEW|RESIDENTIAL_RENO|COMMERCIAL_BUILD|ELECTRICAL|MECHANICAL|SOLAR|DEMOLITION>",
      "status":           "<one of: SUBMITTED|UNDER_REVIEW|APPROVED|INSPECTIONS|CLOSED>",
      "application_date": "<YYYY-MM-DD>",
      "approval_date":    "<YYYY-MM-DD or null>",
      "estimated_value":  <float USD>,
      "applicant_name":   "<realistic contractor or owner name>",
      "applicant_id":     "<TOWN-APPLICANT-NNN>",
      "metadata":         {"source_note": "<10 words max>"}
    }

    IMPORTANT DATE RULE: All dates must be within the 90 days ending on
    TODAY_DATE (provided in the user prompt). The permit_number year field
    must match TODAY_DATE's year. Never generate dates in a past year.

    Use realistic street addresses and contractor names consistent with the town.
    Mix permit types across the 3 records. Output nothing except the JSON array.
""").strip()


class ArlingtonPermitScraper:

    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
        linker: Optional[PartyLinker] = None,
        factory: Optional[MedallionFactory] = None,
    ) -> None:
        loader = ConfigLoader(base_dir=config_base_dir)
        self._config: Dict[str, Any] = loader.get_town_config(town_slug)

        self._town_slug: str = self._config["town_slug"]
        self._town_name: str = self._config.get("town_name", town_slug)
        self._state: str = self._config.get("state", "")
        self._geo_hash: str = self._config.get("geo_hash", "")
        self._te_source_permits: str = self._config["source_mappings"]["permits"]
        self._te_source_applicants: str = self._config["source_mappings"]["tax-assessor"]
        self._api_url: str = self._config["scraper_urls"]["permits_api"]
        self._mock_data: List[Dict[str, Any]] = self._config.get("permit_mock_data", [])

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._ssl_verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if str(value).lower() in ("null", "none", ""):
            return None
        try:
            dt = datetime.fromisoformat(str(value))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Data-fetch methods (priority order)
    # ------------------------------------------------------------------

    def fetch_from_api(self) -> List[Dict[str, Any]]:
        """Attempt to fetch permit records from the configured live API URL."""
        if "PLACEHOLDER" in self._api_url:
            return []
        try:
            import requests
        except ImportError:
            return []
        try:
            resp = requests.get(self._api_url, timeout=_REQUEST_TIMEOUT_S, verify=self._ssl_verify)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, list):
                return payload
            for key in ("permits", "results", "data", "records"):
                if isinstance(payload.get(key), list):
                    return payload[key]
            return []
        except Exception:  # noqa: BLE001
            return []

    def _fetch_llm(self) -> Optional[List[Dict[str, Any]]]:
        """Ask the LLM to synthesize realistic permit records."""
        today = datetime.now(tz=timezone.utc).date().isoformat()
        user_prompt = (
            f"TODAY_DATE is {today}. "
            f"Return 3 recent building permit records for {self._town_name}, {self._state}, USA, "
            f"representative of the town's typical construction activity. "
            f"All dates must be within the 90 days ending on {today}."
        )
        logger.info(
            "ArlingtonPermitScraper | Calling LLM for permit data: '%s, %s'",
            self._town_name, self._state,
        )
        try:
            raw = call_llm(system=_SYSTEM_PROMPT, user=user_prompt, n_tokens=2048)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArlingtonPermitScraper | LLM call failed (%s).", exc)
            return None

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        # Recover from truncation at the last complete object
        if not raw.rstrip().endswith("]"):
            last_brace = raw.rfind("}")
            if last_brace != -1:
                raw = raw[: last_brace + 1] + "\n]"
                logger.debug("ArlingtonPermitScraper | LLM output truncated — salvaged to last '}'.")

        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            logger.warning(
                "ArlingtonPermitScraper | LLM response not valid JSON (%s). Raw[:300]: %s",
                exc, raw[:300],
            )
            return None

        if not isinstance(parsed, list) or not parsed:
            logger.warning("ArlingtonPermitScraper | LLM returned unexpected structure: %s", type(parsed))
            return None

        logger.info(
            "ArlingtonPermitScraper | LLM returned %d permit records for '%s'.",
            len(parsed), self._town_slug,
        )
        return parsed

    # ------------------------------------------------------------------
    # Bronze assembly
    # ------------------------------------------------------------------

    def fetch_bronze(self) -> List[Dict[str, Any]]:
        """
        Return permit records from the highest-priority available source.

        Priority: live API → config mock fixture → LLM synthesis.
        """
        raw = self.fetch_from_api()

        if not raw and self._mock_data:
            logger.info(
                "ArlingtonPermitScraper | Using config mock fixture (%d records).",
                len(self._mock_data),
            )
            raw = list(self._mock_data)

        if not raw:
            llm_data = self._fetch_llm()
            if llm_data:
                raw = llm_data

        if not raw:
            logger.warning(
                "ArlingtonPermitScraper | All live sources failed for '%s' — using synthetic fallback.",
                self._town_slug,
            )
            from datetime import date
            raw = [
                {
                    "permit_number": f"{self._town_slug.upper()[:6]}-2025-001",
                    "permit_type": "BUILDING",
                    "status": "ISSUED",
                    "issue_date": str(date.today()),
                    "expiry_date": None,
                    "address": "1 Main Street",
                    "description": "Interior renovation",
                    "estimated_value": 45000.0,
                    "applicant_name": "SYNTHETIC OWNER A",
                },
                {
                    "permit_number": f"{self._town_slug.upper()[:6]}-2025-002",
                    "permit_type": "ELECTRICAL",
                    "status": "PENDING",
                    "issue_date": str(date.today()),
                    "expiry_date": None,
                    "address": "2 Elm Street",
                    "description": "Panel upgrade",
                    "estimated_value": 8500.0,
                    "applicant_name": "SYNTHETIC OWNER B",
                },
                {
                    "permit_number": f"{self._town_slug.upper()[:6]}-2025-003",
                    "permit_type": "PLUMBING",
                    "status": "ISSUED",
                    "issue_date": str(date.today()),
                    "expiry_date": None,
                    "address": "3 Oak Ave",
                    "description": "Water heater replacement",
                    "estimated_value": 3200.0,
                    "applicant_name": "SYNTHETIC OWNER C",
                },
            ]

        bronze: List[Dict[str, Any]] = []
        for item in raw:
            try:
                bronze.append({
                    "permit_number":    str(item.get("permit_number", "")).strip(),
                    "permit_type":      str(item.get("permit_type", "OTHER")).upper(),
                    "status":           str(item.get("status", "SUBMITTED")).upper(),
                    "application_date": self._parse_date(item.get("application_date")),
                    "approval_date":    self._parse_date(item.get("approval_date")),
                    "estimated_value":  float(item["estimated_value"]) if item.get("estimated_value") is not None else None,
                    "applicant_name":   str(item.get("applicant_name", "")).strip(),
                    "applicant_id":     str(item.get("applicant_id", "")).strip(),
                    "metadata":         dict(item.get("metadata", {})),
                    "te_geo_hash":      self._geo_hash,
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("ArlingtonPermitScraper | Skipping malformed record: %s", exc)
        return bronze

    # ------------------------------------------------------------------
    # Bronze → Gold pipeline (unchanged)
    # ------------------------------------------------------------------

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_permit_pk: int = linker.resolve(self._te_source_permits, bronze["permit_number"])
        te_party_pk_applicant: int = linker.resolve(self._te_source_applicants, bronze["applicant_id"])

        raw_for_factory: Dict[str, Any] = {
            "te_permit_pk":          te_permit_pk,
            "permit_number":         bronze["permit_number"],
            "permit_type":           bronze["permit_type"],
            "status":                bronze["status"],
            "application_date":      bronze["application_date"],
            "approval_date":         bronze.get("approval_date"),
            "estimated_value":       bronze.get("estimated_value"),
            "te_party_pk_applicant": te_party_pk_applicant,
            "metadata":              bronze.get("metadata", {}),
            "te_source":             self._te_source_permits,
            "te_geo_hash":           self._geo_hash,
        }
        return self._factory.map_to_permit(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        bronze_records = self.fetch_bronze()

        if not bronze_records:
            raise ValueError(f"ArlingtonPermitScraper | 0 Bronze records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df = pd.DataFrame(gold_records)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "permits", output_dir=output_dir)
        logger.info("ArlingtonPermitScraper | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
