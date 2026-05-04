# [FILE PATH]: scrapers/transit_scraper.py
# Patch #185 (migrated from arlington_ma_transit.py)
"""
ArlingtonTransitScraper -- Domain 08: Town Pulse / MBTA Transit Alerts.
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 30


class ArlingtonTransitScraper:

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
        self._te_source: str = self._config["source_mappings"]["mbta-alerts"]
        self._base_url: str = self._config["scraper_urls"]["mbta_alerts"]

        mbta: Dict[str, Any] = self._config["town_pulse"]["mbta"]
        self._routes: List[str] = mbta["routes"]
        self._activities: List[str] = mbta["activities"]
        self._event_type: str = mbta["event_type"]

        api_key_env: str = mbta.get("api_key_env", "")
        self._api_key: Optional[str] = os.environ.get(api_key_env) if api_key_env else None

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        self._session: requests.Session = session or requests.Session()
        self._session.verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    def _generate_synthetic_alerts(self) -> List[Dict[str, Any]]:
        """Return placeholder transit alerts for towns with no configured MBTA routes."""
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        return [
            {
                "source_id":   f"synthetic-{self._town_slug}-transit-001",
                "event_name":  "Service Information",
                "description": f"No MBTA routes configured for {self._town_slug}. Add route IDs to configs/{self._town_slug}/config.yaml → town_pulse.mbta.routes.",
                "start_time":  now,
                "end_time":    None,
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            },
        ]

    def fetch_alerts(self, url: Optional[str] = None) -> Dict[str, Any]:
        if url is None:
            target = self._base_url
            params: Optional[Dict[str, Any]] = {
                "filter[route]":    ",".join(self._routes),
                "filter[activity]": ",".join(self._activities),
            }
        else:
            target = url
            params = None

        headers: Dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        resp = self._session.get(target, params=params, headers=headers, timeout=_REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()

    def _build_description(self, attrs: Dict[str, Any]) -> Optional[str]:
        parts: List[str] = []
        effect: str = attrs.get("effect", "")
        if effect:
            parts.append(f"Effect: {effect.replace('_', ' ').title()}")
        severity = attrs.get("severity")
        if severity is not None:
            parts.append(f"Severity: {severity}/10")
        service_effect: str = attrs.get("service_effect", "")
        if service_effect:
            parts.append(service_effect)
        description: str = attrs.get("description", "")
        if description:
            parts.append(description)
        return " | ".join(parts) if parts else None

    def _extract_times(self, attrs: Dict[str, Any]):
        active_period: List[Dict[str, Any]] = attrs.get("active_period") or []
        if active_period:
            start = active_period[0].get("start") or attrs.get("created_at")
            end = active_period[0].get("end")
        else:
            start = attrs.get("created_at") or attrs.get("updated_at")
            end = None
        if not start:
            start = datetime.now(timezone.utc).isoformat()
        return start, end

    def parse_alerts(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = payload.get("data", [])
        records: List[Dict[str, Any]] = []
        for alert in alerts:
            attrs: Dict[str, Any] = alert.get("attributes", {})
            start_time, end_time = self._extract_times(attrs)
            records.append({
                "source_id":   alert["id"],
                "event_name":  (attrs.get("header") or attrs.get("service_effect") or f"MBTA-{alert['id']}"),
                "description": self._build_description(attrs),
                "start_time":  start_time,
                "end_time":    end_time,
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })
        return records

    def _has_next_page(self, payload: Dict[str, Any]) -> Optional[str]:
        return payload.get("links", {}).get("next") or None

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

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        all_bronze: List[Dict[str, Any]] = []
        next_url: Optional[str] = None

        if not self._routes:
            logger.info(
                "ArlingtonTransitScraper | No MBTA routes configured for '%s' — using synthetic fallback.",
                self._town_slug,
            )
            all_bronze = self._generate_synthetic_alerts()
        else:
            try:
                while True:
                    payload = self.fetch_alerts(url=next_url)
                    page_alerts = self.parse_alerts(payload)
                    all_bronze.extend(page_alerts)
                    next_url = self._has_next_page(payload)
                    if not next_url:
                        break
            except Exception as exc:  # noqa: BLE001
                logger.warning("ArlingtonTransitScraper | Live fetch failed (%s). Using synthetic.", exc)
                all_bronze = self._generate_synthetic_alerts()

        if not all_bronze:
            logger.info("ArlingtonTransitScraper | 0 live alerts — using synthetic fallback.")
            all_bronze = self._generate_synthetic_alerts()

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in all_bronze]

        out_path = save_gold_data(
            pd.DataFrame(gold_records), self._town_slug, "transit",
            output_dir=output_dir,
        )
        logger.info("ArlingtonTransitScraper | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
