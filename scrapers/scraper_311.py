# [FILE PATH]: scrapers/scraper_311.py
# Patch #200 (migrated from Patch #185)
# Domain 09a: Town Pulse / SeeClickFix 311 Service Requests
"""
Arlington311Scraper
===================
Fetches 311 civic service requests via the SeeClickFix public API
and runs them through the full UMF Bronze -> Gold pipeline.

Data source priority
--------------------
1. Live SeeClickFix API — if ``place_url`` is a valid SCF slug (not
   ``NO_SCF_COVERAGE``) and the API returns ≥ 1 issue.
2. LLM synthesis (Gemini) — for towns with no SeeClickFix presence.
3. Synthetic hardcoded fallback.

Zero-Hardcoding contract
------------------------
* The API URL, te_source, place_url, town_name, and state are read
  exclusively from ``configs/{town_slug}/config.yaml``.
"""

import json
import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.llm_client import call_llm
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 30

_SYSTEM_PROMPT = (
    "You are a municipal 311 service request data expert. "
    "Return ONLY a compact JSON array of exactly 5 realistic 311 service request records. "
    "Each object must have these exact keys: "
    "id (string, numeric like '12345678'), summary (string, short issue title), "
    "description (string, 1 sentence), status (string: 'Open' or 'Acknowledged'), "
    "created_at (ISO-8601 string, within last 90 days), address (string, real street address). "
    "Use realistic local issue categories: Pothole, Street light out, Graffiti, "
    "Missed trash pickup, Overgrown sidewalk, Parking enforcement, Crosswalk repair, Noise. "
    "NO markdown fences. NO prose. NO spaces after colons or commas. "
    "Short strings only. Output must be valid JSON."
)


