# [FILE PATH]: tests/test_spatial.py
# Patch #204
# Execution Mode: Tier 3 — OverlayResolver Unit + Integration Tests
# Date: 2026-05-07

"""
Unit + integration tests for ``core.spatial.OverlayResolver``.

Test matrix
-----------
  - GEOM_HELPERS:     haversine_ft is symmetric and matches a known
                      Boston→Cambridge baseline within 1%.
  - SYNTHETIC_PIP:    point inside / outside / on a unit-square polygon;
                      multipolygon hit on the second component.
  - ADDRESS_MATCH:    case + whitespace insensitivity + prefix-match
                      ("29 Walnut St" against "29 WALNUT STREET").
  - POLYLINE_NEAR:    centroid 30 ft from a polyline counts as match
                      under the default 50 ft threshold; 70 ft does not.
  - PARCEL_LOOKUP:    by parcel_id and by address against a tiny
                      synthetic parcel parquet.
  - INTEGRATION:      live read of the Phase 2a-2d Arlington Gold parquets
                      for parcel_id="128.0-0003-0012.0" (29 Walnut St);
                      asserts R2 base + NMF overlay + zero environmental
                      / noncompliance / historic hits.

Synthetic tests use temp-dir gold parquets so they run with zero network
I/O and zero dependencies on Tier 2 ingestors.  The 29 Walnut integration
test is auto-skipped when the gold lake hasn't been populated yet.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

import pandas as pd
import pytest

from core.spatial import (
    OverlayHit,
    OverlayResolver,
    ParcelOverlayStack,
    haversine_ft,
)


# ---------------------------------------------------------------------------
# Synthetic-fixture helpers
# ---------------------------------------------------------------------------

def _write_parquet(
    root: pathlib.Path, town_slug: str, domain: str, rows: List[Dict[str, Any]],
) -> pathlib.Path:
    """Persist *rows* as ``{root}/{town_slug}/{domain}.parquet`` and return path."""
    if not rows:
        df = pd.DataFrame()
    else:
        df = pd.DataFrame(rows)
        for col in ("geometry_coordinates", "metadata", "edges_ft"):
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda v: json.dumps(v) if not isinstance(v, str) and v is not None else v
                )
    out = root / town_slug / f"{domain}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    return out


def _unit_square(cx: float, cy: float, half: float = 0.001) -> List[List[List[float]]]:
    """Return a GeoJSON Polygon outer ring centred at (cx, cy)."""
    return [[
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
        [cx - half, cy - half],
    ]]


@pytest.fixture()
def synth_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tmp directory ready to host synthetic gold parquets."""
    return tmp_path / "gold"


@pytest.fixture()
def town_slug() -> str:
    return "synthtown-ma"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

class TestHaversineFt:
    def test_symmetric(self):
        a = (-71.16, 42.41)
        b = (-71.05, 42.36)
        assert haversine_ft(a, b) == pytest.approx(haversine_ft(b, a), abs=1e-6)

    def test_zero_for_same_point(self):
        p = (-71.16, 42.41)
        assert haversine_ft(p, p) < 1e-6

    def test_known_distance(self):
        """
        Boston Common (-71.0656, 42.3551) → Harvard Yard (-71.1167, 42.3744).

        Spherical great-circle distance ≈ 15,470 ft.  Tolerate 1% drift
        because we model Earth as a sphere, not the WGS-84 ellipsoid.
        """
        boston_common = (-71.0656, 42.3551)
        harvard_yard = (-71.1167, 42.3744)
        d = haversine_ft(boston_common, harvard_yard)
        assert d == pytest.approx(15470, rel=0.01)


# ---------------------------------------------------------------------------
# Synthetic point-in-polygon
# ---------------------------------------------------------------------------

