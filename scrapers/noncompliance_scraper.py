# [FILE PATH]: scrapers/noncompliance_scraper.py
# Patch #201
# Execution Mode: Domain 17 — Land-Use / Zoning Non-Compliance polygons
# Date: 2026-05-07
"""
ArlingtonNonComplianceScraper -- Domain 17.

Why this domain exists
----------------------
Arlington's planning GIS publishes a polygon layer named
``LandUse_NonCompliance`` that flags every parcel whose recorded
land-use code diverges from current zoning.  These are *descriptive*
indicators (legal pre-existing non-conforming use, expansion-restricted
parcels) — NOT enforcement cases — but they are still material to a
buildability brief because:

  * a non-conforming use can usually continue but cannot be expanded,
  * a tear-down rebuild typically forfeits the non-conforming status,
  * the new structure must conform to current zoning.

Lifted from ``scripts/29_walnut_queries.py::noncompliance(lat, lon)`` —
that script issued a point query for one address; this scraper ingests
every polygon for the configured town once so the report-side code can
answer "is this parcel flagged?" in microseconds against local Parquet.
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


class ArlingtonNonComplianceScraper:
    """Town-agnostic ingestor for the LandUse_NonCompliance FeatureServer."""

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

        # Skip-on-missing-source: a town that does not publish a land-use
        # noncompliance layer opts out of this domain by leaving the URL
        # (or the source mapping) empty/absent in its config.
        scraper_urls = self._config.get("scraper_urls", {})
        service_root = scraper_urls.get("noncompliance_arcgis_url")
        te_source    = self._config.get("source_mappings", {}).get("noncompliance")
        if not service_root or not str(service_root).strip() or not te_source:
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="noncompliance",
                reason="scraper_urls.noncompliance_arcgis_url is missing or empty",
            )
        self._te_source: str = te_source
        self._service_root: str = str(service_root)

        nc_cfg: Dict[str, Any] = self._config.get("noncompliance", {})
        self._land_use_code_fields:        List[str] = list(nc_cfg.get("land_use_code_field_candidates",        ["LandUseCod"]))
        self._zone_code_numeric_fields:    List[str] = list(nc_cfg.get("zone_code_numeric_field_candidates",    ["zonecode"]))
        self._land_use_zone_diff_fields:   List[str] = list(nc_cfg.get("land_use_zone_diff_field_candidates",   ["luzndiff"]))
        self._status_fields:               List[str] = list(nc_cfg.get("status_field_candidates",               ["status"]))

        self._page_size: int = int(nc_cfg.get("page_size", 1000))
        self._max_features: int = int(nc_cfg.get("max_features", 20000))
        self._request_timeout_s: int = int(nc_cfg.get("request_timeout_s", 30))
        self._out_sr: int = int(nc_cfg.get("output_spatial_reference", 4326))

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

    def _enumerate_layers(self) -> List[Dict[str, Any]]:
        url = self._service_root.rstrip("/")
        logger.info(
            "ArlingtonNonComplianceScraper | Enumerating layers at %s ...", url
        )
        resp = self._session.get(url, params={"f": "json"}, timeout=self._request_timeout_s)
        resp.raise_for_status()
        layers = resp.json().get("layers", []) or []
        polys = [
            {"id": L["id"], "name": L.get("name", f"layer_{L['id']}")}
            for L in layers
            if L.get("geometryType") == "esriGeometryPolygon"
        ]
        if not polys:
            raise RuntimeError(
                "ArlingtonNonComplianceScraper | No polygon layers exposed by "
                f"{url}. Check noncompliance_arcgis_url in config."
            )
        logger.info(
            "ArlingtonNonComplianceScraper | Will ingest %d polygon layer(s): %s",
            len(polys), [(L["id"], L["name"]) for L in polys],
        )
        return polys

    def _fetch_layer(self, layer: Dict[str, Any]) -> List[Dict[str, Any]]:
        layer_id = layer["id"]
        layer_name = layer["name"]
        base = f"{self._service_root.rstrip('/')}/{layer_id}/query"
        offset = 0
        all_features: List[Dict[str, Any]] = []
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
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(
                    f"ArlingtonNonComplianceScraper | ArcGIS error on layer "
                    f"{layer_id} offset={offset}: {payload['error']}"
                )
            feats = payload.get("features", []) or []
            if not feats:
                break
            for f in feats:
                f["_layer_id"] = layer_id
                f["_layer_name"] = layer_name
            all_features.extend(feats)
            if len(feats) < self._page_size:
                break
            offset += self._page_size
        logger.info(
            "ArlingtonNonComplianceScraper | Fetched %d feature(s) from "
            "layer '%s'.",
            len(all_features), layer_name,
        )
        return all_features

    def fetch_features(self) -> List[Dict[str, Any]]:
        layers = self._enumerate_layers()
        out: List[Dict[str, Any]] = []
        for layer in layers:
            try:
                out.extend(self._fetch_layer(layer))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonNonComplianceScraper | Layer '%s' failed (%s) — "
                    "continuing.", layer["name"], exc,
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

            object_id = props.get("FID") or props.get("OBJECTID") or ""
            source_id = ":".join(p for p in (
                str(feat.get("_layer_id", "")), str(object_id),
            ) if p) or feat.get("_layer_name", "noncompliance")

            bronze.append({
                "source_id":            source_id,
                "land_use_code":        self._first_non_empty(props, self._land_use_code_fields),
                "zone_code_numeric":    self._first_non_empty(props, self._zone_code_numeric_fields),
                "land_use_zone_diff":   self._first_non_empty(props, self._land_use_zone_diff_fields),
                "status":               self._first_non_empty(props, self._status_fields),
                "geometry_type":        geom.get("type", "Polygon"),
                "geometry_coordinates": coords,
                "metadata": {
                    "raw_attributes": props,
                    "layer_id":       feat.get("_layer_id"),
                    "layer_name":     feat.get("_layer_name"),
                    "source_dataset": self._te_source,
                },
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })
        if skipped:
            logger.warning(
                "ArlingtonNonComplianceScraper | Skipped %d feature(s) without geometry.",
                skipped,
            )
        logger.info("ArlingtonNonComplianceScraper | Bronze records: %d", len(bronze))
        return bronze

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_violation_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_violation_pk":      te_violation_pk,
            "land_use_code":        bronze.get("land_use_code"),
            "zone_code_numeric":    bronze.get("zone_code_numeric"),
            "land_use_zone_diff":   bronze.get("land_use_zone_diff"),
            "status":               bronze.get("status"),
            "geometry_type":        bronze["geometry_type"],
            "geometry_coordinates": bronze["geometry_coordinates"],
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_noncompliance(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        features = self.fetch_features()
        bronze = self.parse_bronze(features)

        effective_linker = self._linker or get_linker()
        gold = [self._promote_to_gold(b, effective_linker) for b in bronze]

        df = pd.DataFrame(gold)
        if not df.empty:
            df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
            df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "noncompliance", output_dir=output_dir)
        logger.info(
            "ArlingtonNonComplianceScraper | Wrote %d non-compliance polygon(s) -> %s",
            len(gold), out_path,
        )
        return out_path