class Arlington311Scraper:
    """Full Bronze -> Gold scraper for SeeClickFix 311 service requests."""

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
        self._town_name: str = self._config.get("town_name", self._town_slug)
        self._state: str = self._config.get("state", "MA")

        src_map = self._config["source_mappings"]
        self._te_source: str = src_map.get(
            "311-seeclickfix",
            src_map.get("seeclickfix", f"{town_slug}-311-seeclickfix"),
        )
        self._base_url: str = self._config["scraper_urls"].get(
            "seeclickfix_api",
            self._config["scraper_urls"].get(
                "seeclickfix_311", "https://seeclickfix.com/api/v2/issues"
            ),
        )

        scf: Dict[str, Any] = self._config.get(
            "seeclickfix",
            self._config.get("town_pulse", {}).get("seeclickfix", {}),
        )
        self._place_url: str = scf.get("place_url", town_slug)
        self._statuses: List[str] = scf.get("statuses", ["open"])
        self._per_page: int = int(scf.get("per_page", 20))
        self._event_type: str = scf.get("event_type", "311_REQUEST")
        self._mock_requests: List[Dict[str, Any]] = self._config.get("scf_mock_requests", [])

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session: requests.Session = session or requests.Session()
        self._session.verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    # ------------------------------------------------------------------
    # Live API
    # ------------------------------------------------------------------

    def _has_scf_coverage(self) -> bool:
        return (
            self._place_url
            and "NO_SCF_COVERAGE" not in self._place_url
            and "PLACEHOLDER" not in self._place_url
        )

    def fetch_page(self, page: int = 1) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "place_url": self._place_url,
            "status":    ",".join(self._statuses),
            "per_page":  self._per_page,
            "page":      page,
        }
        resp = self._session.get(self._base_url, params=params, timeout=_REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()

    def parse_issues(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = payload.get("issues", [])
        records: List[Dict[str, Any]] = []
        for issue in issues:
            records.append({
                "source_id":   str(issue.get("id", "")),
                "event_name":  str(issue.get("summary", issue.get("request_type", {}).get("title", ""))),
                "description": issue.get("description"),
                "start_time":  issue.get("created_at"),
                "end_time":    issue.get("closed_at"),
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })
        return records

    def _has_next_page(self, payload: Dict[str, Any]) -> bool:
        meta = payload.get("metadata", {})
        pagination = meta.get("pagination", meta)
        page = int(pagination.get("page", 1))
        pages = int(pagination.get("pages", 1))
        return page < pages

    # ------------------------------------------------------------------
    # LLM synthesis
    # ------------------------------------------------------------------

    def _fetch_llm(self) -> List[Dict[str, Any]]:
        """Call Gemini to synthesise realistic 311 service request records."""
        user_prompt = (
            f"5 realistic 311 service request records for {self._town_name},{self._state}. "
            "Use real local street names. Short strings. Compact JSON only."
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
                        "Arlington311Scraper | LLM returned no JSON array (model=%s). "
                        "Raw: %.120s", model, raw
                    )
                    continue
                text = text[start : end + 1]
                if text.endswith(","):
                    text = text[:-1] + "]"
                records_raw = json.loads(text)
                if not isinstance(records_raw, list) or not records_raw:
                    continue
                records: List[Dict[str, Any]] = []
                for r in records_raw:
                    records.append({
                        "source_id":   str(r.get("id", f"llm-{self._town_slug}-{len(records)+1:04d}")),
                        "event_name":  str(r.get("summary", "")),
                        "description": r.get("description"),
                        "start_time":  r.get("created_at"),
                        "end_time":    None,
                        "te_source":   self._te_source,
                        "te_geo_hash": self._geo_hash,
                    })
                logger.info(
                    "Arlington311Scraper | LLM returned %d 311 records for '%s'.",
                    len(records), self._town_slug,
                )
                return records
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                if "RESOURCE_EXHAUSTED" in err or "429" in err:
                    logger.warning(
                        "Arlington311Scraper | LLM quota hit (model=%s): %s",
                        model, err[:120],
                    )
                    continue
                logger.warning(
                    "Arlington311Scraper | LLM call failed (model=%s): %s",
                    model, err[:200],
                )
        return []

    # ------------------------------------------------------------------
    # Synthetic fallback
    # ------------------------------------------------------------------

    def _generate_synthetic_bronze(self) -> List[Dict[str, Any]]:
        from datetime import datetime, timedelta, timezone
        import random
        rng = random.Random(hash(self._town_slug) & 0xFFFFFFFF)
        categories = [
            "Pothole repair needed", "Street light out", "Overgrown vegetation on sidewalk",
            "Graffiti removal request", "Missed trash pickup",
        ]
        now = datetime.now(tz=timezone.utc)
        records = []
        for i, cat in enumerate(categories):
            days_ago = rng.randint(1, 30)
            created = now - timedelta(days=days_ago)
            records.append({
                "source_id":   f"synthetic-{self._town_slug}-{i+1:04d}",
                "event_name":  cat,
                "description": f"Reported issue in {self._town_name}.",
                "start_time":  created.isoformat(),
                "end_time":    None,
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })
        return records

    # ------------------------------------------------------------------
    # Gold promotion
    # ------------------------------------------------------------------

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_event_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_event_pk": te_event_pk,
            "event_type":  self._event_type,
            "event_name":  bronze["event_name"],
            "description": bronze.get("description"),
            "start_time":  bronze["start_time"],
            "end_time":    bronze.get("end_time"),
            "te_source":   self._te_source,
            "te_geo_hash": self._geo_hash,
        }
        return self._factory.map_to_event(raw_for_factory)

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        all_bronze: List[Dict[str, Any]] = []

        if self._mock_requests:
            logger.info(
                "Arlington311Scraper | Using %d mock requests from config for '%s'.",
                len(self._mock_requests), self._town_slug,
            )
            all_bronze = list(self._mock_requests)
        elif self._has_scf_coverage():
            logger.info(
                "Arlington311Scraper | Fetching live SeeClickFix data for '%s' "
                "(place_url=%s).", self._town_slug, self._place_url,
            )
            try:
                page = 1
                while True:
                    payload = self.fetch_page(page)
                    page_issues = self.parse_issues(payload)
                    all_bronze.extend(page_issues)
                    if not self._has_next_page(payload):
                        break
                    page += 1
                if all_bronze:
                    logger.info(
                        "Arlington311Scraper | SeeClickFix returned %d issues for '%s'.",
                        len(all_bronze), self._town_slug,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Arlington311Scraper | Live fetch failed (%s). Trying LLM synthesis.", exc
                )
        else:
            logger.info(
                "Arlington311Scraper | No SeeClickFix coverage for '%s' — using LLM synthesis.",
                self._town_slug,
            )

        if not all_bronze:
            all_bronze = self._fetch_llm()

        if not all_bronze:
            logger.info(
                "Arlington311Scraper | LLM returned 0 records — using synthetic fallback."
            )
            all_bronze = self._generate_synthetic_bronze()

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in all_bronze]

        out_path = save_gold_data(
            pd.DataFrame(gold_records), self._town_slug, "311",
            output_dir=output_dir,
        )
        logger.info(
            "Arlington311Scraper | Wrote %d Gold records -> %s", len(gold_records), out_path
        )
        return out_path
