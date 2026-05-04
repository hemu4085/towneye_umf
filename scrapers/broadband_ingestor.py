# [FILE PATH]: scrapers/broadband_ingestor.py
# Patch #198 — LLM synthesis for broadband (FCC BDC requires auth; LLM fills gap)
"""
ArlingtonBroadbandIngestor -- Domain 06: Connectivity / FCC Broadband.

Data source priority:
  1. Live  — FCC BDC listAvailability API (requires API key — skipped if URL is PLACEHOLDER)
  2. Mock  — broadband_mock_csv_rows fixture in config.yaml
  3. LLM   — Gemini synthesizes realistic ISP records for the town
  4. Synthetic — hardcoded 3-provider fallback so the pipeline never hard-stops
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import csv
import io
import json as _json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 30
_GEO_LEVEL_ADDRESS = "ADDRESS"
_GEO_LEVEL_TOWN = "TOWN"

_SYSTEM_PROMPT = (
    "You are a telecom data expert. "
    "Return ONLY a compact JSON array with NO spaces after colons or commas. "
    "Each object has exactly: provider_name (≤15 chars), technology (FCC code string: 40=cable 50=fiber 70=fixed_wireless), "
    "max_advertised_download_speed (int), max_advertised_upload_speed (int), "
    "low_latency (\"1\"), business_residential_code (\"R\"). "
    "Return exactly 3 records."
)


def _infer_geo_level(location_id: str) -> str:
    loc = location_id.strip()
    if not loc:
        return "UNKNOWN"
    if len(loc) == 6 and loc.isalnum() and " " not in loc:
        return "GEOHASH"
    if loc.isdigit() and len(loc) == 15:
        return "BLOCK"
    if loc.isdigit() and len(loc) == 5:
        return "ZIPCODE"
    parts = loc.split()
    if parts and parts[0].rstrip("-").isdigit():
        return _GEO_LEVEL_ADDRESS
    return _GEO_LEVEL_TOWN


class ArlingtonBroadbandIngestor:

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
        self._town_name: str = self._config.get("town_name", self._town_slug)
        self._state: str = self._config.get("state", "MA")
        self._geo_hash: str = self._config.get("geo_hash", "")
        self._te_source: str = self._config["source_mappings"]["connectivity"]
        self._api_url: str = self._config["scraper_urls"]["fcc_broadband_api"]
        self._mock_rows: List[Dict[str, Any]] = self._config.get("broadband_mock_csv_rows", [])
        self._col_map: Dict[str, str] = self._config.get("broadband_csv_column_map", {})
        self._tech_map: Dict[str, str] = self._config.get("broadband_tech_code_map", {})

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._ssl_verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    def _resolve_tech_type(self, raw_code: Any) -> str:
        return self._tech_map.get(str(raw_code).strip(), "OTHER")

    def _mock_rows_to_csv_stream(self) -> io.StringIO:
        if not self._mock_rows:
            return io.StringIO("")
        all_keys: List[str] = []
        for row in self._mock_rows:
            for k in row:
                if k not in all_keys:
                    all_keys.append(k)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for row in self._mock_rows:
            writer.writerow(row)
        buf.seek(0)
        return buf

    def _synthetic_csv_stream(self) -> io.StringIO:
        """Generate a minimal synthetic broadband CSV when no live or mock data exists."""
        providers = [
            ("Comcast", "40", 1200, 35),
            ("Verizon Fios", "50", 940, 880),
            ("RCN", "40", 500, 20),
        ]
        fieldnames = [
            "brand_name", "technology", "max_advertised_download_speed",
            "max_advertised_upload_speed", "location_id", "low_latency",
            "business_residential_code",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for name, tech, down, up in providers:
            writer.writerow({
                "brand_name": name,
                "technology": tech,
                "max_advertised_download_speed": down,
                "max_advertised_upload_speed": up,
                "location_id": self._town_slug,
                "low_latency": "1",
                "business_residential_code": "R",
            })
        buf.seek(0)
        return buf

    def _fetch_llm(self) -> io.StringIO:
        """Call Gemini to synthesize realistic ISP availability records for this town."""
        try:
            from core.llm_client import call_llm
        except ImportError:
            raise RuntimeError("core.llm_client not available")

        user_prompt = (
            f"3 real ISPs serving {self._town_name},{self._state}. "
            f"Short names (Xfinity,Verizon,RCN,Starlink). No spaces in JSON."
        )
        logger.info(
            "ArlingtonBroadbandIngestor | Calling LLM for broadband data: '%s, %s'",
            self._town_name, self._state,
        )
        # Model preference: 2.5-flash first (best), 2.5-flash-lite as fallback
        for _model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            try:
                raw = call_llm(
                    system=_SYSTEM_PROMPT,
                    user=user_prompt,
                    model=_model,
                    n_tokens=2048,
                )
                break
            except Exception as _model_exc:
                if "429" in str(_model_exc) or "RESOURCE_EXHAUSTED" in str(_model_exc):
                    logger.warning(
                        "ArlingtonBroadbandIngestor | %s quota exhausted, trying next model.", _model
                    )
                    continue
                raise
        else:
            raise RuntimeError("All Gemini models quota-exhausted")
        # Strip markdown fences and extract JSON array from anywhere in the response
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        # Find the JSON array bounds — handles preamble/postamble prose
        arr_start = text.find("[")
        arr_end = text.rfind("]")
        if arr_start != -1 and arr_end > arr_start:
            text = text[arr_start : arr_end + 1]

        logger.debug("ArlingtonBroadbandIngestor | LLM raw (first 200): %s", text[:200])

        import json as _json_mod
        try:
            records = _json_mod.loads(text)
        except _json_mod.JSONDecodeError:
            # Truncation recovery: salvage up to last complete object
            last = text.rfind("}")
            if last != -1:
                try:
                    records = _json_mod.loads(text[: last + 1] + "]")
                    logger.debug("ArlingtonBroadbandIngestor | LLM output truncated — salvaged up to last '}'.")
                except _json_mod.JSONDecodeError as exc2:
                    raise RuntimeError(f"LLM JSON parse failed: {exc2}") from exc2
            else:
                raise RuntimeError("LLM returned no parseable JSON")

        if not isinstance(records, list) or not records:
            raise RuntimeError("LLM returned empty or non-list JSON")

        # Convert to CSV stream matching parse_bronze expectations
        fieldnames = [
            "brand_name", "technology", "max_advertised_download_speed",
            "max_advertised_upload_speed", "location_id", "low_latency",
            "business_residential_code",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "brand_name":                     rec.get("provider_name", "Unknown"),
                "technology":                     str(rec.get("technology", "40")),
                "max_advertised_download_speed":  rec.get("max_advertised_download_speed", 0),
                "max_advertised_upload_speed":    rec.get("max_advertised_upload_speed", 0),
                "location_id":                    self._town_slug,
                "low_latency":                    str(rec.get("low_latency", "1")),
                "business_residential_code":      rec.get("business_residential_code", "R"),
            })
        buf.seek(0)
        logger.info(
            "ArlingtonBroadbandIngestor | LLM returned %d ISP records for '%s'.",
            len(records), self._town_slug,
        )
        return buf

    def fetch_csv_stream(self) -> io.StringIO:
        try:
            import requests
        except ImportError:
            return self._mock_rows_to_csv_stream() if self._mock_rows else self._fetch_llm()

        # 1. Live FCC BDC API — requires POST + OAuth token; plain GET returns 405.
        #    Skip unless the URL has been replaced with a working authenticated endpoint.
        _dead_markers = ("PLACEHOLDER", "broadbandmap.fcc.gov/api/public/map/listAvailability")
        if self._api_url and not any(m in self._api_url for m in _dead_markers):
            try:
                resp = requests.get(self._api_url, timeout=_REQUEST_TIMEOUT_S, verify=self._ssl_verify)
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")
                if "text/csv" in content_type or "application/octet-stream" in content_type:
                    logger.info(
                        "ArlingtonBroadbandIngestor | Live FCC BDC response received for '%s'.",
                        self._town_slug,
                    )
                    return io.StringIO(resp.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonBroadbandIngestor | FCC BDC live fetch failed for '%s': %s",
                    self._town_slug, exc,
                )

        # 2. Config mock fixture
        if self._mock_rows:
            logger.info(
                "ArlingtonBroadbandIngestor | Using mock fixture for '%s'.", self._town_slug
            )
            return self._mock_rows_to_csv_stream()

        # 3. LLM synthesis
        try:
            return self._fetch_llm()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonBroadbandIngestor | LLM synthesis failed for '%s': %s. Using synthetic.",
                self._town_slug, exc,
            )

        # 4. Hard-coded synthetic fallback
        return self._synthetic_csv_stream()

    def parse_bronze(self, csv_stream: io.StringIO) -> List[Dict[str, Any]]:
        fcc_col: Dict[str, str] = self._col_map
        bronze: List[Dict[str, Any]] = []
        reader = csv.DictReader(csv_stream)
        for raw in reader:
            try:
                def _get(canonical: str, fallback: str = "") -> str:
                    fcc_header = fcc_col.get(canonical, canonical)
                    return str(raw.get(fcc_header, raw.get(canonical, fallback))).strip()

                provider_name = _get("provider_name")
                raw_tech_code = _get("fcc_tech_code")
                tech_type = self._resolve_tech_type(raw_tech_code)
                location_id = _get("geo_value")
                geo_level = _infer_geo_level(location_id)

                source_id = str(raw.get("source_id", "")).strip()
                if not source_id:
                    provider_slug = provider_name.lower().replace(" ", "-")[:20]
                    loc_slug = location_id.lower().replace(" ", "-")[:40]
                    source_id = f"{provider_slug}:{raw_tech_code}:{loc_slug}"

                bronze.append({
                    "source_id":    source_id,
                    "geo_level":    geo_level,
                    "geo_value":    location_id,
                    "provider_name": provider_name,
                    "tech_type":    tech_type,
                    "max_down_mbps": float(_get("max_down_mbps") or "0"),
                    "max_up_mbps":  float(_get("max_up_mbps") or "0"),
                    "metadata": {
                        "fcc_tech_code":            raw_tech_code,
                        "low_latency":              _get("low_latency"),
                        "business_residential_code": _get("biz_res_code"),
                    },
                    "te_source":    self._te_source,
                    "te_geo_hash":  self._geo_hash,
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("ArlingtonBroadbandIngestor | Skipping malformed row: %s", exc)
        return bronze

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_broadband_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_broadband_pk": te_broadband_pk,
            "geo_level":       bronze["geo_level"],
            "geo_value":       bronze["geo_value"],
            "provider_name":   bronze["provider_name"],
            "tech_type":       bronze["tech_type"],
            "max_down_mbps":   bronze["max_down_mbps"],
            "max_up_mbps":     bronze["max_up_mbps"],
            "metadata":        bronze.get("metadata", {}),
            "te_source":       self._te_source,
            "te_geo_hash":     self._geo_hash,
        }
        return self._factory.map_to_broadband(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        csv_stream = self.fetch_csv_stream()
        bronze_records = self.parse_bronze(csv_stream)

        if not bronze_records:
            raise ValueError(f"ArlingtonBroadbandIngestor | 0 Bronze records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df = pd.DataFrame(gold_records)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "broadband", output_dir=output_dir)
        logger.info("ArlingtonBroadbandIngestor | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
