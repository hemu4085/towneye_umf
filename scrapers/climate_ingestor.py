# [FILE PATH]: scrapers/climate_ingestor.py
# Patch #197 — FEMA NFHL live WFS wired (arcgis endpoint, bbox geometry query)
"""
ArlingtonClimateIngestor -- Domain 07: Climate Resilience / FEMA NFHL Flood Zones.

Data source priority:
  1. Live  — FEMA NFHL ArcGIS REST API (hazards.fema.gov/arcgis) + town bbox
  2. Mock  — climate_mock_geojson fixture in config.yaml
  3. Synthetic — minimal single-zone placeholder so the pipeline never hard-stops
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 30


class ArlingtonClimateIngestor:

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
        self._te_source: str = self._config["source_mappings"]["climate_resilience"]
        self._wfs_url: str = self._config["scraper_urls"]["fema_nfhl_wfs"]
        self._mock_geojson: Dict[str, Any] = self._config.get("climate_mock_geojson", {})
        self._flood_zone_map: Dict[str, Dict[str, str]] = self._config.get("climate_flood_zone_map", {})

        fema_wfs_cfg: Dict[str, Any] = self._config.get("climate_fema_wfs_params", {})
        raw_bbox: str = fema_wfs_cfg.get("bbox", "")
        self._fema_bbox: str = raw_bbox  # stored separately; built into ArcGIS geometry param at query time
        self._fema_wfs_params: Dict[str, Any] = {
            "where":            fema_wfs_cfg.get("where", "1=1"),
            "outFields":        fema_wfs_cfg.get("out_fields", "FLD_ZONE,SFHA_TF,DFIRM_ID,ZONE_SUBTY"),
            "f":                "json",
            "returnGeometry":   "false",
            "resultRecordCount": "2000",
        }

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._ssl_verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    def _classify_fema_zone(self, fema_zone: Optional[str]) -> Tuple[str, str]:
        if not fema_zone:
            return "OTHER", "UNDETERMINED"
        key = str(fema_zone).strip().upper()
        entry = self._flood_zone_map.get(key, {})
        return entry.get("zone_type", "FLOOD_100YR"), entry.get("risk_level", "UNDETERMINED")

    def _synthetic_geojson(self) -> Dict[str, Any]:
        """Return a minimal synthetic flood-zone GeoJSON for towns with no live or mock data."""
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "fema_zone": "X",
                        "zone_type": "FLOOD_500YR",
                        "risk_level": "MODERATE",
                        "source_id": f"{self._te_source}:X:synthetic",
                        "description": "Synthetic flood zone data (no live FEMA data available)",
                    },
                    "geometry": {"type": "Polygon", "coordinates": []},
                },
            ],
        }

    def fetch_geojson(self) -> Dict[str, Any]:
        try:
            import requests
        except ImportError:
            return self._mock_geojson or self._synthetic_geojson()

        bbox = self._fema_bbox.strip()
        if not bbox or "PLACEHOLDER" in bbox.upper():
            logger.warning(
                "ArlingtonClimateIngestor | No bbox configured for '%s' — skipping live FEMA fetch.",
                self._town_slug,
            )
            return self._mock_geojson or self._synthetic_geojson()

        # ArcGIS NFHL layer 28 (Flood_Hazard_Area) accepts a plain
        # "xmin,ymin,xmax,ymax" bbox string with inSR=4326.
        # Layer 28 does NOT expose COMMUNITY_ID or STATE_CD — use where=1=1
        # and let the geometry envelope do all the spatial filtering.
        # The JSON-envelope form with spatialReference caused 504 timeouts;
        # the simple string form is confirmed to return HTTP 200.
        params = {
            "where":             "1=1",
            "geometry":          bbox,      # e.g. "-71.17,42.39,-71.13,42.44"
            "geometryType":      "esriGeometryEnvelope",
            "inSR":              "4326",
            "outFields":         "FLD_ZONE,SFHA_TF,ZONE_SUBTY",
            "returnGeometry":    "false",
            "resultRecordCount": "200",
            "f":                 "json",
        }

        logger.info(
            "ArlingtonClimateIngestor | Querying FEMA NFHL for '%s' (bbox=%s) ...",
            self._town_slug,
            bbox,
        )
        try:
            resp = requests.get(
                self._wfs_url,
                params=params,
                timeout=_REQUEST_TIMEOUT_S,
                verify=self._ssl_verify,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TownEye/1.0)"},
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                logger.warning(
                    "ArlingtonClimateIngestor | FEMA API error for '%s': %s",
                    self._town_slug, payload["error"],
                )
                return self._mock_geojson or self._synthetic_geojson()
            features = payload.get("features", [])
            logger.info(
                "ArlingtonClimateIngestor | FEMA returned %d feature(s) for '%s'.",
                len(features), self._town_slug,
            )
            if not features:
                return self._mock_geojson or self._synthetic_geojson()
            return payload
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonClimateIngestor | FEMA live fetch failed for '%s': %s. Falling back.",
                self._town_slug, exc,
            )
            return self._mock_geojson or self._synthetic_geojson()

    def parse_bronze(self, feature_collection: Dict[str, Any]) -> List[Dict[str, Any]]:
        features: List[Dict[str, Any]] = feature_collection.get("features", [])
        bronze: List[Dict[str, Any]] = []
        for idx, feat in enumerate(features):
            try:
                # Support both ArcGIS JSON (attributes/rings) and GeoJSON (properties/coordinates)
                props: Dict[str, Any] = feat.get("attributes") or feat.get("properties") or {}
                geom: Dict[str, Any] = feat.get("geometry") or {}

                zone_type = props.get("zone_type")
                risk_level = props.get("risk_level")
                fema_zone = props.get("fema_zone") or props.get("FLD_ZONE")
                if not zone_type or not risk_level:
                    zone_type, risk_level = self._classify_fema_zone(fema_zone)

                dfirm_id = props.get("dfirm_id") or props.get("DFIRM_ID") or "NFHL"
                source_id: str = (
                    str(props.get("source_id", "")).strip()
                    or f"{self._te_source}:{dfirm_id}:{fema_zone or 'UNK'}:{idx}"
                )

                # ArcGIS JSON uses "rings"; GeoJSON uses "coordinates"
                coordinates = geom.get("coordinates") or geom.get("rings") or []

                bronze.append({
                    "source_id":            source_id,
                    "zone_type":            str(zone_type).upper(),
                    "risk_level":           str(risk_level).upper(),
                    "geometry_type":        geom.get("type", "Polygon"),
                    "geometry_coordinates": coordinates,
                    "metadata": {
                        "description":    props.get("description", ""),
                        "fema_zone":      fema_zone,
                        "zone_subtype":   props.get("ZONE_SUBTY") or props.get("zone_subty", ""),
                        "dfirm_id":       props.get("dfirm_id") or props.get("DFIRM_ID"),
                        "sfha":           props.get("SFHA_TF") or props.get("sfha_tf", ""),
                        "census_tract":   props.get("census_tract", ""),
                        "source_dataset": self._te_source,
                    },
                    "te_source":   self._te_source,
                    "te_geo_hash": self._geo_hash,
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("ArlingtonClimateIngestor | Skipping malformed feature: %s", exc)
        return bronze

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_zone_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_zone_pk":           te_zone_pk,
            "zone_type":            bronze["zone_type"],
            "risk_level":           bronze["risk_level"],
            "geometry_type":        bronze["geometry_type"],
            "geometry_coordinates": bronze["geometry_coordinates"],
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_climate_zone(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        feature_collection = self.fetch_geojson()
        bronze_records = self.parse_bronze(feature_collection)

        if not bronze_records:
            raise ValueError(f"ArlingtonClimateIngestor | 0 Bronze records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df = pd.DataFrame(gold_records)
        df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "climate-zones", output_dir=output_dir)
        logger.info("ArlingtonClimateIngestor | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
