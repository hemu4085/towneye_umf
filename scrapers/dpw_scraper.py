# [FILE PATH]: scrapers/dpw_scraper.py
# Patch #185 (migrated from arlington_ma_dpw.py)
# Patch #195 (LLM-backed infra synthesis when no live PDF)
"""
ArlingtonDPWScraper -- Domain 04: Infra Friction / DPW Capital Plans.

Data-source priority
--------------------
1. Live PDF download  (``dpw_capital_plans_pdf`` config URL via pdfplumber)
2. Config mock fixture (``dpw_mock_projects``)
3. LLM synthesis      (Gemini / OpenAI / Anthropic via ``core.llm_client``)
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
    You are a municipal infrastructure expert.  Return ONLY a JSON array
    (no markdown fences, no explanation) of 3 realistic capital improvement
    projects for the given US municipality, based on your knowledge of that
    town's publicly available Capital Improvement Plan (CIP).

    Each element must have exactly these fields:
    {
      "project_id":           "<TOWN-DPW-NNN>",
      "project_name":         "<official project name, ≤8 words>",
      "project_type":         "<one of: ROAD_PAVING|WATER_MAIN|SEWER_MAIN|SIDEWALK|BRIDGE|PARK|OTHER>",
      "status":               "<one of: PLANNED|DESIGN|BID|IN_PROGRESS|COMPLETED|DEFERRED>",
      "estimated_cost":       <float USD or null>,
      "start_date":           "<YYYY-MM-DD or null>",
      "end_date":             "<YYYY-MM-DD or null>",
      "location_description": "<street or area, ≤10 words>",
      "metadata":             {"source_note": "<10 words max>"}
    }

    IMPORTANT DATE RULE: All start_date and end_date values MUST be on or
    after TODAY_DATE (provided in the user prompt). Projects with status
    PLANNED, DESIGN, or BID must have start_date in the future.
    Projects with status IN_PROGRESS may have a past start_date but must
    have a future end_date. Never generate dates before TODAY_DATE unless
    status is COMPLETED or DEFERRED.

    Use real street names and project types consistent with the town's CIP.
    Output nothing except the JSON array.
""").strip()


