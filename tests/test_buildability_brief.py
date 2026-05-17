# [FILE PATH]: tests/test_buildability_brief.py
# Patch #205
# Execution Mode: Tier 4 — BuildabilityBriefGenerator Unit + Integration Tests
# Date: 2026-05-07

"""
Unit + integration tests for ``reports.buildability_brief``.

Test matrix
-----------
  - INPUT_VALIDATION  : Pydantic refuses an invalid date / missing parcel.
  - DATA_COLLECTION   : collect_data() builds a BriefData from a synthetic
                        Gold lake (parcel + zoning + zoning-overlay +
                        empty wraparound parquets).  Envelope math is
                        verified against hand-computed values.
  - VERDICT_LOGIC     : verdict class flips green/yellow/red based on the
                        wraparound flags and overlay availability.
  - HTML_RENDER       : render_html() emits the expected section headers,
                        zone codes, and lot-size figures for the synthetic
                        parcel.
  - INTEGRATION       : live read of the Phase 2a-2d Arlington Gold lake
                        for parcel_id="128.0-0003-0012.0" (29 Walnut St);
                        asserts R2+NMF in the brief, the four wraparound
                        rows all read "No overlap.", and the rendered HTML
                        carries the parcel address, parcel id, and the
                        Tier 3 OverlayResolver-driven copy.

Synthetic tests run with zero network I/O and zero dependency on the
Tier 2 ingestors; the integration class auto-skips when the gold lake
hasn't been populated yet.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date
from typing import Any, Dict, List

import pandas as pd
import pytest

from reports.buildability_brief import (
    BriefData,
    BriefInputs,
    BuildabilityBriefGenerator,
    BuildableEnvelope,
    PropertyInfo,
    WraparoundConstraint,
    ZoningRule,
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
        for col in ("geometry_coordinates", "metadata", "edges_ft", "allowed_uses"):
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda v: json.dumps(v) if not isinstance(v, str) and v is not None else v
                )
    out = root / town_slug / f"{domain}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    return out


def _square_polygon(cx: float, cy: float, half: float = 0.0005) -> List[List[List[float]]]:
    """A small square polygon centred at (cx, cy)."""
    return [[
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
        [cx - half, cy - half],
    ]]


@pytest.fixture()
def synth_root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "gold"


@pytest.fixture()
def synth_town() -> str:
    return "synthtown-ma"


@pytest.fixture()
def synth_lake(synth_root, synth_town):
    """Build a complete 7-domain Gold lake covering one parcel."""
    parcel_polygon = _square_polygon(-71.0, 42.0, half=0.0008)
    _write_parquet(synth_root, synth_town, "parcel", [{
        "parcel_id":        "BB-1",
        "address":          "1 Test Way",
        "geometry_type":    "Polygon",
        "geometry_coordinates": parcel_polygon,
        "centroid_lat":     42.0,
        "centroid_lon":     -71.0,
        "area_sqft":        3000.0,
        "perimeter_ft":     220.0,
        "longest_edge_ft":  56.0,
        "edges_ft":         [56.0, 55.0, 54.0, 55.0],
        "metadata":         {},
    }])
    _write_parquet(synth_root, synth_town, "zoning-overlay", [
        {
            "te_overlay_pk":    1,
            "layer_name":       "Zoning Districts",
            "zone_code":        "R2",
            "overlay_type":     "Base",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _square_polygon(-71.0, 42.0, half=0.005),
            "metadata":         {},
        },
        {
            "te_overlay_pk":    2,
            "layer_name":       "Zoning Overlay Districts",
            "zone_code":        "NMF",
            "overlay_type":     "Multi-Family",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _square_polygon(-71.0, 42.0, half=0.004),
            "metadata":         {},
        },
    ])
    _write_parquet(synth_root, synth_town, "zoning", [
        {
            "zone_code":        "R2",
            "zone_description": "Two-Family Residence District",
            "allowed_uses":     ["Single-Family Dwelling", "Two-Family Dwelling"],
            "max_height_ft":    35.0,
            "metadata":         {"min_lot_sqft": 6000, "min_frontage_ft": 50,
                                 "max_far": 0.50, "setback_front_ft": 15},
        },
    ])
    _write_parquet(synth_root, synth_town, "property", [{
        "te_property_pk":     1,
        "parcel_id":          "BB-1",
        "address":            "1 Test Way",
        "owner_name":         "TEST OWNER",
        "year_built":         1927,
        "building_type":      "Old Style",
        "luc":                "101",
        "luc_description":    "One Family",
        "beds":               3,
        "baths":              2,
        "assessed_value":     1000000.0,
        "lot_size_sqft":      3000.0,
        "metadata":           {"finished_area_sqft": 1490.0, "last_sale_price": 750000.0,
                               "last_sale_date": "2017-06-13", "book_page": "69423-104"},
    }])
    for d in ("macris", "local-historic", "environmental-overlay", "noncompliance"):
        _write_parquet(synth_root, synth_town, d, [])
    return synth_root


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_missing_parcel_id_raises(self):
        with pytest.raises(ValueError):
            BriefInputs(town_slug="x")  # parcel_id missing

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            BriefInputs(town_slug="x", parcel_id="P-1", prepared_on="not-a-date")

    def test_minimal_inputs_accepted(self):
        bi = BriefInputs(town_slug="x", parcel_id="P-1")
        assert bi.prepared_for is None
        assert bi.prepared_on is None


# ---------------------------------------------------------------------------
# Data collection + envelope math
# ---------------------------------------------------------------------------

class TestDataCollection:
    def test_collect_data_partitions_zoning_correctly(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        assert isinstance(data, BriefData)
        assert [h.code for h in data.base_zoning_hits] == ["R2"]
        assert [h.code for h in data.overlay_zoning_hits] == ["NMF"]
        assert data.has_overlay_election is True
        assert data.primary_zone_code == "R2"
        assert data.primary_overlay_code == "NMF"

    def test_zoning_rules_loaded_from_parquet(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        r2 = data.zoning_rules.get("R2")
        assert isinstance(r2, ZoningRule)
        assert r2.max_far == pytest.approx(0.50)
        assert r2.min_lot_sqft == 6000

    def test_property_info_projected(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        p = data.property_info
        assert isinstance(p, PropertyInfo)
        assert p.owner_name == "TEST OWNER"
        assert p.year_built == 1927
        assert p.assessed_value == pytest.approx(1000000.0)
        assert p.finished_area_sqft == pytest.approx(1490.0)

    def test_envelope_far_math_correct(self, synth_lake, synth_town):
        """3,000 sf × FAR 0.50 = 1,500 sf max GFA; existing 1,490 → 10 sf room."""
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        r2_env = next(e for e in data.envelopes if e.zone_code == "R2")
        assert r2_env.max_gfa_sqft == pytest.approx(1500.0)
        assert r2_env.expansion_room_sqft == pytest.approx(10.0)
        assert r2_env.pct_of_far_cap == pytest.approx(1490 / 1500)
        # 3000 sf < 6000 sf min → non-conforming
        assert r2_env.qualifies is False

    def test_envelope_overlay_without_rule_is_unbounded(self, synth_lake, synth_town):
        """NMF has no rule in zoning.parquet → overlay envelope returns 'None required'."""
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        nmf = next(e for e in data.envelopes if e.zone_code == "NMF")
        assert nmf.is_overlay is True
        assert nmf.max_far is None
        assert nmf.max_gfa_sqft is None
        assert "None required" not in (nmf.notes or "")  # rationale carries it
        assert "no machine-readable rule" in nmf.rationale

    def test_unknown_parcel_raises(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        with pytest.raises(ValueError):
            gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="DOES-NOT-EXIST"))

    def test_town_mismatch_raises(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        bad_inputs = BriefInputs(town_slug="other-ma", parcel_id="BB-1")
        with pytest.raises(ValueError, match="does not match"):
            gen.generate(bad_inputs)


# ---------------------------------------------------------------------------
# Verdict class logic
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_clean_parcel_with_overlay_yields_yellow(self, synth_lake, synth_town):
        """No wraparound flags + R2 non-conforming → v-yellow (lot doesn't qualify base)."""
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        # 3000 sf < R2's 6000 sf → qualifies=False; no env hits → flagged=0; → v-yellow
        assert data.headline_verdict_class == "v-yellow"

    def test_clean_qualifying_parcel_yields_green(self, synth_root, synth_town):
        """Lot that meets R2 6000 sf min and has no wraparound flags → v-green."""
        # Build a lake where the parcel comfortably exceeds 6000 sf.
        _write_parquet(synth_root, synth_town, "parcel", [{
            "parcel_id":        "BIG-1",
            "address":          "100 Big Lot Way",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _square_polygon(-71.0, 42.0, half=0.0008),
            "centroid_lat":     42.0,
            "centroid_lon":     -71.0,
            "area_sqft":        10000.0,
            "perimeter_ft":     400.0,
            "longest_edge_ft":  100.0,
            "edges_ft":         [100.0, 100.0, 100.0, 100.0],
            "metadata":         {},
        }])
        _write_parquet(synth_root, synth_town, "zoning-overlay", [{
            "te_overlay_pk":    1,
            "layer_name":       "Zoning Districts",
            "zone_code":        "R2",
            "overlay_type":     "Base",
            "geometry_type":    "Polygon",
            "geometry_coordinates": _square_polygon(-71.0, 42.0, half=0.005),
            "metadata":         {},
        }])
        _write_parquet(synth_root, synth_town, "zoning", [{
            "zone_code":        "R2",
            "zone_description": "Two-Family Residence District",
            "allowed_uses":     ["Single-Family Dwelling"],
            "max_height_ft":    35.0,
            "metadata":         {"min_lot_sqft": 6000, "max_far": 0.50},
        }])
        _write_parquet(synth_root, synth_town, "property", [])
        for d in ("macris", "local-historic", "environmental-overlay", "noncompliance"):
            _write_parquet(synth_root, synth_town, d, [])

        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_root)
        data = gen.collect_data(BriefInputs(town_slug=synth_town, parcel_id="BIG-1"))
        assert data.headline_verdict_class == "v-green"


