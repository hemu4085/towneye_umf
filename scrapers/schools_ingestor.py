# [FILE PATH]: scrapers/schools_ingestor.py
# Patch #185 (migrated from arlington_ma_schools.py)
"""
ArlingtonSchoolCalendarIngestor -- Domain 09b: Economic Pulse / School Calendar ICS.
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 20
_DEFAULT_EVENT_TYPE = "SCHOOL_HOLIDAY"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TownEye/1.0; +https://towneye.com/bot)"}


def _to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


class ArlingtonSchoolCalendarIngestor:

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
        self._geo_hash: str = self._config.get("geo_hash", "")
        self._te_source: str = self._config["source_mappings"]["school_calendar"]
        self._ics_url: str = self._config["scraper_urls"]["school_calendar_ics"]
        self._mock_events: List[Dict[str, Any]] = self._config.get("school_calendar_mock_events", [])

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._ssl_verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    @staticmethod
    def _render_dt_prop(prop_name: str, value: str) -> str:
        if "T" in value:
            compact = value.replace("-", "").replace(":", "")
            if not compact.endswith("Z"):
                compact = compact + "Z"
            return f"{prop_name}:{compact}"
        else:
            compact = value.replace("-", "")
            return f"{prop_name};VALUE=DATE:{compact}"

    def _render_mock_ics(self) -> str:
        events = self._mock_events
        if not events:
            # Generic school calendar events so new towns always have data
            from datetime import datetime, timezone, timedelta
            now = datetime.now(tz=timezone.utc)
            year = now.year
            events = [
                {
                    "uid": f"synthetic-first-day-{year}@{self._town_slug}",
                    "summary": "First Day of School",
                    "dtstart": f"{year}-09-05",
                    "dtend":   f"{year}-09-06",
                    "event_type": "SCHOOL_START",
                    "foot_traffic_impact": "HIGH",
                    "description": "Synthetic event — no live school calendar available",
                },
                {
                    "uid": f"synthetic-thanksgiving-{year}@{self._town_slug}",
                    "summary": "Thanksgiving Recess",
                    "dtstart": f"{year}-11-27",
                    "dtend":   f"{year}-12-02",
                    "event_type": "SCHOOL_HOLIDAY",
                    "foot_traffic_impact": "MODERATE",
                    "description": "Synthetic event — no live school calendar available",
                },
                {
                    "uid": f"synthetic-winter-break-{year}@{self._town_slug}",
                    "summary": "Winter Break",
                    "dtstart": f"{year}-12-23",
                    "dtend":   f"{year+1}-01-03",
                    "event_type": "SCHOOL_HOLIDAY",
                    "foot_traffic_impact": "HIGH",
                    "description": "Synthetic event — no live school calendar available",
                },
            ]
        lines: List[str] = [
            "BEGIN:VCALENDAR", "VERSION:2.0",
            f"PRODID:-//TownEye UMF//{self._town_slug}//EN",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        ]
        for ev in events:
            dtstart = str(ev.get("dtstart", "19700101"))
            dtend   = str(ev.get("dtend",   "19700102"))
            lines += [
                "BEGIN:VEVENT",
                f"UID:{ev.get('uid', 'unknown@towneye')}",
                f"SUMMARY:{ev.get('summary', '')}",
                self._render_dt_prop("DTSTART", dtstart),
                self._render_dt_prop("DTEND",   dtend),
                f"DESCRIPTION:{ev.get('description', '')}",
                f"X-TOWNEYE-EVENT-TYPE:{ev.get('event_type', _DEFAULT_EVENT_TYPE)}",
                f"X-TOWNEYE-FOOT-TRAFFIC:{ev.get('foot_traffic_impact', 'MODERATE')}",
                "END:VEVENT",
            ]
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    def fetch_ics_text(self) -> str:
        try:
            import requests
        except ImportError:
            return self._render_mock_ics()

        if "PLACEHOLDER" in self._ics_url:
            logger.debug(
                "ArlingtonSchoolCalendarIngestor | ICS URL is a placeholder for '%s' — using mock",
                self._town_slug,
            )
            return self._render_mock_ics()

        try:
            resp = requests.get(
                self._ics_url,
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT_S,
                verify=self._ssl_verify,
            )
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "text/calendar" not in content_type and "text/plain" not in content_type:
                return self._render_mock_ics()
            return resp.text
        except Exception:  # noqa: BLE001
            return self._render_mock_ics()

    def parse_bronze(self, ics_text: str) -> List[Dict[str, Any]]:
        try:
            from icalendar import Calendar  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("'icalendar' is required. Run: pip install icalendar>=5.0") from exc

        cal = Calendar.from_ical(ics_text)
        bronze: List[Dict[str, Any]] = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            try:
                uid: str = str(component.get("UID", "")).strip()
                summary: str = str(component.get("SUMMARY", "")).strip()
                description: str = str(component.get("DESCRIPTION", "")).strip() or None

                raw_start = component.get("DTSTART")
                raw_end   = component.get("DTEND")
                start_dt = _to_utc_datetime(raw_start.dt if raw_start else "1970-01-01")
                end_dt   = _to_utc_datetime(raw_end.dt) if raw_end else None

                event_type: str = str(component.get("X-TOWNEYE-EVENT-TYPE", _DEFAULT_EVENT_TYPE)).strip()
                foot_traffic: str = str(component.get("X-TOWNEYE-FOOT-TRAFFIC", "MODERATE")).strip()

                if not uid:
                    uid = f"{summary.lower().replace(' ', '-')[:40]}:{start_dt.date()}"

                bronze.append({
                    "uid":               uid,
                    "event_name":        summary,
                    "event_type":        event_type,
                    "description":       description,
                    "start_time":        start_dt,
                    "end_time":          end_dt,
                    "foot_traffic_impact": foot_traffic,
                    "te_source":         self._te_source,
                    "te_geo_hash":       self._geo_hash,
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("ArlingtonSchoolCalendarIngestor | Skipping VEVENT: %s", exc)
        return bronze

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_event_pk: int = linker.resolve(self._te_source, bronze["uid"])
        raw_for_factory: Dict[str, Any] = {
            "te_event_pk":  te_event_pk,
            "event_type":   bronze["event_type"],
            "event_name":   bronze["event_name"],
            "description":  bronze.get("description"),
            "start_time":   bronze["start_time"],
            "end_time":     bronze.get("end_time"),
            "te_source":    self._te_source,
            "te_geo_hash":  self._geo_hash,
            "_foot_traffic_impact": bronze.get("foot_traffic_impact", "MODERATE"),
        }
        gold = self._factory.map_to_event(raw_for_factory)
        gold["foot_traffic_impact"] = bronze.get("foot_traffic_impact", "MODERATE")
        return gold

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        ics_text = self.fetch_ics_text()
        bronze_records = self.parse_bronze(ics_text)

        if not bronze_records:
            raise ValueError(f"ArlingtonSchoolCalendarIngestor | 0 ICS events for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df = pd.DataFrame(gold_records)
        out_path = save_gold_data(df, self._town_slug, "school-calendar", output_dir=output_dir)
        logger.info("ArlingtonSchoolCalendarIngestor | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
