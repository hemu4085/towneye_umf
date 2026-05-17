# [FILE PATH]: scrapers/parcel_scraper.py
# Patch #198 + Tier 5 update
# Execution Mode: Domain 14 — Parcel Geometry (GIS polygon ingestor)
# Date: 2026-05-07
"""
ArlingtonParcelScraper -- Domain 14: Parcel Geometry / GIS Polygons.

Why this domain exists
----------------------
Domain 01 (``property``) ingests the *assessor's tax record* — beds, baths,
year built, assessed value — by HTML-scraping the Patriot Properties portal.
What it does NOT have is **the parcel polygon**.  Without a polygon you cannot:

* compute lot dimensions for a setback / envelope check,
* answer "what is the longest edge that touches Walnut Street?",
* point-in-polygon resolve an arbitrary lat/lon to its parcel,
* render a setback diagram in a buildability brief.

Two source patterns
-------------------
This scraper supports two source patterns out of the box:

* **Per-town FeatureServer** — the town publishes its own "Parcels with
  CAMA" service in ArcGIS Online.  The scraper enumerates every polygon
  layer and pulls all features.  Used by towns that self-host (Arlington's
  original setup).

* **Statewide-with-filter** — a multi-town FeatureServer (e.g. MassGIS L3
  Parcels) hosts every town's parcels in a single layer; the scraper passes
  a ``where`` clause like ``TOWN_ID=10`` to fetch only this town's rows.
  Used by towns that don't self-host but exist in MassGIS L3.  Configured
  via the new ``parcels.where_clause`` knob.

The MassGIS L3 layer carries the **full CAMA assessor record per parcel**
(owner, year built, sale data, lot size, building area, zoning, etc.) in
its raw_attributes — a Path A promoter can lift those into property.parquet
without ever touching Patriot Properties.

Skipped-domain semantics
------------------------
If ``scraper_urls.parcels_arcgis_url`` is missing or empty, the scraper
raises ``DomainNotApplicableError``.  The master loop classifies this as
"skipped" rather than "failed", letting a town opt out of a domain when no
public source exists.

This module is the productionised lift of three ad-hoc functions originally
written as a one-off recovery script for 29 Walnut St:
``scripts/29_walnut_queries.py::parcel`` and ``::parcel_by_id``.
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.master_loop import DomainNotApplicableError
from core.storage import save_gold_data

logger = logging.getLogger(__name__)


class ArlingtonParcelScraper:
    """
    Town-agnostic ingestor for an ArcGIS parcel polygon FeatureServer.

    The class name is kept as ``Arlington…`` for symmetry with the existing
    Domain 01–13 scrapers and the master-loop registry, but every value used
    inside ``run()`` is read from ``configs/{town_slug}/config.yaml``.  No
    Arlington-specific string ever appears in this file.
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
        self._te_source: str = self._config["source_mappings"]["parcel_geometry"]

        # Skip-on-missing-URL semantics: a town that does not publish a
        # parcel layer (and is not in MassGIS L3) opts out of this domain
        # by leaving ``scraper_urls.parcels_arcgis_url`` empty or absent.
        scraper_urls: Dict[str, Any] = self._config.get("scraper_urls", {})
        service_root = scraper_urls.get("parcels_arcgis_url")
        if not service_root or not str(service_root).strip():
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="parcel",
                reason="scraper_urls.parcels_arcgis_url is missing or empty",
            )
        self._service_root: str = str(service_root)

        parcels_cfg: Dict[str, Any] = self._config.get("parcels", {})
        self._id_field_candidates: List[str] = list(
            parcels_cfg.get("id_field_candidates", ["MAP_PAR_ID"])
        )
        self._address_field_candidates: List[str] = list(
            parcels_cfg.get("address_field_candidates", ["SITE_ADDR"])
        )
        # Optional WHERE clause used when ingesting from a statewide layer
        # that holds many towns (e.g. MassGIS L3 with TOWN_ID filter).
        # Defaults to "1=1" — the full-layer behaviour preserved.
        self._where_clause: str = str(parcels_cfg.get("where_clause", "1=1")).strip() or "1=1"
        self._page_size: int = int(parcels_cfg.get("page_size", 1000))
        self._max_features: int = int(parcels_cfg.get("max_features", 50000))
        self._request_timeout_s: int = int(parcels_cfg.get("request_timeout_s", 30))
        self._out_sr: int = int(parcels_cfg.get("output_spatial_reference", 4326))

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
    # Geometry helpers — pure functions, no IO
    # ------------------------------------------------------------------

    @staticmethod
    def _haversine_ft(p1: List[float], p2: List[float]) -> float:
        """
        Great-circle distance between two ``[lon, lat]`` points in feet.
        Suitable for parcel-scale edges (max error <0.05% over 1 km).
        """
        radius_m = 6_371_000
        lat1, lon1 = math.radians(p1[1]), math.radians(p1[0])
        lat2, lon2 = math.radians(p2[1]), math.radians(p2[0])
        a = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        return 2 * radius_m * math.asin(math.sqrt(a)) * 3.28084

    @classmethod
    def _outer_ring(cls, geometry: Dict[str, Any]) -> List[List[float]]:
        """
        Return the outer ring of a GeoJSON Polygon or MultiPolygon as a flat
        list of ``[lon, lat]`` vertex pairs.  Empty list if geometry is missing
        or unsupported.
        """
        if not geometry:
            return []
        gtype = geometry.get("type")
        coords = geometry.get("coordinates") or []
        if not coords:
            return []
        if gtype == "Polygon":
            return list(coords[0])
        if gtype == "MultiPolygon":
            return list(coords[0][0]) if coords and coords[0] else []
        return []

    @classmethod
    def _polygon_area_sqft(cls, ring: List[List[float]]) -> float:
        """
        Approximate the polygon area in square feet using the shoelace
        formula on a local equirectangular projection anchored at the
        centroid.  Accurate to a few percent over parcel-sized lots.
        """
        n = len(ring)
        if n < 3:
            return 0.0
        lat0 = sum(p[1] for p in ring) / n
        cos_lat0 = math.cos(math.radians(lat0))
        feet_per_deg_lat = 364_000.0  # average
        feet_per_deg_lon = feet_per_deg_lat * cos_lat0
        xs = [(p[0]) * feet_per_deg_lon for p in ring]
        ys = [(p[1]) * feet_per_deg_lat for p in ring]
        area2 = 0.0
        for i in range(n - 1):
            area2 += xs[i] * ys[i + 1] - xs[i + 1] * ys[i]
        return abs(area2) / 2.0

    @classmethod
    def _ring_metrics(
        cls,
        ring: List[List[float]],
    ) -> Tuple[List[float], float, float, float, float, float]:
        """
        Compute (edges_ft, perimeter_ft, longest_edge_ft, area_sqft,
        centroid_lat, centroid_lon) for a polygon outer ring.  Returns zeros
        for any malformed ring.
        """
        if len(ring) < 2:
            return [], 0.0, 0.0, 0.0, 0.0, 0.0
        edges = [
            round(cls._haversine_ft(ring[i], ring[i + 1]), 2)
            for i in range(len(ring) - 1)
        ]
        perimeter = round(sum(edges), 2)
        longest = max(edges) if edges else 0.0
        area = round(cls._polygon_area_sqft(ring), 2)
        cy = sum(p[1] for p in ring) / len(ring)
        cx = sum(p[0] for p in ring) / len(ring)
        return edges, perimeter, longest, area, round(cy, 7), round(cx, 7)

    # ------------------------------------------------------------------
    # ArcGIS layer discovery + paginated feature fetch
    # ------------------------------------------------------------------

    def _enumerate_polygon_layers(self) -> List[Dict[str, Any]]:
        """
        Hit the FeatureServer root and return every layer whose
        ``geometryType`` is ``esriGeometryPolygon``.  Polygon ordering on the
        service is not guaranteed, so the scraper does this every run.
        """
        url = self._service_root.rstrip("/")
        logger.info(
            "ArlingtonParcelScraper | Enumerating layers at %s ...", url
        )
        resp = self._session.get(url, params={"f": "json"}, timeout=self._request_timeout_s)
        resp.raise_for_status()
        layers = resp.json().get("layers", []) or []
        polygons = [
            {"id": L["id"], "name": L.get("name", f"layer_{L['id']}")}
            for L in layers
            if L.get("geometryType") == "esriGeometryPolygon"
        ]
        if not polygons:
            raise RuntimeError(
                "ArlingtonParcelScraper | No polygon layers exposed by "
                f"{url}.  Check parcels_arcgis_url in config."
            )
        logger.info(
            "ArlingtonParcelScraper | Found %d polygon layer(s): %s",
            len(polygons),
            [L["name"] for L in polygons],
        )
        return polygons

    def _fetch_layer(self, layer_id: int) -> List[Dict[str, Any]]:
        """
        Page through every feature in a single polygon layer using
        ``resultOffset`` + ``resultRecordCount``.  Returns a flat list of
        GeoJSON Feature dicts.
        """
        base = f"{self._service_root.rstrip('/')}/{layer_id}/query"
        offset = 0
        all_features: List[Dict[str, Any]] = []
        while offset < self._max_features:
            params = {
                "f":                 "geojson",
                "where":             self._where_clause,
                "outFields":         "*",
                "returnGeometry":    "true",
                "outSR":             str(self._out_sr),
                "resultOffset":      str(offset),
                "resultRecordCount": str(self._page_size),
            }
            logger.debug(
                "ArlingtonParcelScraper | GET layer=%d offset=%d page_size=%d",
                layer_id, offset, self._page_size,
            )
            resp = self._session.get(base, params=params, timeout=self._request_timeout_s)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(
                    f"ArlingtonParcelScraper | ArcGIS error on layer {layer_id} "
                    f"offset={offset}: {payload['error']}"
                )
            features = payload.get("features", []) or []
            if not features:
                break
            all_features.extend(features)
            if len(features) < self._page_size:
                break
            offset += self._page_size
        logger.info(
            "ArlingtonParcelScraper | Fetched %d feature(s) from layer %d.",
            len(all_features), layer_id,
        )
        return all_features

    def fetch_features(self) -> List[Dict[str, Any]]:
        """
        Return every parcel polygon feature across every polygon layer in the
        configured FeatureServer.

        Most towns expose a single ``Parcels`` polygon layer; some publish
        separate condo / R.O.W. / vacant layers.  We ingest them all so the
        Gold table is the single source of truth for parcel geometry.
        """
        polygon_layers = self._enumerate_polygon_layers()
        all_features: List[Dict[str, Any]] = []
        for layer in polygon_layers:
            try:
                feats = self._fetch_layer(layer["id"])
                for f in feats:
                    f.setdefault("_layer_id", layer["id"])
                    f.setdefault("_layer_name", layer["name"])
                all_features.extend(feats)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonParcelScraper | Layer %s failed (%s) — continuing.",
                    layer["name"], exc,
                )
        logger.info(
            "ArlingtonParcelScraper | Total features across all polygon "
            "layers: %d",
            len(all_features),
        )
        return all_features

    # ------------------------------------------------------------------
    # Bronze → Gold pipeline
    # ------------------------------------------------------------------

    def _resolve_parcel_id(self, props: Dict[str, Any]) -> Optional[str]:
        """First non-empty value among configured id_field_candidates."""
        for key in self._id_field_candidates:
            v = props.get(key)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                return s
        return None

    def _resolve_address(self, props: Dict[str, Any]) -> Optional[str]:
        """
        Return the first non-empty configured address field, normalised.

        Some assessor-published GIS layers right-pad street names to a
        fixed width (e.g. Arlington's ``fullstreet`` field stores
        ``'29  WALNUT ST                          '``).  We strip
        leading/trailing whitespace **and** collapse any run of internal
        whitespace to a single space so the same address always renders
        identically regardless of the source field used.
        """
        for key in self._address_field_candidates:
            v = props.get(key)
            if v is None:
                continue
            s = " ".join(str(v).split())
            if s:
                return s
        return None

    def parse_bronze(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalise GeoJSON parcel features into Bronze dicts ready for the
        factory.  Drops features that lack a usable parcel id or geometry.
        """
        bronze: List[Dict[str, Any]] = []
        skipped_no_id = 0
        skipped_no_geom = 0
        for feat in features:
            props: Dict[str, Any] = feat.get("properties") or feat.get("attributes") or {}
            geom: Dict[str, Any] = feat.get("geometry") or {}

            parcel_id = self._resolve_parcel_id(props)
            if not parcel_id:
                skipped_no_id += 1
                continue

            ring = self._outer_ring(geom)
            if len(ring) < 3:
                skipped_no_geom += 1
                continue

            edges, perim, longest, area, c_lat, c_lon = self._ring_metrics(ring)

            bronze.append({
                "parcel_id":            parcel_id,
                "address":              self._resolve_address(props),
                "geometry_type":        geom.get("type", "Polygon"),
                "geometry_coordinates": geom.get("coordinates", []),
                "area_sqft":            area,
                "perimeter_ft":         perim,
                "longest_edge_ft":      longest,
                "edges_ft":             edges,
                "centroid_lat":         c_lat,
                "centroid_lon":         c_lon,
                "metadata": {
                    "raw_attributes": props,
                    "layer_id":       feat.get("_layer_id"),
                    "layer_name":     feat.get("_layer_name"),
                    "source_dataset": self._te_source,
                },
                "te_source":   self._te_source,
                "te_geo_hash": self._geo_hash,
            })

        if skipped_no_id or skipped_no_geom:
            logger.warning(
                "ArlingtonParcelScraper | Skipped %d feature(s) without a "
                "parcel id and %d feature(s) without a usable polygon ring.",
                skipped_no_id, skipped_no_geom,
            )
        logger.info(
            "ArlingtonParcelScraper | Bronze records: %d", len(bronze)
        )
        return bronze

    def _promote_to_gold(
        self,
        bronze: Dict[str, Any],
        linker: PartyLinker,
    ) -> Dict[str, Any]:
        te_parcel_pk: int = linker.resolve(self._te_source, bronze["parcel_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_parcel_pk":         te_parcel_pk,
            "parcel_id":            bronze["parcel_id"],
            "address":              bronze.get("address"),
            "geometry_type":        bronze["geometry_type"],
            "geometry_coordinates": bronze["geometry_coordinates"],
            "area_sqft":            bronze.get("area_sqft"),
            "perimeter_ft":         bronze.get("perimeter_ft"),
            "longest_edge_ft":      bronze.get("longest_edge_ft"),
            "edges_ft":             bronze.get("edges_ft", []),
            "centroid_lat":         bronze.get("centroid_lat"),
            "centroid_lon":         bronze.get("centroid_lon"),
            "metadata":             bronze.get("metadata", {}),
            "te_source":            self._te_source,
            "te_geo_hash":          self._geo_hash,
        }
        return self._factory.map_to_parcel(raw_for_factory)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        """
        Execute the full ingestor: fetch → parse → promote → persist.

        Returns the path to the Parquet file written.

        Raises
        ------
        ValueError
            If 0 Bronze records survive parsing.
        RuntimeError
            On unrecoverable upstream errors (e.g. service unreachable).
        """
        features = self.fetch_features()
        bronze_records = self.parse_bronze(features)

        if not bronze_records:
            raise ValueError(
                f"ArlingtonParcelScraper | 0 Bronze records for "
                f"'{self._town_slug}'. Check parcels_arcgis_url and "
                "id_field_candidates in config."
            )

        effective_linker = self._linker or get_linker()
        gold_records = [
            self._promote_to_gold(b, effective_linker) for b in bronze_records
        ]

        df = pd.DataFrame(gold_records)
        # Serialise complex columns to JSON strings so Parquet can persist them
        # losslessly and the report-side loader can round-trip via json.loads.
        df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
        df["edges_ft"] = df["edges_ft"].apply(_json.dumps)
        df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(
            df, self._town_slug, "parcel", output_dir=output_dir
        )
        logger.info(
            "ArlingtonParcelScraper | Wrote %d Gold parcel(s) -> %s",
            len(gold_records), out_path,
        )
        return out_path
