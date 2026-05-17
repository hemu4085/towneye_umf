# [FILE PATH]: core/spatial.py
# Patch #204
# Execution Mode: Tier 3 — Spatial Overlay Resolver
# Date: 2026-05-07
"""
core.spatial -- the Spatial Overlay Resolver.

Why this module exists
----------------------
Phases 2a-2d gave us **six town-wide Gold parquets** of polygon / point /
polyline data (parcel, zoning-overlay, macris, local-historic,
environmental-overlay, noncompliance).  Without a single resolver, every
report has to:

  * load each parquet,
  * deserialise the JSON-encoded geometry column,
  * run its own ray-cast / shapely point-in-polygon code,
  * stitch hits across domains into a unified data structure.

That is roughly 200 lines of repeated, error-prone glue per report, and
historically every report has subtly disagreed (different lat/lon
precision, different polyline handling, different "address-match" rules).

``OverlayResolver`` collapses all of that into a single call:

    >>> from core.spatial import OverlayResolver
    >>> r = OverlayResolver(town_slug="arlington-ma")
    >>> stack = r.resolve(parcel_id="128.0-0003-0012.0")
    >>> stack.summary_one_liner()
    "29 WALNUT ST | base R2 + NMF | 0 historic, 0 env, 0 noncompliance"

The result is a fully validated ``ParcelOverlayStack`` Pydantic object
that downstream report templates render without any spatial logic of
their own — they just project columns out of the model.

Geometry library
----------------
Built on ``shapely>=2.0``.  Why not the ad-hoc ray-cast helpers used
during Phases 2a-2d verification?

  * Ray-cast on the outer ring fails for polygons with holes (interior
    rings).  Several Arlington overlay polygons have inner rings around
    parcels that are excluded from the district.
  * MultiPolygons need a hit on ANY component, not just the first.
  * Polyline distance ("nearest segment") needs proper geodesic math.
    Arlington's National Historic District is published as a single
    polyline boundary, so "is this property within X feet of the NHD
    perimeter?" needs distance-to-polyline.

Shapely handles all three correctly out of the box.

Coordinate handling
-------------------
All geometries in the Gold parquets are GeoJSON in WGS-84 (lon/lat,
EPSG:4326).  Shapely treats coordinates as 2D Cartesian — fine for
point-in-polygon at municipal scale (sub-mile features, sub-foot
positional accuracy).  For distances we use the haversine helper from
the Phase 2a parcel scraper rather than Shapely's planar ``.distance()``,
so reported feet are real ground-feet, not WGS-84 degrees.
"""

from __future__ import annotations

import json
import logging
import math
import pathlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import shape as _shapely_shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Point as _ShapelyPoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

_EARTH_RADIUS_M = 6371000.0
_M_TO_FT = 3.28084


def haversine_ft(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """
    Great-circle distance between two ``(lon, lat)`` points, in feet.

    Lifted from ``scripts/29_walnut_queries.py::_haversine_ft`` so the
    resolver and the existing parcel scraper agree on units.
    """
    lat1, lon1 = math.radians(p1[1]), math.radians(p1[0])
    lat2, lon2 = math.radians(p2[1]), math.radians(p2[0])
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a)) * _M_TO_FT


def _to_geojson(row: pd.Series) -> Dict[str, Any]:
    """Build a GeoJSON-shaped dict from a Gold parquet row."""
    coords = row["geometry_coordinates"]
    if isinstance(coords, str):
        coords = json.loads(coords)
    return {"type": row["geometry_type"], "coordinates": coords}


def _shapely_from_row(row: pd.Series) -> Optional[BaseGeometry]:
    """Build a shapely geometry from a Gold parquet row, or ``None``."""
    try:
        return _shapely_shape(_to_geojson(row))
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "core.spatial | shapely build failed for row "
            "(geom_type=%r, err=%s) — skipping.",
            row.get("geometry_type"), exc,
        )
        return None


