# [FILE PATH]: scrapers/local_historic_scraper.py
# Patch #202
# Execution Mode: Domain 18 — Local Historic Resources (multi-source aggregator)
# Date: 2026-05-07
"""
ArlingtonLocalHistoricScraper -- Domain 18.

Aggregates Arlington's four locally-hosted historic-resource FeatureServers:

  * ``Local_Historic_District``           — per-parcel LHD assignments (~406 polygons)
  * ``National_Historic_District``        — singleton NHD boundary polyline (1)
  * ``Historic_Overlay_Districts``        — the 7 named LHD areas (7 polygons)
  * ``Historic_Commission_Inventory_view``— AHC inventory points (~1,226)

All four are normalised into the existing ``TeHistoricResource`` schema.
This is the **town-level** counterpart to Domain 16 (statewide MACRIS).
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

# GeoJSON geometry-type names used internally — we map ArcGIS esri-types
# to GeoJSON-style strings during parse so downstream code is uniform.
_ESRI_TO_GEOJSON_GEOMETRY = {
    "Point":      "Point",
    "LineString": "LineString",
    "Polygon":    "Polygon",
    "MultiPoint":      "MultiPoint",
    "MultiLineString": "MultiLineString",
    "MultiPolygon":    "MultiPolygon",
}


class ArlingtonLocalHistoricScraper:
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

        # Skip-on-missing-source: this scraper is a multi-FeatureServer
        # aggregator.  A town with no local-historic infrastructure opts
        # out by leaving local_historic_arcgis_urls absent or empty.
        scraper_urls = self._config.get("scraper_urls", {}) or {}
        urls         = scraper_urls.get("local_historic_arcgis_urls") or {}
        te_source    = self._config.get("source_mappings", {}).get("local_historic")
        if not isinstance(urls, dict) or not urls or not te_source:
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="local-historic",
                reason="scraper_urls.local_historic_arcgis_urls is missing or empty",
            )
        self._te_source: str = te_source
        self._service_urls: Dict[str, str] = {
            k: str(v).strip() for k, v in urls.items() if v and str(v).strip()
        }
        if not self._service_urls:
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="local-historic",
                reason="all local_historic_arcgis_urls values are empty",
            )

        lh_cfg: Dict[str, Any] = self._config.get("local_historic", {})
        self._field_maps: Dict[str, Dict[str, List[str]]] = {
            k: {fk: list(v or []) for fk, v in m.items()}
            for k, m in (lh_cfg.get("source_field_maps", {}) or {}).items()
        }
        self._default_legends: Dict[str, str] = dict(
            lh_cfg.get("source_default_legends", {})
        )

        # Tier 5 cleanup (2026-05-07): some MA towns publish the historic survey
        # FeatureServer with extra layers (full town parcels, district polygons)
        # alongside the canonical historic-points layer.  ``source_layer_filters``
        # lets a per-source-key {include_layer_ids|exclude_layer_ids} map narrow
        # the enumerate-and-page loop to only the real historic data.  Example
        # (Lexington):
        #   local_historic:
        #     source_layer_filters:
        #       survey: {include_layer_ids: [0]}
        # Arlington omits the block — all four of its FeatureServers are single-
        # purpose, so the un-filtered behaviour is correct.
        self._source_layer_filters: Dict[str, Dict[str, List[int]]] = {
            k: {
                "include_layer_ids": [int(x) for x in (v.get("include_layer_ids") or [])],
                "exclude_layer_ids": [int(x) for x in (v.get("exclude_layer_ids") or [])],
            }
            for k, v in (lh_cfg.get("source_layer_filters", {}) or {}).items()
        }

        self._page_size: int = int(lh_cfg.get("page_size", 1000))
        self._max_features: int = int(lh_cfg.get("max_features", 20000))
        self._request_timeout_s: int = int(lh_cfg.get("request_timeout_s", 30))
        self._out_sr: int = int(lh_cfg.get("output_spatial_reference", 4326))

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

    def _fetch_source(self, source_key: str, service_root: str) -> List[Dict[str, Any]]:
        """Enumerate every layer (point/polygon/polyline) of one FS and page through it."""
        url = service_root.rstrip("/")
        logger.info(
            "ArlingtonLocalHistoricScraper | [%s] enumerating %s ...",
            source_key, url,
        )
        try:
            resp = self._session.get(url, params={"f": "json"}, timeout=self._request_timeout_s)
            resp.raise_for_status()
            layers = resp.json().get("layers", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonLocalHistoricScraper | [%s] failed to enumerate (%s).",
                source_key, exc,
            )
            return []

        usable = [
            {
                "id":   L["id"],
                "name": L.get("name", f"layer_{L['id']}"),
                "geometryType": L.get("geometryType"),
            }
            for L in layers
            if L.get("geometryType") in (
                "esriGeometryPoint", "esriGeometryPolygon", "esriGeometryPolyline",
            )
        ]

        # Apply per-source layer filter (introduced in Tier 5 cleanup).
        layer_filter = self._source_layer_filters.get(source_key, {})
        include_ids = layer_filter.get("include_layer_ids") or []
        exclude_ids = layer_filter.get("exclude_layer_ids") or []
        if include_ids:
            before = len(usable)
            usable = [L for L in usable if int(L["id"]) in include_ids]
            logger.info(
                "ArlingtonLocalHistoricScraper | [%s] include_layer_ids=%s "
                "narrowed %d -> %d layer(s).",
                source_key, include_ids, before, len(usable),
            )
        elif exclude_ids:
            before = len(usable)
            usable = [L for L in usable if int(L["id"]) not in exclude_ids]
            logger.info(
                "ArlingtonLocalHistoricScraper | [%s] exclude_layer_ids=%s "
                "dropped %d -> %d layer(s).",
                source_key, exclude_ids, before, len(usable),
            )

        if not usable:
            logger.warning(
                "ArlingtonLocalHistoricScraper | [%s] no usable layers.",
                source_key,
            )
            return []

        all_features: List[Dict[str, Any]] = []
        for layer in usable:
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
                resp = self._session.get(base, params=params, timeout=self._request_timeout_s)
                if resp.status_code >= 400:
                    logger.warning(
                        "ArlingtonLocalHistoricScraper | [%s] layer %d offset=%d "
                        "HTTP %s — skipping rest of layer.",
                        source_key, layer["id"], offset, resp.status_code,
                    )
                    break
                payload = resp.json()
                if payload.get("error"):
                    logger.warning(
                        "ArlingtonLocalHistoricScraper | [%s] layer %d offset=%d "
                        "ArcGIS error %s — skipping rest of layer.",
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
            "ArlingtonLocalHistoricScraper | [%s] fetched %d feature(s).",
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
                    "ArlingtonLocalHistoricScraper | source %r failed (%s) — "
                    "continuing.", source_key, exc,
                )
        logger.info(
            "ArlingtonLocalHistoricScraper | Total features across all sources: %d",
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

            source_key: str = feat.get("_source_key", "")
            field_map = self._field_maps.get(source_key, {})

            mhcn = self._first_non_empty(props, field_map.get("mhcn", []))
            object_id = props.get("OBJECTID") or props.get("FID") or ""
            source_id = ":".join(p for p in (
                str(source_key),
                str(feat.get("_layer_id", "")),
                str(mhcn or "").strip(),
                str(object_id),
            ) if p) or feat.get("_layer_name", source_key)

            legend = self._first_non_empty(props, field_map.get("legend", []))
            if not legend:
                legend = self._default_legends.get(source_key)

            bronze.append({
                "source_id":            source_id,
                "mhcn":                 mhcn,
                "resource_kind":        self._first_non_empty(props, field_map.get("resource_kind", [])),
                "legend":               legend,
                "designation":          self._first_non_empty(props, field_map.get("designation", [])),
                "designation_date":     self._first_non_empty(props, field_map.get("designation_date", [])),
                "historic_name":        self._first_non_empty(props, field_map.get("historic_name", [])),
                "common_name":          self._first_non_empty(props, field_map.get("common_name", [])),
                "address":              self._first_non_empty(props, field_map.get("address", [])),
                "town_name":            self._town_slug.split("-")[0].title(),
                "construction_date":    self._first_non_empty(props, field_map.get("construction_date", [])),
                "architectural_style":  self._first_non_empty(props, field_map.get("architectural_style", [])),
                "architect":            self._first_non_empty(props, field_map.get("architect", [])),
                "use_type":             self._first_non_empty(props, field_map.get("use_type", [])),
                "significance":         self._first_non_empty(props, field_map.get("significance", [])),
                "demolished":           self._first_non_empty(props, field_map.get("demolished", [])),
                "geometry_type":        geom.get("type", "Polygon"),
                "geometry_coordinates": coords,
                "metadata": {
                    "raw_attributes": props,
                    "source_key":     source_key,
                    "layer_id":       feat.get("_layer_id"),
                    "layer_name":     feat.get("_layer_name"),
                    "source_dataset": self._te_source,
                },
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })
        if skipped:
            logger.warning(
                "ArlingtonLocalHistoricScraper | Skipped %d feature(s) without geometry.",
                skipped,
            )
        logger.info("ArlingtonLocalHistoricScraper | Bronze records: %d", len(bronze))
        return bronze

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_resource_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_resource_pk":       te_resource_pk,
            "mhcn":                 bronze.get("mhcn"),
            "resource_kind":        bronze.get("resource_kind"),
            "legend":               bronze.get("legend"),
            "designation":          bronze.get("designation"),
            "designation_date":     bronze.get("designation_date"),
            "historic_name":        bronze.get("historic_name"),
            "common_name":          bronze.get("common_name"),
            "address":              bronze.get("address"),
            "town_name":            bronze["town_name"],
            "construction_date":    bronze.get("construction_date"),
            "architectural_style":  bronze.get("architectural_style"),
            "architect":            bronze.get("architect"),
            "use_type":             bronze.get("use_type"),
            "significance":         bronze.get("significance"),
            "demolished":           bronze.get("demolished"),
            "geometry_type":        bronze["geometry_type"],
            "geometry_coordinates": bronze["geometry_coordinates"],
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_historic_resource(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        features = self.fetch_features()
        bronze = self.parse_bronze(features)

        effective_linker = self._linker or get_linker()
        gold = [self._promote_to_gold(b, effective_linker) for b in bronze]

        df = pd.DataFrame(gold)
        if not df.empty:
            df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
            df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "local-historic", output_dir=output_dir)
        logger.info(
            "ArlingtonLocalHistoricScraper | Wrote %d local-historic record(s) -> %s",
            len(gold), out_path,
        )
        return out_path