class ArlingtonDPWScraper:

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
        self._te_source: str = self._config["source_mappings"]["infra_friction"]
        self._pdf_url: str = self._config["scraper_urls"]["dpw_capital_plans_pdf"]
        self._mock_projects: List[Dict[str, Any]] = self._config.get("dpw_mock_projects", [])

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._ssl_verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    def _parse_date(self, value: Any) -> Optional[datetime]:
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

    def fetch_from_pdf(self) -> List[Dict[str, Any]]:
        """Attempt to extract CIP project rows from a live PDF URL."""
        if "PLACEHOLDER" in self._pdf_url:
            return []
        try:
            import pdfplumber  # type: ignore[import]
            import requests
            import io
        except ImportError:
            return []

        try:
            resp = requests.get(self._pdf_url, timeout=_REQUEST_TIMEOUT_S, verify=self._ssl_verify)
            resp.raise_for_status()
        except Exception:  # noqa: BLE001
            return []

        rows: List[Dict[str, Any]] = []
        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables():
                        if not table or len(table) < 2:
                            continue
                        headers = [str(h).strip().lower() for h in table[0]]
                        for row in table[1:]:
                            rows.append(dict(zip(headers, row)))
        except Exception:  # noqa: BLE001
            return []
        return rows

    def _fetch_llm(self) -> Optional[List[Dict[str, Any]]]:
        """Ask the LLM to synthesize CIP projects from its training knowledge."""
        today = datetime.now(tz=timezone.utc).date().isoformat()
        user_prompt = (
            f"TODAY_DATE is {today}. "
            f"Return 3 capital improvement projects for {self._town_name}, {self._state}, USA, "
            f"based on the town's public Capital Improvement Plan. "
            f"All dates must be on or after {today}."
        )
        logger.info(
            "ArlingtonDPWScraper | Calling LLM for CIP data: '%s, %s'",
            self._town_name, self._state,
        )
        try:
            raw = call_llm(system=_SYSTEM_PROMPT, user=user_prompt, n_tokens=2048)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArlingtonDPWScraper | LLM call failed (%s).", exc)
            return None

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        # Recover from truncation: close the array at the last complete object
        if not raw.rstrip().endswith("]"):
            last_brace = raw.rfind("}")
            if last_brace != -1:
                raw = raw[: last_brace + 1] + "\n]"
                logger.debug("ArlingtonDPWScraper | LLM output truncated — salvaged to last '}'.")

        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            logger.warning(
                "ArlingtonDPWScraper | LLM response not valid JSON (%s). Raw[:300]: %s",
                exc, raw[:300],
            )
            return None

        if not isinstance(parsed, list) or not parsed:
            logger.warning("ArlingtonDPWScraper | LLM returned unexpected structure: %s", type(parsed))
            return None

        logger.info(
            "ArlingtonDPWScraper | LLM returned %d CIP projects for '%s'.",
            len(parsed), self._town_slug,
        )
        return parsed

    # ------------------------------------------------------------------
    # Bronze assembly
    # ------------------------------------------------------------------

    def fetch_bronze(self) -> List[Dict[str, Any]]:
        """
        Return CIP project records from the highest-priority available source.

        Priority: live PDF → config mock fixture → LLM synthesis.
        """
        raw = self.fetch_from_pdf()

        if not raw and self._mock_projects:
            logger.info(
                "ArlingtonDPWScraper | Using config mock fixture (%d projects).",
                len(self._mock_projects),
            )
            raw = list(self._mock_projects)

        if not raw:
            llm_data = self._fetch_llm()
            if llm_data:
                raw = llm_data

        if not raw:
            logger.warning(
                "ArlingtonDPWScraper | All live sources failed for '%s' — using synthetic fallback.",
                self._town_slug,
            )
            raw = [
                {
                    "project_id":    f"{self._town_slug.upper()[:6]}-CIP-001",
                    "project_name":  "Road Resurfacing Program",
                    "project_type":  "ROAD_PAVING",
                    "status":        "PLANNED",
                    "estimated_cost": 1500000.0,
                    "start_date":    None,
                    "end_date":      None,
                    "description":   "Annual road resurfacing for deteriorated roadways.",
                    "funding_source": "General Fund",
                    "department":    "DPW",
                },
                {
                    "project_id":    f"{self._town_slug.upper()[:6]}-CIP-002",
                    "project_name":  "Stormwater Infrastructure Upgrade",
                    "project_type":  "DRAINAGE",
                    "status":        "IN_PROGRESS",
                    "estimated_cost": 850000.0,
                    "start_date":    None,
                    "end_date":      None,
                    "description":   "Upgrade aging stormwater pipes to meet current capacity.",
                    "funding_source": "State Grant",
                    "department":    "DPW",
                },
                {
                    "project_id":    f"{self._town_slug.upper()[:6]}-CIP-003",
                    "project_name":  "Sidewalk Accessibility Improvements",
                    "project_type":  "SIDEWALK",
                    "status":        "PLANNED",
                    "estimated_cost": 450000.0,
                    "start_date":    None,
                    "end_date":      None,
                    "description":   "ADA-compliant curb cuts and sidewalk repairs.",
                    "funding_source": "Federal ADA Grant",
                    "department":    "DPW",
                },
            ]

        bronze: List[Dict[str, Any]] = []
        for item in raw:
            try:
                bronze.append({
                    "project_id":           str(item.get("project_id", "")),
                    "project_name":         str(item.get("project_name", "")).strip(),
                    "project_type":         str(item.get("project_type", "OTHER")).upper(),
                    "status":               str(item.get("status", "PLANNED")).upper(),
                    "estimated_cost":       float(item["estimated_cost"]) if item.get("estimated_cost") is not None else None,
                    "start_date":           self._parse_date(item.get("start_date")),
                    "end_date":             self._parse_date(item.get("end_date")),
                    "location_description": str(item.get("location_description", "")).strip(),
                    "metadata":             dict(item.get("metadata", {})),
                    "te_source":            self._te_source,
                    "te_geo_hash":          self._geo_hash,
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("ArlingtonDPWScraper | Skipping malformed record: %s", exc)
        return bronze

    # ------------------------------------------------------------------
    # Bronze → Gold pipeline (unchanged)
    # ------------------------------------------------------------------

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_project_pk: int = linker.resolve(self._te_source, bronze["project_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_project_pk":        te_project_pk,
            "project_name":         bronze["project_name"],
            "project_type":         bronze["project_type"],
            "status":               bronze["status"],
            "estimated_cost":       bronze.get("estimated_cost"),
            "start_date":           bronze.get("start_date"),
            "end_date":             bronze.get("end_date"),
            "location_description": bronze["location_description"],
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_infra_project(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        bronze_records = self.fetch_bronze()

        if not bronze_records:
            raise ValueError(f"ArlingtonDPWScraper | 0 Bronze records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df = pd.DataFrame(gold_records)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "infra-projects", output_dir=output_dir)
        logger.info("ArlingtonDPWScraper | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