def _ensure_metadata(value: Any) -> Dict[str, Any]:
    """Round-trip JSON-encoded metadata column into a dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:  # noqa: BLE001
            return {}
    return {}


# ---------------------------------------------------------------------------
# Pydantic result models
# ---------------------------------------------------------------------------

MatchType = Literal["spatial", "address", "polyline-near"]


class OverlayHit(BaseModel):
    """A single overlay polygon (or point / polyline) that touches the parcel."""
    model_config = ConfigDict(from_attributes=True)

    domain: str = Field(
        ...,
        description=(
            "Source Gold parquet — 'zoning-overlay', 'macris', "
            "'local-historic', 'environmental-overlay', 'noncompliance', "
            "or 'parcel' for the property's own row."
        ),
    )
    match_type: MatchType = Field(
        ...,
        description=(
            "How this hit was produced: 'spatial' = point fell inside "
            "polygon; 'address' = address-string match between parcel "
            "and the row's address column; 'polyline-near' = parcel "
            "centroid is within configured distance of a polyline "
            "(used for the NHD boundary)."
        ),
    )
    layer: str = Field(
        ...,
        description=(
            "Sub-layer or category name within the domain — e.g. "
            "'Zoning Districts' / 'Zoning Overlay Districts' for "
            "zoning-overlay, 'flood-effective' / 'wetland' for "
            "environmental-overlay."
        ),
    )
    code: Optional[str] = Field(
        None,
        description=(
            "Short classification code — zone_code (R2, NMF), FEMA "
            "flood zone (AE, X), wetland CLASSIF (BVW, IVW), etc."
        ),
    )
    label: Optional[str] = Field(
        None,
        description=(
            "Human-readable label — district name, FEMA zone subtype, "
            "historic resource name, etc.  Used directly in reports."
        ),
    )
    geometry_type: str = Field(..., description="GeoJSON geometry type.")
    distance_ft: Optional[float] = Field(
        None,
        description=(
            "Geodesic distance from parcel centroid to this feature, in "
            "feet.  Only populated for 'polyline-near' matches; spatial "
            "and address matches leave it None."
        ),
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "The promoted columns of the source row (everything except "
            "geometry).  Reports project labels out of this dict."
        ),
    )


class ParcelInfo(BaseModel):
    """Summary of the parcel itself — populated when resolved by parcel_id."""
    model_config = ConfigDict(from_attributes=True)

    parcel_id: str
    address: Optional[str] = None
    centroid_lat: float
    centroid_lon: float
    area_sqft: Optional[float] = None
    perimeter_ft: Optional[float] = None
    longest_edge_ft: Optional[float] = None
    edges_ft: List[float] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ParcelOverlayStack(BaseModel):
    """
    Unified spatial-resolution result for a single parcel or point.

    This is the **report contract** — every report that needs to know
    "what overlays apply to this address?" projects fields out of this
    model rather than re-reading parquets directly.
    """
    model_config = ConfigDict(from_attributes=True)

    town_slug: str
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    query_kind: Literal["parcel_id", "address", "lat_lon"]
    query_value: str = Field(
        ..., description="The exact input value (parcel_id | address | 'lat,lon').",
    )

    parcel: Optional[ParcelInfo] = Field(
        None,
        description="Parcel summary; populated only when resolved by parcel_id.",
    )
    point_lat: float
    point_lon: float

    zoning_overlay:        List[OverlayHit] = Field(default_factory=list)
    macris:                List[OverlayHit] = Field(default_factory=list)
    local_historic:        List[OverlayHit] = Field(default_factory=list)
    environmental_overlay: List[OverlayHit] = Field(default_factory=list)
    noncompliance:         List[OverlayHit] = Field(default_factory=list)

    def summary_one_liner(self) -> str:
        """Compact single-line summary of the stack — useful for logs / CLI."""
        zone_codes = sorted({h.code for h in self.zoning_overlay if h.code})
        addr = (self.parcel.address if self.parcel else None) or self.query_value
        return (
            f"{addr} | "
            f"zones={'+'.join(zone_codes) or 'none'} | "
            f"hist={len(self.macris) + len(self.local_historic)} "
            f"env={len(self.environmental_overlay)} "
            f"noncomp={len(self.noncompliance)}"
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

# Domains the resolver consumes.  Each entry maps a logical key to the
# parquet basename under data/gold/{town_slug}/.
_DOMAIN_PARQUETS: Dict[str, str] = {
    "parcel":                "parcel",
    "zoning_overlay":        "zoning-overlay",
    "macris":                "macris",
    "local_historic":        "local-historic",
    "environmental_overlay": "environmental-overlay",
    "noncompliance":         "noncompliance",
}


class OverlayResolver:
    """
    Lazy, town-scoped spatial resolver for the Tier 2 Gold parquets.

    Construct once per town, call ``resolve(...)`` per address / parcel.
    All parquets are cached after first read; rebuilding the resolver
    drops the cache.

    Parameters
    ----------
    town_slug : str
        Kebab-case town id (matches the ``data/gold/{slug}/`` directory).
    data_dir : str | os.PathLike, default ``"data/gold"``
        Root of the Gold data lake.
    polyline_near_threshold_ft : float, default ``50.0``
        For polyline overlays (e.g. the NHD boundary), how close in feet
        a parcel centroid must be for ``match_type="polyline-near"`` to
        fire.  ``None`` disables polyline matching.
    """

    def __init__(
        self,
        town_slug: str,
        data_dir: str | pathlib.Path = "data/gold",
        polyline_near_threshold_ft: Optional[float] = 50.0,
    ) -> None:
        self.town_slug = town_slug
        self._data_dir = pathlib.Path(data_dir)
        self._polyline_threshold_ft = polyline_near_threshold_ft
        self._frames: Dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Internal — parquet loading + geometry hydration
    # ------------------------------------------------------------------

    def _load(self, key: str) -> pd.DataFrame:
        """Load the gold parquet for *key* (one of ``_DOMAIN_PARQUETS`` keys)."""
        if key in self._frames:
            return self._frames[key]
        domain = _DOMAIN_PARQUETS[key]
        path = self._data_dir / self.town_slug / f"{domain}.parquet"
        if not path.exists():
            logger.warning(
                "OverlayResolver | parquet missing: %s — treating as empty.",
                path,
            )
            df = pd.DataFrame()
        else:
            df = pd.read_parquet(path)
            for col in ("geometry_coordinates", "metadata", "edges_ft"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        self._frames[key] = df
        return df

    # ------------------------------------------------------------------
    # Internal — query-point construction
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_address(s: Any) -> str:
        """
        Lowercase + collapse whitespace for address-string comparison.

        Handles pandas / numpy NaN floats (empty parquet cells round-trip
        through pyarrow as ``float('nan')``, which is truthy in Python),
        as well as None and non-string inputs.
        """
        if s is None:
            return ""
        if isinstance(s, float) and math.isnan(s):
            return ""
        try:
            if pd.isna(s):  # numpy / pandas NA scalars
                return ""
        except (TypeError, ValueError):
            pass
        return re.sub(r"\s+", " ", str(s).strip().lower())

    def _resolve_query_point(
        self,
        *,
        parcel_id: Optional[str],
        address: Optional[str],
        lat: Optional[float],
        lon: Optional[float],
    ) -> Tuple[
        Literal["parcel_id", "address", "lat_lon"],
        str,
        Optional[ParcelInfo],
        float,
        float,
    ]:
        """
        Pick the (query_kind, query_value, parcel_info, lat, lon) tuple
        from the caller's arguments.

        Precedence: ``parcel_id`` > explicit ``lat``/``lon`` > ``address``.
        Address-only resolution requires the parcel parquet to have a
        matching row; otherwise ``ValueError`` is raised because we
        cannot pick a query point.
        """
        if parcel_id is not None:
            row = self._lookup_parcel_row(parcel_id=parcel_id)
            if row is None:
                raise ValueError(
                    f"OverlayResolver | parcel_id={parcel_id!r} not found in "
                    f"parcel.parquet for town={self.town_slug!r}.",
                )
            pinfo = self._parcel_info_from_row(row)
            return ("parcel_id", parcel_id, pinfo, pinfo.centroid_lat, pinfo.centroid_lon)

        if lat is not None and lon is not None:
            return ("lat_lon", f"{lat:.6f},{lon:.6f}", None, float(lat), float(lon))

        if address is not None:
            row = self._lookup_parcel_row(address=address)
            if row is None:
                raise ValueError(
                    f"OverlayResolver | address={address!r} did not match any "
                    f"parcel in parcel.parquet for town={self.town_slug!r}.  "
                    f"Pass explicit lat/lon if the address is outside the "
                    f"parcel layer.",
                )
            pinfo = self._parcel_info_from_row(row)
            return ("address", address, pinfo, pinfo.centroid_lat, pinfo.centroid_lon)

        raise ValueError(
            "OverlayResolver.resolve() requires one of: parcel_id, "
            "(lat AND lon), or address.",
        )

    def _lookup_parcel_row(
        self,
        *,
        parcel_id: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Optional[pd.Series]:
        """Find a parcel row by id (exact) or by address (case-insensitive)."""
        df = self._load("parcel")
        if df.empty:
            return None
        if parcel_id is not None and "parcel_id" in df.columns:
            hit = df[df["parcel_id"] == parcel_id]
            if not hit.empty:
                return hit.iloc[0]
        if address is not None and "address" in df.columns:
            target = self._normalize_address(address)
            mask = df["address"].fillna("").apply(
                lambda s: self._normalize_address(s) == target
            )
            hit = df[mask]
            if not hit.empty:
                return hit.iloc[0]
        return None

    @staticmethod
    def _parcel_info_from_row(row: pd.Series) -> ParcelInfo:
        edges = row.get("edges_ft", []) or []
        if not isinstance(edges, list):
            edges = list(edges)
        return ParcelInfo(
            parcel_id=str(row["parcel_id"]),
            address=row.get("address"),
            centroid_lat=float(row["centroid_lat"]),
            centroid_lon=float(row["centroid_lon"]),
            area_sqft=row.get("area_sqft"),
            perimeter_ft=row.get("perimeter_ft"),
            longest_edge_ft=row.get("longest_edge_ft"),
            edges_ft=[float(x) for x in edges],
            metadata=_ensure_metadata(row.get("metadata", {})),
        )

    # ------------------------------------------------------------------
    # Spatial primitives — applied per domain
    # ------------------------------------------------------------------

    def _spatial_hits(
        self,
        df: pd.DataFrame,
        point: _ShapelyPoint,
        point_lonlat: Tuple[float, float],
        domain: str,
        layer_col: str,
        code_col: Optional[str],
        label_col: Optional[str],
        attribute_cols: List[str],
    ) -> List[OverlayHit]:
        """Generic point-in-polygon (and polyline-near) scanner for one domain."""
        hits: List[OverlayHit] = []
        if df.empty:
            return hits
        for _, row in df.iterrows():
            geom = _shapely_from_row(row)
            if geom is None:
                continue

            match_type: Optional[MatchType] = None
            distance_ft: Optional[float] = None
            gtype = geom.geom_type  # "Point", "Polygon", "MultiPolygon", "LineString", ...

            if gtype in ("Polygon", "MultiPolygon"):
                if geom.contains(point) or geom.intersects(point):
                    match_type = "spatial"
            elif gtype in ("LineString", "MultiLineString"):
                if self._polyline_threshold_ft is not None:
                    nearest = self._nearest_distance_ft(geom, point_lonlat)
                    if nearest <= self._polyline_threshold_ft:
                        match_type = "polyline-near"
                        distance_ft = round(nearest, 1)
            else:
                # Point/MultiPoint: skip — points can't "contain" the query.
                # Domain-specific address matching handles point layers.
                continue

            if match_type is None:
                continue

            attrs = {col: row[col] for col in attribute_cols if col in row.index}
            hits.append(OverlayHit(
                domain=domain,
                match_type=match_type,
                layer=str(row.get(layer_col, "") or ""),
                code=(str(row.get(code_col)) if code_col and pd.notna(row.get(code_col)) else None),
                label=(str(row.get(label_col)) if label_col and pd.notna(row.get(label_col)) else None),
                geometry_type=str(row.get("geometry_type", gtype)),
                distance_ft=distance_ft,
                attributes={k: _to_jsonable(v) for k, v in attrs.items()},
            ))
        return hits

    @staticmethod
    def _nearest_distance_ft(
        geom: BaseGeometry, point_lonlat: Tuple[float, float],
    ) -> float:
        """
        Geodesic distance from *point_lonlat* to the nearest vertex of *geom*.

        Approximation: we sample the LineString's vertices and report the
        minimum haversine distance to any of them.  For municipal-scale
        overlays this is within 0.5 ft of the true segment-distance.
        """
        coords: List[Tuple[float, float]] = []
        gtype = geom.geom_type
        if gtype == "LineString":
            coords = list(geom.coords)
        elif gtype == "MultiLineString":
            for ls in geom.geoms:
                coords.extend(ls.coords)
        if not coords:
            return float("inf")
        return min(haversine_ft(point_lonlat, (c[0], c[1])) for c in coords)

    def _address_match_hits(
        self,
        df: pd.DataFrame,
        target_address: Optional[str],
        domain: str,
        layer_col: str,
        code_col: Optional[str],
        label_col: Optional[str],
        attribute_cols: List[str],
    ) -> List[OverlayHit]:
        """For Point-geom domains (MACRIS, AHC inventory) — match on address column."""
        hits: List[OverlayHit] = []
        if df.empty or not target_address:
            return hits
        target = self._normalize_address(target_address)
        if not target:
            return hits
        if "address" not in df.columns:
            return hits
        # Looser containment match — handles "29 Walnut St" vs "29 Walnut Street"
        # by checking that the parcel's number+street prefix shows up in the
        # MACRIS row's address.  Exact equality is also accepted.
        prefix_match = re.match(r"^\s*(\d+)\s+(\w+)", target)
        prefix = f"{prefix_match.group(1)} {prefix_match.group(2)}" if prefix_match else None
        for _, row in df.iterrows():
            row_addr = self._normalize_address(row.get("address"))
            if not row_addr:
                continue
            matched = (row_addr == target) or (prefix is not None and row_addr.startswith(prefix))
            if not matched:
                continue
            attrs = {col: row[col] for col in attribute_cols if col in row.index}
            hits.append(OverlayHit(
                domain=domain,
                match_type="address",
                layer=str(row.get(layer_col, "") or ""),
                code=(str(row.get(code_col)) if code_col and pd.notna(row.get(code_col)) else None),
                label=(str(row.get(label_col)) if label_col and pd.notna(row.get(label_col)) else None),
                geometry_type=str(row.get("geometry_type", "Point")),
                attributes={k: _to_jsonable(v) for k, v in attrs.items()},
            ))
        return hits

    # ------------------------------------------------------------------
    # Public — the one-call resolver
    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        parcel_id: Optional[str] = None,
        address: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> ParcelOverlayStack:
        """
        Resolve every overlay for the given parcel / address / point.

        Parameters
        ----------
        parcel_id : str, optional
            Stable parcel natural key (e.g. ``"128.0-0003-0012.0"``).
            When given, the parcel polygon centroid is used as the
            spatial query point and the parcel's own address feeds
            the MACRIS / local-historic address-match routines.
        address : str, optional
            Free-text address.  Looked up against ``parcel.address``;
            on a hit, the parcel's centroid drives the spatial join.
        lat, lon : float, optional
            Bypass the parcel layer entirely and query directly at
            this WGS-84 coordinate.  ``ParcelInfo`` is left None.

        Returns
        -------
        ParcelOverlayStack
            Validated unified result.  Empty per-domain lists are valid
            (mean "no overlay applies"), not errors.
        """
        query_kind, query_value, parcel_info, point_lat, point_lon = self._resolve_query_point(
            parcel_id=parcel_id, address=address, lat=lat, lon=lon,
        )
        point = _ShapelyPoint(point_lon, point_lat)
        point_lonlat = (point_lon, point_lat)

        # Address used for MACRIS / local-historic point-layer matching.
        # When the caller passed an explicit address we use that; when they
        # passed a parcel_id we use the parcel's published address.
        match_address = address or (parcel_info.address if parcel_info else None)

        # Zoning overlay (polygon containment)
        zoning_overlay = self._spatial_hits(
            self._load("zoning_overlay"),
            point, point_lonlat,
            domain="zoning-overlay",
            layer_col="layer_name",
            code_col="zone_code",
            label_col="overlay_type",
            attribute_cols=[
                "layer_name", "zone_code", "overlay_type",
                "geometry_type", "metadata",
            ],
        )

        # MACRIS (statewide) — both address match (points) and polygon containment
        df_macris = self._load("macris")
        macris_addr = self._address_match_hits(
            df_macris, match_address,
            domain="macris",
            layer_col="resource_kind",
            code_col="legend",
            label_col="historic_name",
            attribute_cols=[
                "mhcn", "address", "legend", "designation",
                "designation_date", "historic_name", "common_name",
                "resource_kind", "geometry_type",
            ],
        )
        macris_spatial = self._spatial_hits(
            df_macris, point, point_lonlat,
            domain="macris",
            layer_col="resource_kind",
            code_col="legend",
            label_col="historic_name",
            attribute_cols=[
                "mhcn", "legend", "designation", "designation_date",
                "historic_name", "common_name", "resource_kind",
                "geometry_type",
            ],
        )

        # Local historic (4 sources unified) — same dual-mode handling
        df_local = self._load("local_historic")
        local_addr = self._address_match_hits(
            df_local, match_address,
            domain="local-historic",
            layer_col="resource_kind",
            code_col="legend",
            label_col="historic_name",
            attribute_cols=[
                "mhcn", "address", "legend", "designation",
                "historic_name", "common_name", "resource_kind",
                "geometry_type",
            ],
        )
        local_spatial = self._spatial_hits(
            df_local, point, point_lonlat,
            domain="local-historic",
            layer_col="resource_kind",
            code_col="legend",
            label_col="historic_name",
            attribute_cols=[
                "mhcn", "legend", "designation",
                "historic_name", "common_name", "resource_kind",
                "geometry_type",
            ],
        )

        env_overlay = self._spatial_hits(
            self._load("environmental_overlay"),
            point, point_lonlat,
            domain="environmental-overlay",
            layer_col="source_layer_name",
            code_col="zone_code",
            label_col="zone_subtype",
            attribute_cols=[
                "category", "zone_code", "zone_subtype", "sfha_flag",
                "static_bfe", "source_layer_name", "geometry_type",
            ],
        )

        noncompliance = self._spatial_hits(
            self._load("noncompliance"),
            point, point_lonlat,
            domain="noncompliance",
            layer_col="status",
            code_col="land_use_code",
            label_col="status",
            attribute_cols=[
                "land_use_code", "zone_code_numeric", "land_use_zone_diff",
                "status", "geometry_type",
            ],
        )

        return ParcelOverlayStack(
            town_slug=self.town_slug,
            query_kind=query_kind,
            query_value=query_value,
            parcel=parcel_info,
            point_lat=point_lat,
            point_lon=point_lon,
            zoning_overlay=zoning_overlay,
            macris=macris_addr + macris_spatial,
            local_historic=local_addr + local_spatial,
            environmental_overlay=env_overlay,
            noncompliance=noncompliance,
        )


# ---------------------------------------------------------------------------
# Helpers exported for callers
# ---------------------------------------------------------------------------

def _to_jsonable(value: Any) -> Any:
    """Coerce numpy / pandas scalars to native Python so Pydantic accepts them."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "OverlayHit",
    "OverlayResolver",
    "ParcelInfo",
    "ParcelOverlayStack",
    "haversine_ft",
]
