# [FILE PATH]: scrapers/macris_scraper.py
# Patch #200
# Execution Mode: Domain 16 — MACRIS Historic Resources (statewide, town-filtered)
# Date: 2026-05-07
"""
ArlingtonMacrisScraper -- Domain 16: MACRIS Historic Resources.

Why this domain exists
----------------------
MACRIS (Massachusetts Cultural Resource Information System) is the
state-level inventory of every recognised historic resource —
individual buildings, districts, burial grounds, statues, monuments —
maintained by the Massachusetts Historical Commission.  Buildability
analysis needs to answer:

  * "Is this address MACRIS-listed?"           (point match)
  * "Is this address inside a historic district?"  (polygon match)
  * "What's the legal designation?"            (NRHP / LHD / NHL / Inv.)

A positive answer can mean demolition delays, design review by the
local Historical Commission, or §106 federal review — all of which
materially affect what a buyer can do with the lot.

Source
------
The scraper points at MAPC's canonical statewide group layer:

  https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/MHC_Inventory_GDB/FeatureServer

  layer 0 -- Points    (~226k statewide)
  layer 1 -- Polygons  (~7k  statewide)
  layer 2 -- Town status  (skipped; metadata only)

A previous version of the codebase pointed at gis.bostonplans.org's
MHC_Historic_Inventory mirror — which turned out to be Boston-only
(every TOWN_NAME = 'Boston'), explaining why the buildability brief
historically reported zero MACRIS hits for any non-Boston address.
The MAPC-hosted service used here covers all 351 MA municipalities.

Lifted from ``scripts/29_walnut_queries.py::macris(lat, lon)`` and
generalised: that script issued a 30m point-buffer query for one
address; this scraper ingests every MACRIS record for the configured
town once so the report-side code can answer point-and-polygon
questions in microseconds against local Parquet.
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


class ArlingtonMacrisScraper:
    """
    Town-agnostic ingestor for the MAPC-hosted statewide MACRIS service.

    The class name keeps the registry-friendly ``Arlington…`` prefix for
    symmetry with Domain 01–15, but every value used in ``run()`` is read
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

        # Skip-on-missing-source: a town opts out of MACRIS by leaving
        # historic_resources.macris_arcgis_url or macris_town_name empty.
        # MACRIS itself is statewide, but a town with no inventory rows
        # (or no source_mappings.historic_resources) cleanly opts out.
        hr_cfg: Dict[str, Any] = self._config.get("historic_resources", {}) or {}
        service_root = hr_cfg.get("macris_arcgis_url")
        town_name    = hr_cfg.get("macris_town_name")
        te_source    = self._config.get("source_mappings", {}).get("historic_resources")
        if (
            not service_root or not str(service_root).strip()
            or not town_name or not str(town_name).strip()
            or not te_source
        ):
            raise DomainNotApplicableError(
                town_slug=town_slug,
                domain="macris",
                reason="historic_resources.macris_arcgis_url / macris_town_name is missing",
            )
        self._te_source: str = te_source
        self._service_root: str = str(service_root)
        self._town_name: str = str(town_name)

        m_cfg: Dict[str, Any] = self._config.get("macris", {})
        self._exclude_layer_ids = set(int(x) for x in m_cfg.get("exclude_layer_ids", []))
        self._town_field_candidates: List[str] = list(
            m_cfg.get("town_filter_field_candidates", ["TOWN_NAME"])
        )
        self._mhcn_fields:                List[str] = list(m_cfg.get("mhcn_field_candidates",                ["MHCN"]))
        self._resource_kind_fields:       List[str] = list(m_cfg.get("resource_kind_field_candidates",       ["TYPE"]))
        self._legend_fields:              List[str] = list(m_cfg.get("legend_field_candidates",              ["LEGEND"]))
        self._designation_fields:         List[str] = list(m_cfg.get("designation_field_candidates",         ["DESIGNATIO"]))
        self._designation_date_fields:    List[str] = list(m_cfg.get("designation_date_field_candidates",    ["D_DATE"]))
        self._historic_name_fields:       List[str] = list(m_cfg.get("historic_name_field_candidates",       ["HISTORIC_N"]))
        self._common_name_fields:         List[str] = list(m_cfg.get("common_name_field_candidates",         ["COMMON_NAM"]))
        self._address_fields:             List[str] = list(m_cfg.get("address_field_candidates",             ["ADDRESS"]))
        self._construction_date_fields:   List[str] = list(m_cfg.get("construction_date_field_candidates",   ["CONSTRUCTI"]))
        self._architectural_style_fields: List[str] = list(m_cfg.get("architectural_style_field_candidates", ["ARCHITECTU", "ARCH"]))
        self._architect_fields:           List[str] = list(m_cfg.get("architect_field_candidates",           ["MAKER"]))
        self._use_type_fields:            List[str] = list(m_cfg.get("use_type_field_candidates",            ["USE_TYPE"]))
        self._significance_fields:        List[str] = list(m_cfg.get("significance_field_candidates",        ["SIGNIFICAN"]))
        self._demolished_fields:          List[str] = list(m_cfg.get("demolished_field_candidates",          ["DEMOLISHED"]))

        self._page_size: int = int(m_cfg.get("page_size", 1000))
        self._max_features: int = int(m_cfg.get("max_features", 50000))
        self._request_timeout_s: int = int(m_cfg.get("request_timeout_s", 30))
        self._out_sr: int = int(m_cfg.get("output_spatial_reference", 4326))

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

    def _detect_town_field(self, layer_url: str) -> Optional[str]:
        """
        Return the first town-filter field name that exists on *layer_url*.

        We try each candidate against the layer's schema endpoint rather
        than firing speculative queries (an unknown field returns "Failed
        to execute query." with no count).
        """
        sch = self._session.get(
            layer_url, params={"f": "json"}, timeout=self._request_timeout_s
        ).json()
        present = {f["name"] for f in sch.get("fields", [])}
        for cand in self._town_field_candidates:
            if cand in present:
                return cand
        return None

    # ------------------------------------------------------------------
    # ArcGIS layer discovery + paginated feature fetch
    # ------------------------------------------------------------------

    def _enumerate_layers(self) -> List[Dict[str, Any]]:
        """Return every (point|polygon) layer the FeatureServer exposes."""
        url = self._service_root.rstrip("/")
        logger.info(
            "ArlingtonMacrisScraper | Enumerating layers at %s ...", url
        )
        resp = self._session.get(
            url, params={"f": "json"}, timeout=self._request_timeout_s
        )
        resp.raise_for_status()
        layers = resp.json().get("layers", []) or []
        keep = [
            {
                "id":   L["id"],
                "name": L.get("name", f"layer_{L['id']}"),
                "geometryType": L.get("geometryType"),
            }
            for L in layers
            if L["id"] not in self._exclude_layer_ids
            and L.get("geometryType") in ("esriGeometryPoint", "esriGeometryPolygon")
        ]
        if not keep:
            raise RuntimeError(
                "ArlingtonMacrisScraper | No usable layers exposed by "
                f"{url}. Check macris_arcgis_url in config."
            )
        logger.info(
            "ArlingtonMacrisScraper | Will ingest %d layer(s): %s",
            len(keep),
            [(L["id"], L["name"]) for L in keep],
        )
        return keep

    def _fetch_layer(self, layer: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Page through every Arlington feature in a single MACRIS layer.

        Filter is ``WHERE TOWN_NAME='{macris_town_name}'`` — this is what
        makes a 226,000-row statewide service tractable for a 1,300-row
        per-town extract.
        """
        layer_id = layer["id"]
        layer_name = layer["name"]
        layer_url = f"{self._service_root.rstrip('/')}/{layer_id}"

        town_field = self._detect_town_field(layer_url)
        if not town_field:
            logger.warning(
                "ArlingtonMacrisScraper | Layer '%s' has none of the configured "
                "town-filter fields %s — skipping.",
                layer_name, self._town_field_candidates,
            )
            return []
        where = f"{town_field}='{self._town_name}'"

        offset = 0
        all_features: List[Dict[str, Any]] = []
        while offset < self._max_features:
            params = {
                "f":                 "geojson",
                "where":             where,
                "outFields":         "*",
                "returnGeometry":    "true",
                "outSR":             str(self._out_sr),
                "resultOffset":      str(offset),
                "resultRecordCount": str(self._page_size),
            }
            logger.debug(
                "ArlingtonMacrisScraper | GET layer=%d offset=%d where=%r",
                layer_id, offset, where,
            )
            resp = self._session.get(
                f"{layer_url}/query", params=params,
                timeout=self._request_timeout_s,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(
                    f"ArlingtonMacrisScraper | ArcGIS error on layer "
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
            "ArlingtonMacrisScraper | Fetched %d feature(s) from "
            "layer '%s' (id=%d).",
            len(all_features), layer_name, layer_id,
        )
        return all_features

    def fetch_features(self) -> List[Dict[str, Any]]:
        """Return every MACRIS feature (point + polygon) for the configured town."""
        layers = self._enumerate_layers()
        all_features: List[Dict[str, Any]] = []
        for layer in layers:
            try:
                all_features.extend(self._fetch_layer(layer))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ArlingtonMacrisScraper | Layer '%s' failed (%s) — "
                    "continuing with remaining layers.",
                    layer["name"], exc,
                )
        logger.info(
            "ArlingtonMacrisScraper | Total MACRIS features for town "
            "%r: %d",
            self._town_name, len(all_features),
        )
        return all_features

    # ------------------------------------------------------------------
    # Bronze → Gold pipeline
    # ------------------------------------------------------------------

    def parse_bronze(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalise GeoJSON MACRIS features into Bronze dicts."""
        bronze: List[Dict[str, Any]] = []
        skipped_no_geom = 0
        for feat in features:
            props: Dict[str, Any] = feat.get("properties") or feat.get("attributes") or {}
            geom: Dict[str, Any] = feat.get("geometry") or {}

            coords = geom.get("coordinates") or []
            if not coords:
                skipped_no_geom += 1
                continue

            mhcn = self._first_non_empty(props, self._mhcn_fields)
            object_id = props.get("OBJECTID") or props.get("OBJECTID_1") or ""

            # Synthetic source_id used by the linker.  Composite of layer +
            # MHCN + objectid so re-runs do not produce duplicate PKs and
            # rows without an MHCN (rare but possible) still get a stable key.
            source_id = ":".join(
                p for p in (
                    str(feat.get("_layer_id", "")),
                    str(mhcn or "").strip(),
                    str(object_id),
                ) if p
            ) or feat.get("_layer_name", "macris")

            bronze.append({
                "source_id":            source_id,
                "mhcn":                 mhcn,
                "resource_kind":        self._first_non_empty(props, self._resource_kind_fields),
                "legend":               self._first_non_empty(props, self._legend_fields),
                "designation":          self._first_non_empty(props, self._designation_fields),
                "designation_date":     self._first_non_empty(props, self._designation_date_fields),
                "historic_name":        self._first_non_empty(props, self._historic_name_fields),
                "common_name":          self._first_non_empty(props, self._common_name_fields),
                "address":              self._first_non_empty(props, self._address_fields),
                "town_name":            self._town_name,
                "construction_date":    self._first_non_empty(props, self._construction_date_fields),
                "architectural_style":  self._first_non_empty(props, self._architectural_style_fields),
                "architect":            self._first_non_empty(props, self._architect_fields),
                "use_type":             self._first_non_empty(props, self._use_type_fields),
                "significance":         self._first_non_empty(props, self._significance_fields),
                "demolished":           self._first_non_empty(props, self._demolished_fields),
                "geometry_type":        geom.get("type", "Point"),
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

        if skipped_no_geom:
            logger.warning(
                "ArlingtonMacrisScraper | Skipped %d feature(s) without "
                "usable geometry.",
                skipped_no_geom,
            )
        logger.info(
            "ArlingtonMacrisScraper | Bronze records: %d", len(bronze)
        )
        return bronze

    def _promote_to_gold(
        self,
        bronze: Dict[str, Any],
        linker: PartyLinker,
    ) -> Dict[str, Any]:
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

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        features = self.fetch_features()
        bronze_records = self.parse_bronze(features)

        if not bronze_records:
            logger.warning(
                "ArlingtonMacrisScraper | 0 MACRIS features for town %r — "
                "writing empty parquet so downstream loaders see an "
                "explicit empty table rather than a missing file.",
                self._town_name,
            )

        effective_linker = self._linker or get_linker()
        gold_records = [
            self._promote_to_gold(b, effective_linker) for b in bronze_records
        ]

        df = pd.DataFrame(gold_records)
        if not df.empty:
            df["geometry_coordinates"] = df["geometry_coordinates"].apply(_json.dumps)
            df["metadata"] = df["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df, self._town_slug, "macris", output_dir=output_dir)
        logger.info(
            "ArlingtonMacrisScraper | Wrote %d MACRIS row(s) -> %s",
            len(gold_records), out_path,
        )
        return out_path