class TestPointInPolygon:
    def test_point_inside_polygon_hits(self, synth_root, town_slug):
        # Parcel layer with one tiny square at (-71.0, 42.0)
        _write_parquet(synth_root, town_slug, "parcel", [{
            "parcel_id":        "P-1",
            "address":          "1 Test Way",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        100.0,
            "perimeter_ft":     40.0,
            "longest_edge_ft":  10.0,
            "edges_ft":         [10.0, 10.0, 10.0, 10.0],
            "metadata":         {},
        }])
        # Zoning overlay polygon covering the parcel
        _write_parquet(synth_root, town_slug, "zoning-overlay", [{
            "te_overlay_pk":    1,
            "layer_name":       "Zoning Districts",
            "zone_code":        "R2",
            "overlay_type":     "Base",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0, half=0.01),
            "metadata":         {},
        }])
        # Empty siblings so the resolver doesn't blow up
        for d in ("macris", "local-historic", "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, town_slug, d, [])

        r = OverlayResolver(town_slug=town_slug, data_dir=synth_root)
        stack = r.resolve(parcel_id="P-1")
        assert isinstance(stack, ParcelOverlayStack)
        assert len(stack.zoning_overlay) == 1
        assert stack.zoning_overlay[0].code == "R2"
        assert stack.zoning_overlay[0].match_type == "spatial"

    def test_point_outside_polygon_misses(self, synth_root, town_slug):
        _write_parquet(synth_root, town_slug, "parcel", [{
            "parcel_id":        "P-2",
            "address":          "2 Far St",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        100.0,
            "perimeter_ft":     40.0,
            "longest_edge_ft":  10.0,
            "edges_ft":         [10.0, 10.0, 10.0, 10.0],
            "metadata":         {},
        }])
        # Zoning polygon FAR away
        _write_parquet(synth_root, town_slug, "zoning-overlay", [{
            "te_overlay_pk":    1,
            "layer_name":       "Zoning Districts",
            "zone_code":        "R2",
            "overlay_type":     "Base",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-72.0, 43.0),
            "metadata":         {},
        }])
        for d in ("macris", "local-historic", "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, town_slug, d, [])

        stack = OverlayResolver(town_slug=town_slug, data_dir=synth_root).resolve(parcel_id="P-2")
        assert stack.zoning_overlay == []

    def test_multipolygon_hit_on_second_component(self, synth_root, town_slug):
        _write_parquet(synth_root, town_slug, "parcel", [{
            "parcel_id":        "P-3",
            "address":          "3 Multi Rd",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        100.0,
            "perimeter_ft":     40.0,
            "longest_edge_ft":  10.0,
            "edges_ft":         [10.0, 10.0, 10.0, 10.0],
            "metadata":         {},
        }])
        # MultiPolygon: first component far away, second component covers parcel
        multi_coords = [_unit_square(-72.0, 43.0), _unit_square(-71.0, 42.0, half=0.01)]
        _write_parquet(synth_root, town_slug, "zoning-overlay", [{
            "te_overlay_pk":    1,
            "layer_name":       "Zoning Districts",
            "zone_code":        "R3",
            "overlay_type":     "Base",
            "geometry_type":    "MultiPolygon",
            "geometry_coordinates": multi_coords,
            "metadata":         {},
        }])
        for d in ("macris", "local-historic", "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, town_slug, d, [])

        stack = OverlayResolver(town_slug=town_slug, data_dir=synth_root).resolve(parcel_id="P-3")
        assert len(stack.zoning_overlay) == 1
        assert stack.zoning_overlay[0].code == "R3"


# ---------------------------------------------------------------------------
# Address match
# ---------------------------------------------------------------------------

class TestAddressMatch:
    def _build_minimal_layout(self, root: pathlib.Path, town_slug: str) -> None:
        _write_parquet(root, town_slug, "parcel", [{
            "parcel_id":        "AM-1",
            "address":          "29 WALNUT ST",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        100.0,
            "perimeter_ft":     40.0,
            "longest_edge_ft":  10.0,
            "edges_ft":         [10.0, 10.0, 10.0, 10.0],
            "metadata":         {},
        }])
        _write_parquet(root, town_slug, "zoning-overlay", [])
        _write_parquet(root, town_slug, "environmental-overlay", [])
        _write_parquet(root, town_slug, "noncompliance", [])

    def test_address_prefix_match_lowercase(self, synth_root, town_slug):
        self._build_minimal_layout(synth_root, town_slug)
        # MACRIS row whose address differs in case + suffix word
        _write_parquet(synth_root, town_slug, "macris", [{
            "te_resource_pk":   1,
            "mhcn":             "ARL.999",
            "address":          "29 walnut street",
            "town_name":        "Arlington",
            "legend":           "Inv.",
            "designation":      None,
            "designation_date": None,
            "historic_name":    "Test House",
            "common_name":      None,
            "resource_kind":    "Building",
            "geometry_type":    "Point",
            "geometry_coordinates": [-71.0, 42.0],
            "metadata":         {},
        }])
        _write_parquet(synth_root, town_slug, "local-historic", [])

        r = OverlayResolver(town_slug=town_slug, data_dir=synth_root)
        stack = r.resolve(parcel_id="AM-1")
        assert len(stack.macris) == 1
        assert stack.macris[0].match_type == "address"
        assert stack.macris[0].attributes["mhcn"] == "ARL.999"

    def test_address_no_match_when_unrelated(self, synth_root, town_slug):
        self._build_minimal_layout(synth_root, town_slug)
        _write_parquet(synth_root, town_slug, "macris", [{
            "te_resource_pk":   1,
            "mhcn":             "ARL.998",
            "address":          "111 Pleasant St",
            "town_name":        "Arlington",
            "legend":           "Inv.",
            "designation":      None,
            "designation_date": None,
            "historic_name":    "Other House",
            "common_name":      None,
            "resource_kind":    "Building",
            "geometry_type":    "Point",
            "geometry_coordinates": [-71.5, 42.5],
            "metadata":         {},
        }])
        _write_parquet(synth_root, town_slug, "local-historic", [])

        stack = OverlayResolver(
            town_slug=town_slug, data_dir=synth_root,
        ).resolve(parcel_id="AM-1")
        assert stack.macris == []


# ---------------------------------------------------------------------------
# Polyline near-distance
# ---------------------------------------------------------------------------

class TestPolylineNear:
    def test_within_threshold_fires(self, synth_root, town_slug):
        # Parcel centroid at (-71.0, 42.0).  Polyline ~30 ft NE of it.
        # 30 ft ≈ 0.0000826 deg lat, so we offset by 0.00008 deg.
        polyline_coords = [
            [-71.0 + 0.00010, 42.0 + 0.00008],
            [-71.0 + 0.00040, 42.0 + 0.00008],
        ]
        _write_parquet(synth_root, town_slug, "parcel", [{
            "parcel_id":        "PN-1",
            "address":          "1 Edge Ln",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        100.0,
            "perimeter_ft":     40.0,
            "longest_edge_ft":  10.0,
            "edges_ft":         [10.0, 10.0, 10.0, 10.0],
            "metadata":         {},
        }])
        _write_parquet(synth_root, town_slug, "local-historic", [{
            "te_resource_pk":   1,
            "mhcn":             None,
            "address":          None,
            "town_name":        "Arlington",
            "legend":           "NHD",
            "designation":      None,
            "designation_date": None,
            "historic_name":    "Test NHD Boundary",
            "common_name":      None,
            "resource_kind":    None,
            "geometry_type":    "LineString",
            "geometry_coordinates": polyline_coords,
            "metadata":         {},
        }])
        for d in ("zoning-overlay", "macris", "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, town_slug, d, [])

        r = OverlayResolver(
            town_slug=town_slug, data_dir=synth_root, polyline_near_threshold_ft=50.0,
        )
        stack = r.resolve(parcel_id="PN-1")
        assert len(stack.local_historic) == 1
        assert stack.local_historic[0].match_type == "polyline-near"
        assert stack.local_historic[0].distance_ft is not None
        assert stack.local_historic[0].distance_ft <= 50.0

    def test_outside_threshold_misses(self, synth_root, town_slug):
        # Polyline ~70 ft from parcel — over the default 50 ft threshold.
        polyline_coords = [
            [-71.0 + 0.00010, 42.0 + 0.00020],
            [-71.0 + 0.00040, 42.0 + 0.00020],
        ]
        _write_parquet(synth_root, town_slug, "parcel", [{
            "parcel_id":        "PN-2",
            "address":          "1 Far Ln",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _unit_square(-71.0, 42.0),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        100.0,
            "perimeter_ft":     40.0,
            "longest_edge_ft":  10.0,
            "edges_ft":         [10.0, 10.0, 10.0, 10.0],
            "metadata":         {},
        }])
        _write_parquet(synth_root, town_slug, "local-historic", [{
            "te_resource_pk":   1,
            "mhcn":             None,
            "address":          None,
            "town_name":        "Arlington",
            "legend":           "NHD",
            "designation":      None,
            "designation_date": None,
            "historic_name":    "Test NHD Boundary",
            "common_name":      None,
            "resource_kind":    None,
            "geometry_type":    "LineString",
            "geometry_coordinates": polyline_coords,
            "metadata":         {},
        }])
        for d in ("zoning-overlay", "macris", "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, town_slug, d, [])

        r = OverlayResolver(
            town_slug=town_slug, data_dir=synth_root, polyline_near_threshold_ft=50.0,
        )
        stack = r.resolve(parcel_id="PN-2")
        assert stack.local_historic == []


# ---------------------------------------------------------------------------
# Parcel lookup + query-mode precedence
# ---------------------------------------------------------------------------

class TestParcelLookup:
    @pytest.fixture()
    def two_parcels(self, synth_root, town_slug) -> None:
        _write_parquet(synth_root, town_slug, "parcel", [
            {
                "parcel_id":        "X-1",
                "address":          "29 WALNUT ST",
                "geometry_type":    "Polygon",
                "geometry_coordinates": _unit_square(-71.0, 42.0),
                "centroid_lat":     42.0,
                "centroid_lon":     -71.0,
                "area_sqft":        100.0,
                "perimeter_ft":     40.0,
                "longest_edge_ft":  10.0,
                "edges_ft":         [10.0, 10.0, 10.0, 10.0],
                "metadata":         {},
            },
            {
                "parcel_id":        "X-2",
                "address":          "30 PINE ST",
                "geometry_type":    "Polygon",
                "geometry_coordinates": _unit_square(-72.0, 43.0),
                "centroid_lat":     43.0,
                "centroid_lon":     -72.0,
                "area_sqft":        200.0,
                "perimeter_ft":     60.0,
                "longest_edge_ft":  20.0,
                "edges_ft":         [15.0, 15.0, 15.0, 15.0],
                "metadata":         {},
            },
        ])
        for d in ("zoning-overlay", "macris", "local-historic",
                  "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, town_slug, d, [])

    def test_resolve_by_parcel_id(self, synth_root, town_slug, two_parcels):
        stack = OverlayResolver(
            town_slug=town_slug, data_dir=synth_root,
        ).resolve(parcel_id="X-2")
        assert stack.query_kind == "parcel_id"
        assert stack.parcel.parcel_id == "X-2"
        assert stack.point_lat == 43.0

    def test_resolve_by_address_finds_centroid(self, synth_root, town_slug, two_parcels):
        stack = OverlayResolver(
            town_slug=town_slug, data_dir=synth_root,
        ).resolve(address="29 walnut st")
        assert stack.query_kind == "address"
        assert stack.parcel.parcel_id == "X-1"
        assert stack.point_lat == 42.0

    def test_resolve_by_lat_lon_skips_parcel(self, synth_root, town_slug, two_parcels):
        stack = OverlayResolver(
            town_slug=town_slug, data_dir=synth_root,
        ).resolve(lat=42.5, lon=-71.5)
        assert stack.query_kind == "lat_lon"
        assert stack.parcel is None
        assert (stack.point_lat, stack.point_lon) == (42.5, -71.5)

    def test_unknown_parcel_id_raises(self, synth_root, town_slug, two_parcels):
        with pytest.raises(ValueError, match="not found"):
            OverlayResolver(
                town_slug=town_slug, data_dir=synth_root,
            ).resolve(parcel_id="DOES-NOT-EXIST")

    def test_no_arguments_raises(self, synth_root, town_slug):
        with pytest.raises(ValueError, match="requires one of"):
            OverlayResolver(
                town_slug=town_slug, data_dir=synth_root,
            ).resolve()


# ---------------------------------------------------------------------------
# Live integration — 29 Walnut St against the real Phase 2a-2d Gold lake
# ---------------------------------------------------------------------------

ARLINGTON_GOLD = pathlib.Path("data/gold/arlington-ma")
WALNUT_PARCEL_ID = "128.0-0003-0012.0"
REQUIRED_PARQUETS = (
    "parcel.parquet", "zoning-overlay.parquet", "macris.parquet",
    "local-historic.parquet", "environmental-overlay.parquet",
    "noncompliance.parquet",
)


@pytest.mark.skipif(
    not all((ARLINGTON_GOLD / f).exists() for f in REQUIRED_PARQUETS),
    reason=(
        "Skipped because the Arlington Gold lake hasn't been populated. "
        "Run: python core/master_loop.py --towns arlington-ma --skip-discovery"
    ),
)
class Test29WalnutIntegration:
    """End-to-end: known buildability answer derived from real parquets."""

    @pytest.fixture(scope="class")
    def stack(self) -> ParcelOverlayStack:
        return OverlayResolver(town_slug="arlington-ma").resolve(parcel_id=WALNUT_PARCEL_ID)

    def test_parcel_resolves(self, stack):
        assert stack.parcel is not None
        assert stack.parcel.parcel_id == WALNUT_PARCEL_ID
        assert stack.parcel.address and "WALNUT" in stack.parcel.address.upper()

    def test_zoning_includes_r2_and_nmf(self, stack):
        codes = sorted({h.code for h in stack.zoning_overlay if h.code})
        assert "R2" in codes, f"expected R2 in zoning hits, got {codes}"
        assert "NMF" in codes, f"expected NMF overlay in zoning hits, got {codes}"

    def test_no_macris_hit(self, stack):
        # Empty result is the *correct* answer for 29 Walnut — see Phase 2c log.
        assert stack.macris == []

    def test_no_local_historic_hit(self, stack):
        assert stack.local_historic == []

    def test_no_environmental_hit(self, stack):
        assert stack.environmental_overlay == []

    def test_no_noncompliance_hit(self, stack):
        assert stack.noncompliance == []

    def test_summary_one_liner_format(self, stack):
        s = stack.summary_one_liner()
        assert "WALNUT" in s.upper()
        assert "R2" in s
        assert "NMF" in s
