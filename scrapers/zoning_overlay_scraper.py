# [FILE PATH]: scrapers/zoning_overlay_scraper.py
# Patch #199
# Execution Mode: Domain 15 — Zoning Overlay Polygon (GIS spatial ingestor)
# Date: 2026-05-07
"""
ArlingtonZoningOverlayScraper -- Domain 15: Zoning Overlay Polygons.

Why this domain exists
----------------------
Domain 02 (``zoning``) ingests the *textual bylaw* — for each zone code
("R2", "NMF", "MBMF") it produces a row with ``allowed_uses``,
``max_height_ft``, ``min_lot_sqft``, etc.  What it does NOT have is a
**spatial extent** for each district.  Without polygons you cannot:

* point-in-polygon resolve a parcel to its full applicable rules stack,
* surface the MBTA Communities Act §3A overlays (NMF / MBMF) that
  Massachusetts towns are now required to publish,
* render an overlay-vs-base zone diff in a buildability brief.

This scraper enumerates the configured ``Zoning_and_Overlay_Districts``
FeatureServer, paginates every polygon layer, and writes one Gold row per
polygon to ``data/gold/{town_slug}/zoning-overlay.parquet``.

Lifted from ``scripts/29_walnut_queries.py::zoning(lat, lon)`` and
generalised: that script issued a point query for one address; this
scraper ingests the entire spatial layer once so the report-side code
can answer the same point-in-polygon query in microseconds against
local Parquet.
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


class ArlingtonZoningOverlayScraper:
    """
    Town-agnostic ingestor for an ArcGIS zoning + overlay polygon FeatureServer.

    The class name keeps the registry-friendly ``Arlington…`` prefix for
    symmetry with Domain 01–14, but every value used in ``run()`` is read
    from ``configs/{town_slug}/config.yaml`` — no Arlington-specific
    string ever appears in this file.
    """

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

        # Skip-on-missing-source: opt-out semantics for towns that don't
        # publish a zoning overlay FeatureServer.
        scraper_urls = self._config.get("scraper_urls", {})
        service_root = scraper_urls.get("zoning_overlay_arcgis_url")
        te_source    = self._config.get("source_mappings", {}).get("zoning_overlay")
        if not service_root or not str(service_root).strip() or not te_source:
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="zoning-overlay",
                reason="scraper_urls.zoning_overlay_arcgis_url is missing or empty",
            )
        self._te_source: str = te_source
        self._service_root: str = str(service_root)

        overlay_cfg: Dict[str, Any] = self._config.get("zoning_overlay", {})
        self._code_fields: List[str] = list(
            overlay_cfg.get("code_field_candidates", ["ZoneCode"])
        )
        self._type_fields: List[str] = list(
            overlay_cfg.get("type_field_candidates", ["OverlayType"])
        )
        self._name_fields: List[str] = list(
            overlay_cfg.get("name_field_candidates", ["ZoneName"])
        )
        self._page_size: int = int(overlay_cfg.get("page_size", 500))
        self._max_features: int = int(overlay_cfg.get("max_features", 5000))
        self._request_timeout_s: int = int(overlay_cfg.get("request_timeout_s", 30))
        self._out_sr: int = int(overlay_cfg.get("output_spatial_reference", 4326))

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session: requests.Session = session or requests.Session()
        self._session.verify = _ssl_verify
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; TownEye/1.0)",
        })

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    # ------------------------------------------------------------------
    # Field-name resolution helpers — config-driven, no hardcoded keys
    # ------------------------------------------------------------------

    @staticmethod
    def _first_non_empty(props: Dict[str, Any], candidates: List[str]) -> Optional[str]:
        """First non-empty stripped string value from *candidates* in *props*."""
        for key in candidates:
            v = props.get(key)
            if v is None:
                continue
            s = " ".join(str(v).split())
            if s:
                return s
        return None

    # ------------------------------------------------------------------
    # ArcGIS layer discovery + paginated feature fetch
    # ------------------------------------------------------------------

    def _enumerate_polygon_layers(self) -> List[Dict[str, Any]]:
        """
        Hit the FeatureServer root and return every polygon layer.

        Polygon layer ordering on the service is not guaranteed (Arlington
        has historically reordered after Town Meeting amendments), so the
        scraper re-discovers them on every run.

        Optional config knobs (Tier 5 update):

        * ``zoning_overlay.include_layer_ids`` — allowlist; when present,
          only layers whose ``id`` appears in the list are kept.  Used
          for FeatureServers that publish workshop drafts or unrelated
          editing layers alongside the canonical zoning layer
          (e.g. Lexington's MBTA_MULTIFAMILY_ZONING_editing service has
          15 polygon layers but only ids 13/14 are real zoning).

        * ``zoning_overlay.exclude_layer_ids`` — denylist; applied after
          the allowlist (no-op when both are absent).
        """
        url = self._service_root.rstrip("/")
        logger.info(
            "ArlingtonZoningOverlayScraper | Enumerating layers at %s ...", url
        )
        resp = self._session.get(
            url, params={"f": "json"}, timeout=self._request_timeout_s
        )
        resp.raise_for_status()
        layers = resp.json().get("layers", []) or []
        polygons = [
            {"id": L["id"], "name": L.get("name", f"layer_{L['id']}")}
            for L in layers
            if L.get("geometryType") == "esriGeometryPolygon"
        ]

        # Apply optional include/exclude allowlists.
        overlay_cfg: Dict[str, Any] = self._config.get("zoning_overlay", {}) or {}
        include = overlay_cfg.get("include_layer_ids") or []
        exclude = overlay_cfg.get("exclude_layer_ids") or []
        if include:
            include_set = {int(x) for x in include}
            polygons = [p for p in polygons if int(p["id"]) in include_set]
        if exclude:
            exclude_set = {int(x) for x in exclude}
            polygons = [p for p in polygons if int(p["id"]) not in exclude_set]

        if not polygons:
            raise RuntimeError(
                "ArlingtonZoningOverlayScraper | No polygon layers exposed by "
                f"{url}. Check zoning_overlay_arcgis_url in config."
            )
        logger.info(
            "ArlingtonZoningOverlayScraper | Found %d polygon layer(s): %s",
            len(polygons),
            [L["name"] for L in polygons],
        )
        return polygons

    def _fetch_layer(self, layer: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Page through every feature in a single polygon layer using
        ``resultOffset`` + ``resultRecordCount``.  Tags every feature with
        the originating layer id and name so the parser can preserve
        provenance.
        """
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
            logger.debug(
                "ArlingtonZoningOverlayScraper | GET layer=%d offset=%d",
                layer_id, offset,
            )
            resp = self._session.get(
                base, params=params, timeout=self._request_timeout_s,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(
                    f"ArlingtonZoningOverlayScraper | ArcGIS error on layer "
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
            "ArlingtonZoningOverlayScraper | Fetched %d feature(s) from "
            "layer '%s'.",
            len(all_features), layer_name,
        )
        return all_features

    def fetch_features(self) -> List[Dict[str, Any]]:
        """Return every overlay polygon feature across every layer."""
        polygon_layers = self._enumerate_polygon_layers()
        all_features: List[Dict[str, Any]] = []
        for layer in polygon_layers:
            try:
                all_features.extend(self._fetch_layer(layer))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonZoningOverlayScraper | Layer '%s' failed (%s) — "
                    "continuing with remaining layers.",
                    layer["name"], exc,
                )
        logger.info(
            "ArlingtonZoningOverlayScraper | Total polygons across all "
            "overlay layers: %d",
            len(all_features),
        )
        return all_features

    # ------------------------------------------------------------------
    # Bronze → Gold pipeline
    # ------------------------------------------------------------------

    def _infer_overlay_type(
        self,
        layer_name: str,
        explicit_type: Optional[str],
    ) -> Optional[str]:
        """
        Prefer the feature's own ``OverlayType`` attribute.  When absent,
        fall back to a coarse classification derived from the layer name
        so consumers always get a sensible bucket.

        Layer-name → overlay-type heuristic (case-insensitive, longest-match):
          contains "multi-family" / "neighborhood multi-family" → "Multi-Family"
          contains "historic"                                   → "Historic"
          contains "mass ave" / "corridor"                      → "Corridor"
          contains "industrial" / "office"                      → "Industrial"
          contains "business"                                   → "Business"
          contains "zoning districts" / "base"                  → "Base"

        This is a tiebreaker only — the underlying ``layer_name`` is always
        preserved as a first-class field, so consumers that need the raw
        provenance never lose it.
        """
        if explicit_type:
            return explicit_type
        if not layer_name:
            return None
        n = layer_name.lower()
        if "multi-family" in n or "multi family" in n or "multifamily" in n:
            return "Multi-Family"
        if "historic" in n:
            return "Historic"
        if "mass ave" in n or "corridor" in n:
            return "Corridor"
        if "industrial" in n or "office" in n:
            return "Industrial"
        if "business" in n:
            return "Business"
        if "zoning district" in n or "base zone" in n:
            return "Base"
        return None

    def parse_bronze(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalise GeoJSON overlay features into Bronze dicts."""
        bronze: List[Dict[str, Any]] = []
        skipped_no_geom = 0
        for feat in features:
            props: Dict[str, Any] = feat.get("properties") or feat.get("attributes") or {}
            geom: Dict[str, Any] = feat.get("geometry") or {}

            coords = geom.get("coordinates") or []
            if not coords:
                skipped_no_geom += 1
                continue

            zone_code = self._first_non_empty(props, self._code_fields)
            explicit_type = self._first_non_empty(props, self._type_fields)
            district_name = self._first_non_empty(props, self._name_fields)

            layer_name = feat.get("_layer_name") or "unknown"
            overlay_type = self._infer_overlay_type(layer_name, explicit_type)

            # Synthetic source_id used by the linker.  Composite of layer +
            # zone code + (objectid|district name) so each row gets a
            # deterministic PK and re-runs do not produce duplicates.
            object_id = props.get("OBJECTID") or props.get("OBJECTID_1") or ""
            source_id_parts = [
                str(feat.get("_layer_id", "")),
                str(zone_code or "").strip(),
                str(district_name or "").strip(),
                str(object_id),
            ]
            source_id = ":".join([p for p in source_id_parts if p]) or layer_name

            bronze.append({
                "source_id":            source_id,
                "layer_name":           layer_name,
                "zone_code":            zone_code,
                "overlay_type":         overlay_type,
                "geometry_type":        geom.get("type", "Polygon"),
                "geometry_coordinates": coords,
                "metadata": {
                    "raw_attributes":   props,
                    "layer_id":         feat.get("_layer_id"),
                    "district_name":    district_name,
                    "source_dataset":   self._te_source,
                },
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })

        if skipped_no_geom:
            logger.warning(
                "ArlingtonZoningOverlayScraper | Skipped %d feature(s) "
                "without a usable polygon ring.",
                skipped_no_geom,
            )
        logger.info(
            "ArlingtonZoningOverlayScraper | Bronze records: %d", len(bronze)
        )
        return bronze

    def _promote_to_gold(
        self,
        bronze: Dict[str, Any],
        linker: PartyLinker,
    ) -> Dict[str, Any]:
        te_overlay_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_overlay_pk":        te_overlay_pk,
            "layer_name":           bronze["layer_name"],
            "zone_code":            bronze.get("zone_code"),
            "overlay_type":         bronze.get("overlay_type"),
            "geometry_type":        bronze["geometry_type"],
            "geometry_coordinates": bronze["geometry_coordinates"],
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_zoning_overlay(raw_for_factory)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        features = self.fetch_features()
        bronze_records = self.parse_bronze(features)

        if not bronze_records:
            raise ValueError(
                f"ArlingtonZoningOverlayScraper | 0 Bronze records for "
                f"'{self._town_slug}'.  Check zoning_overlay_arcgis_url in config."
            )

        effective_linker = self._linker or get_linker()
        gold_records = [
            self._promote_to_gold(b, effective_linker) for b in bronze_records
        ]

        df = pd.DataFrame(gold_records)
        df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(
            df, self._town_slug, "zoning-overlay", output_dir=output_dir
        )
        logger.info(
            "ArlingtonZoningOverlayScraper | Wrote %d Gold polygon(s) -> %s",
            len(gold_records), out_path,
        )
        return out_path
