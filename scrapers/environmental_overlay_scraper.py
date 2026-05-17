# [FILE PATH]: scrapers/environmental_overlay_scraper.py
# Patch #203
# Execution Mode: Domain 19 — Environmental Overlay (wetlands + flood zones)
# Date: 2026-05-07
"""
ArlingtonEnvironmentalOverlayScraper -- Domain 19.

Aggregates three water/flood overlay FeatureServers into one Gold parquet:

  * ``wetland``           — town wetlands inventory (~28 polygons)
  * ``flood-effective``   — current FEMA NFHL panels mirrored locally (~1,266)
  * ``flood-preliminary`` — FEMA preliminary updates, e.g. June 2023 (~1,238)

The category column discriminates which source produced each row.  All
share enough schema overlap (FLD_ZONE / fld_zone, plus wetlands' CLASSIF)
that a single ``TeEnvironmentalOverlay`` row covers every case.
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.master_loop import DomainNotApplicableError
from core.storage import save_gold_data

logger = logging.getLogger(__name__)


# Mapping from config-source-key to TeEnvironmentalOverlay.category enum value.
# Kept here (not in YAML) because category is part of the Pydantic schema —
# changing it would be a breaking schema change for downstream consumers.
_CATEGORY_FOR_SOURCE = {
    "wetland":           "wetland",
    "flood_effective":   "flood-effective",
    "flood_preliminary": "flood-preliminary",
}


class ArlingtonEnvironmentalOverlayScraper:
    """Multi-FS aggregator that writes one Gold parquet per town."""

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

        # Skip-on-missing-source: a town that publishes no local wetlands
        # or flood-zone services opts out by leaving the URL dict empty.
        # (Statewide FEMA NFHL is queried separately by the brief
        # generator's spatial layer when the parquet is empty.)
        scraper_urls = self._config.get("scraper_urls", {}) or {}
        urls         = scraper_urls.get("environmental_overlay_arcgis_urls") or {}
        te_source    = self._config.get("source_mappings", {}).get("environmental_overlay")
        if not isinstance(urls, dict) or not urls or not te_source:
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="environmental-overlay",
                reason="scraper_urls.environmental_overlay_arcgis_urls is missing or empty",
            )
        self._te_source: str = te_source
        self._service_urls: Dict[str, str] = {
            k: str(v).strip() for k, v in urls.items() if v and str(v).strip()
        }
        if not self._service_urls:
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="environmental-overlay",
                reason="all environmental_overlay_arcgis_urls values are empty",
            )

        eo_cfg: Dict[str, Any] = self._config.get("environmental_overlay", {})
        self._field_maps: Dict[str, Dict[str, List[str]]] = {
            k: {fk: list(v or []) for fk, v in m.items()}
            for k, m in (eo_cfg.get("source_field_maps", {}) or {}).items()
        }

        self._page_size: int = int(eo_cfg.get("page_size", 1000))
        self._max_features: int = int(eo_cfg.get("max_features", 20000))
        self._request_timeout_s: int = int(eo_cfg.get("request_timeout_s", 30))
        self._out_sr: int = int(eo_cfg.get("output_spatial_reference", 4326))

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session: requests.Session = session or requests.Session()
        self._session.verify = _ssl_verify
        self._session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; TownEye/1.0)"})

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    @staticmethod
    def _first_non_empty(props: Dict[str, Any], candidates: List[str]) -> Optional[str]:
        for key in candidates:
            v = props.get(key)
            if v is None:
                continue
            s = " ".join(str(v).split())
            if s:
                return s
        return None

    @staticmethod
    def _first_non_empty_float(
        props: Dict[str, Any], candidates: List[str],
    ) -> Optional[float]:
        for key in candidates:
            v = props.get(key)
            if v is None:
                continue
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
        return None

    def _fetch_source(self, source_key: str, service_root: str) -> List[Dict[str, Any]]:
        url = service_root.rstrip("/")
        logger.info(
            "ArlingtonEnvironmentalOverlayScraper | [%s] enumerating %s ...",
            source_key, url,
        )
        try:
            resp = self._session.get(
                url, params={"f": "json"}, timeout=self._request_timeout_s,
            )
            resp.raise_for_status()
            layers = resp.json().get("layers", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonEnvironmentalOverlayScraper | [%s] enumerate failed (%s).",
                source_key, exc,
            )
            return []
        polys = [
            {"id": L["id"], "name": L.get("name", f"layer_{L['id']}")}
            for L in layers
            if L.get("geometryType") == "esriGeometryPolygon"
        ]
        if not polys:
            logger.warning(
                "ArlingtonEnvironmentalOverlayScraper | [%s] no polygon layers.",
                source_key,
            )
            return []

        all_features: List[Dict[str, Any]] = []
        for layer in polys:
            base = f"{url}/{layer['id']}/query"
            offset = 0
            while offset < self._max_features:
                params = {
                    "f":                 "geojson",
                    "where":             "1=1",
                    "outFields":         "*",
                    "returnGeometry":    "true",
                    "outSR":             str(self._out_sr),
                    "resultOffset":      str(offset),
                    "resultRecordCount": str(self._page_size),
                }
                resp = self._session.get(
                    base, params=params, timeout=self._request_timeout_s,
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "ArlingtonEnvironmentalOverlayScraper | [%s] layer %d "
                        "offset=%d HTTP %s — skipping rest of layer.",
                        source_key, layer["id"], offset, resp.status_code,
                    )
                    break
                payload = resp.json()
                if payload.get("error"):
                    logger.warning(
                        "ArlingtonEnvironmentalOverlayScraper | [%s] layer %d "
                        "offset=%d ArcGIS error %s — skipping rest of layer.",
                        source_key, layer["id"], offset, payload["error"],
                    )
                    break
                feats = payload.get("features", []) or []
                if not feats:
                    break
                for f in feats:
                    f["_source_key"] = source_key
                    f["_layer_id"]   = layer["id"]
                    f["_layer_name"] = layer["name"]
                all_features.extend(feats)
                if len(feats) < self._page_size:
                    break
                offset += self._page_size
        logger.info(
            "ArlingtonEnvironmentalOverlayScraper | [%s] fetched %d feature(s).",
            source_key, len(all_features),
        )
        return all_features

    def fetch_features(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for source_key, url in self._service_urls.items():
            try:
                out.extend(self._fetch_source(source_key, url))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonEnvironmentalOverlayScraper | source %r failed (%s) — "
                    "continuing.", source_key, exc,
                )
        logger.info(
            "ArlingtonEnvironmentalOverlayScraper | Total features across sources: %d",
            len(out),
        )
        return out

    def parse_bronze(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bronze: List[Dict[str, Any]] = []
        skipped = 0
        for feat in features:
            props: Dict[str, Any] = feat.get("properties") or feat.get("attributes") or {}
            geom: Dict[str, Any] = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if not coords:
                skipped += 1
                continue

            source_key = feat.get("_source_key", "")
            field_map = self._field_maps.get(source_key, {})
            category = _CATEGORY_FOR_SOURCE.get(source_key, source_key)

            object_id = props.get("OBJECTID") or props.get("FID") or ""
            source_id = ":".join(p for p in (
                source_key, str(feat.get("_layer_id", "")), str(object_id),
            ) if p) or feat.get("_layer_name", source_key)

            bronze.append({
                "source_id":            source_id,
                "category":             category,
                "zone_code":            self._first_non_empty(props, field_map.get("zone_code", [])),
                "zone_subtype":         self._first_non_empty(props, field_map.get("zone_subtype", [])),
                "sfha_flag":            self._first_non_empty(props, field_map.get("sfha_flag", [])),
                "static_bfe":           self._first_non_empty_float(props, field_map.get("static_bfe", [])),
                "source_layer_name":    feat.get("_layer_name", source_key),
                "geometry_type":        geom.get("type", "Polygon"),
                "geometry_coordinates": coords,
                "metadata": {
                    "raw_attributes": props,
                    "source_key":     source_key,
                    "layer_id":       feat.get("_layer_id"),
                    "service_root":   self._service_urls.get(source_key),
                    "source_dataset": self._te_source,
                },
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })
        if skipped:
            logger.warning(
                "ArlingtonEnvironmentalOverlayScraper | Skipped %d feature(s) "
                "without geometry.",
                skipped,
            )
        logger.info(
            "ArlingtonEnvironmentalOverlayScraper | Bronze records: %d",
            len(bronze),
        )
        return bronze

    def _promote_to_gold(
        self, bronze: Dict[str, Any], linker: PartyLinker,
    ) -> Dict[str, Any]:
        te_overlay_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_overlay_pk":        te_overlay_pk,
            "category":             bronze["category"],
            "zone_code":            bronze.get("zone_code"),
            "zone_subtype":         bronze.get("zone_subtype"),
            "sfha_flag":            bronze.get("sfha_flag"),
            "static_bfe":           bronze.get("static_bfe"),
            "source_layer_name":    bronze["source_layer_name"],
            "geometry_type":        bronze["geometry_type"],
            "geometry_coordinates": bronze["geometry_coordinates"],
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_environmental_overlay(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        features = self.fetch_features()
        bronze = self.parse_bronze(features)

        effective_linker = self._linker or get_linker()
        gold = [self._promote_to_gold(b, effective_linker) for b in bronze]

        df = pd.DataFrame(gold)
        if not df.empty:
            df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
            df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "environmental-overlay", output_dir=output_dir)
        logger.info(
            "ArlingtonEnvironmentalOverlayScraper | Wrote %d overlay polygon(s) -> %s",
            len(gold), out_path,
        )
        return out_path