# ---------------------------------------------------------------------------
# HTML render
# ---------------------------------------------------------------------------

class TestHtmlRender:
    def test_html_carries_section_headers(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        html = gen.generate(BriefInputs(town_slug=synth_town, parcel_id="BB-1",
                                        prepared_for="Tester",
                                        prepared_on=date(2026, 5, 7)))
        for header in (
            "1 · Executive Summary",
            "2 · Parcel Snapshot",
            "3 · Zoning Stack",
            "4 · Buildable Envelope",
            "5 · Development Options Matrix",
            "6 · Wraparound Constraints",
            "7 · Process Pathway",
            "8 · Open Items",
            "9 · Methodology",
        ):
            assert header in html, f"missing section header: {header!r}"

    def test_html_carries_zoning_codes_and_lot_size(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        html = gen.generate(BriefInputs(town_slug=synth_town, parcel_id="BB-1",
                                        prepared_on=date(2026, 5, 7)))
        assert ">R2<" in html or "<strong>R2</strong>" in html
        assert ">NMF<" in html or "<strong>NMF</strong>" in html
        assert "3,000 sf" in html

    def test_html_displays_owner_when_property_record_exists(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        html = gen.generate(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        assert "TEST OWNER" in html
        assert "1927" in html

    def test_html_shows_no_overlap_for_clean_wraparound(self, synth_lake, synth_town):
        gen = BuildabilityBriefGenerator(town_slug=synth_town, data_dir=synth_lake)
        html = gen.generate(BriefInputs(town_slug=synth_town, parcel_id="BB-1"))
        assert html.count("No overlap.") == 4  # 4 wraparound categories all clear


# ---------------------------------------------------------------------------
# Live integration — 29 Walnut St brief from the real Phase 2a-2d Gold lake
# ---------------------------------------------------------------------------

ARLINGTON_GOLD = pathlib.Path("data/gold/arlington-ma")
WALNUT_PARCEL_ID = "128.0-0003-0012.0"
REQUIRED_PARQUETS = (
    "parcel.parquet", "zoning.parquet", "zoning-overlay.parquet",
    "macris.parquet", "local-historic.parquet",
    "environmental-overlay.parquet", "noncompliance.parquet",
)


@pytest.mark.skipif(
    not all((ARLINGTON_GOLD / f).exists() for f in REQUIRED_PARQUETS),
    reason=(
        "Skipped because the Arlington Gold lake hasn't been populated. "
        "Run: python core/master_loop.py --towns arlington-ma --skip-discovery"
    ),
)
class Test29WalnutIntegration:
    """End-to-end: render the 29 Walnut brief from the real parquets."""

    @pytest.fixture(scope="class")
    def data_and_html(self) -> tuple[BriefData, str]:
        gen = BuildabilityBriefGenerator(town_slug="arlington-ma")
        inputs = BriefInputs(
            town_slug="arlington-ma",
            parcel_id=WALNUT_PARCEL_ID,
            prepared_for="Julie Gibson",
            prepared_on=date(2026, 5, 7),
        )
        data = gen.collect_data(inputs)
        html = gen.render_html(data)
        return data, html

    def test_parcel_snapshot_data(self, data_and_html):
        data, _ = data_and_html
        assert data.parcel.parcel_id == WALNUT_PARCEL_ID
        assert "WALNUT" in (data.parcel.address or "").upper()
        assert data.parcel.area_sqft and data.parcel.area_sqft > 3000

    def test_zoning_stack_has_r2_and_nmf(self, data_and_html):
        data, _ = data_and_html
        base_codes = {h.code for h in data.base_zoning_hits}
        overlay_codes = {h.code for h in data.overlay_zoning_hits}
        assert "R2" in base_codes
        assert "NMF" in overlay_codes
        assert data.has_overlay_election is True

    def test_envelope_math_runs_for_r2(self, data_and_html):
        data, _ = data_and_html
        r2 = next((e for e in data.envelopes if e.zone_code == "R2"), None)
        assert r2 is not None
        assert r2.max_far == pytest.approx(0.50)
        assert r2.lot_sqft > 3000  # GIS polygon area
        assert r2.max_gfa_sqft == pytest.approx(r2.lot_sqft * 0.50)

    def test_all_wraparound_clear(self, data_and_html):
        data, _ = data_and_html
        for w in data.wraparound:
            assert w.status == "clear", (
                f"expected '{w.label}' to be clear; got status={w.status} "
                f"detail={w.detail}"
            )

    def test_html_carries_29_walnut_facts(self, data_and_html):
        _, html = data_and_html
        assert "29 WALNUT" in html.upper()
        assert "128.0-0003-0012.0" in html
        assert "<strong>R2</strong>" in html
        assert "<strong>NMF</strong>" in html
        assert html.count("No overlap.") == 4

    def test_html_writes_to_disk_round_trip(self, data_and_html, tmp_path):
        _, html = data_and_html
        out = tmp_path / "29_walnut_v2.html"
        out.write_text(html, encoding="utf-8")
        assert out.exists()
        assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
        assert "Buildability Brief" in out.read_text(encoding="utf-8")
