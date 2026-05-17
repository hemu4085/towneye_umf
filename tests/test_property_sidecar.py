# [FILE PATH]: tests/test_property_sidecar.py
# Patch #206
# Execution Mode: Tier 4.5 — Patriot Parser + Sidecar Promoter Unit Tests
# Date: 2026-05-07

"""
Unit tests for the Tier 4.5 deliverables:

  * ``ArlingtonPropertyScraper._parse_lot_size_fin_area``
  * ``ArlingtonPropertyScraper._parse_sale_date_price``
  * ``ArlingtonPropertyScraper._parse_luc_description``
  * ``PropertySidecarPromoter`` (loader, filter, promote, merge orchestration)
  * End-to-end sidecar→parquet pipeline against a synthetic Arlington
    config + temp Bronze tree.

These tests exercise the parsers in isolation (no scraper instance
needed for the static helpers) and use the **real** arlington-ma config
to drive the sidecar promoter through ``_promote_to_gold`` so we test
the same code path the production CLI hits.

There is no live HTTP traffic in any test — sidecar JSON files live on
the temp filesystem, and the parquet outputs are written to the test's
tmp_path.
"""

from __future__ import annotations

import json
import pathlib
from typing import Dict

import pandas as pd
import pytest

from scrapers.property_scraper import ArlingtonPropertyScraper
from scrapers.property_sidecar import PropertySidecarPromoter

# Captured at import time so tests that monkeypatch.chdir(tmp_path) can
# still hand the promoter an absolute path to the real configs/ tree.
PROJECT_CONFIGS_DIR = (pathlib.Path(__file__).resolve().parent.parent / "configs").resolve()


# ---------------------------------------------------------------------------
# Static parsers
# ---------------------------------------------------------------------------

class TestParseLotSizeFinArea:
    def test_typical_29_walnut_format(self):
        lot, fin = ArlingtonPropertyScraper._parse_lot_size_fin_area("3,023 1,490")
        assert lot == 3023.0
        assert fin == 1490.0

    def test_lot_only_no_finished_area(self):
        lot, fin = ArlingtonPropertyScraper._parse_lot_size_fin_area("7,627")
        assert lot == 7627.0
        assert fin is None

    def test_extra_whitespace(self):
        lot, fin = ArlingtonPropertyScraper._parse_lot_size_fin_area("  3023   1490  ")
        assert lot == 3023.0
        assert fin == 1490.0

    def test_empty_returns_none_pair(self):
        assert ArlingtonPropertyScraper._parse_lot_size_fin_area(None) == (None, None)
        assert ArlingtonPropertyScraper._parse_lot_size_fin_area("") == (None, None)
        assert ArlingtonPropertyScraper._parse_lot_size_fin_area("   ") == (None, None)

    def test_garbage_components_return_none(self):
        lot, fin = ArlingtonPropertyScraper._parse_lot_size_fin_area("foo bar")
        assert lot is None and fin is None


class TestParseSaleDatePrice:
    def test_29_walnut_real_format_with_stray_space(self):
        """Patriot Properties output: '6/13/ 2017 $750,000' (note space after '/')."""
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("6/13/ 2017 $750,000")
        assert d == "2017-06-13"
        assert p == 750000.0

    def test_29_walnut_terr_real_format(self):
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("11/15/ 2024 $1,125,000")
        assert d == "2024-11-15"
        assert p == 1125000.0

    def test_two_digit_year_2017(self):
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("6/13/17 $750,000")
        assert d == "2017-06-13"
        assert p == 750000.0

    def test_zero_padded_dates(self):
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("06/13/2017 $750,000")
        assert d == "2017-06-13"
        assert p == 750000.0

    def test_price_with_decimal(self):
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("6/13/2017 $750,000.50")
        assert d == "2017-06-13"
        assert p == 750000.50

    def test_only_price_no_date(self):
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("$ 12,345")
        assert d is None
        assert p == 12345.0

    def test_only_date_no_price(self):
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("6/13/2017")
        assert d == "2017-06-13"
        assert p is None

    def test_invalid_date_falls_through_but_price_survives(self):
        """Date '13/13/2017' is invalid (month=13); price still parsed."""
        d, p = ArlingtonPropertyScraper._parse_sale_date_price("13/13/2017 $99")
        assert d is None
        assert p == 99.0

    def test_empty_returns_none_pair(self):
        assert ArlingtonPropertyScraper._parse_sale_date_price(None) == (None, None)
        assert ArlingtonPropertyScraper._parse_sale_date_price("") == (None, None)


class TestParseLucDescription:
    def test_typical_29_walnut_format(self):
        luc, desc = ArlingtonPropertyScraper._parse_luc_description("101 One Family")
        assert luc == "101"
        assert desc == "One Family"

    def test_three_digit_code(self):
        luc, desc = ArlingtonPropertyScraper._parse_luc_description("104 Two Family")
        assert luc == "104"
        assert desc == "Two Family"

    def test_no_numeric_prefix_returns_none_code(self):
        luc, desc = ArlingtonPropertyScraper._parse_luc_description("Mixed Use")
        assert luc is None
        assert desc == "Mixed Use"

    def test_empty_returns_none_pair(self):
        assert ArlingtonPropertyScraper._parse_luc_description(None) == (None, None)
        assert ArlingtonPropertyScraper._parse_luc_description("") == (None, None)


# ---------------------------------------------------------------------------
# Sidecar loader (file discovery + JSON shape tolerance)
# ---------------------------------------------------------------------------

class TestSidecarLoading:
    def test_load_wrapped_layout(self, tmp_path: pathlib.Path):
        f = tmp_path / "assessor.json"
        f.write_text(json.dumps({
            "status": 200,
            "saved_html": "ignored.html",
            "parsed_29_records": [
                {"parcel_id": "P-1", "owner": "OWNER A"},
                {"parcel_id": "P-2", "owner": "OWNER B"},
            ],
        }))
        recs = PropertySidecarPromoter.load_records_from_file(f)
        assert len(recs) == 2
        assert {r["parcel_id"] for r in recs} == {"P-1", "P-2"}

    def test_load_flat_list_layout(self, tmp_path: pathlib.Path):
        f = tmp_path / "flat.json"
        f.write_text(json.dumps([
            {"parcel_id": "P-1", "owner": "OWNER A"},
            {"parcel_id": "P-2", "owner": "OWNER B"},
        ]))
        recs = PropertySidecarPromoter.load_records_from_file(f)
        assert len(recs) == 2

    def test_load_unknown_shape_returns_empty(self, tmp_path: pathlib.Path):
        f = tmp_path / "weird.json"
        f.write_text(json.dumps({"foo": "bar"}))
        assert PropertySidecarPromoter.load_records_from_file(f) == []

    def test_load_unparseable_returns_empty(self, tmp_path: pathlib.Path):
        f = tmp_path / "bad.json"
        f.write_text("{ not valid json")
        assert PropertySidecarPromoter.load_records_from_file(f) == []

    def test_discover_glob_walks_data_dir(self, tmp_path: pathlib.Path):
        (tmp_path / "p1").mkdir()
        (tmp_path / "p2").mkdir()
        (tmp_path / "other").mkdir()
        (tmp_path / "p1" / "assessor.json").write_text("[]")
        (tmp_path / "p2" / "assessor.json").write_text("[]")
        (tmp_path / "other" / "not_assessor.json").write_text("[]")

        promoter = PropertySidecarPromoter(
            town_slug="arlington-ma",
            config_base_dir=str(PROJECT_CONFIGS_DIR),
            data_dir=tmp_path,
            gold_dir=tmp_path / "gold",
        )
        files = promoter.discover_sidecar_files()
        names = sorted(p.parent.name for p in files)
        assert names == ["p1", "p2"]


# ---------------------------------------------------------------------------
# End-to-end against the real arlington-ma config
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_29_walnut_sidecar(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> pathlib.Path:
    """
    Mimic the on-disk layout produced by ``scripts/29_walnut_queries.py``
    *and* chdir into the temp dir.

    Why chdir?  ``core.storage.save_gold_data`` deliberately normalises
    any absolute output path back to a ``data/<tier>/...`` relative
    path (a safety feature that prevents nested
    ``data/gold/abs/path/data/gold`` artifacts when the CLI is run with
    odd ``--output-dir`` values).  The side effect is that absolute
    ``tmp_path``s are silently rewritten to the project's real
    ``data/gold``.  Working from a temporary CWD with the canonical
    ``data/<bronze|gold>`` subtree keeps the test fully isolated.
    """
    monkeypatch.chdir(tmp_path)
    bronze_dir = tmp_path / "data" / "29_walnut"
    bronze_dir.mkdir(parents=True)
    payload: Dict = {
        "status": 200,
        "saved_html": "data/29_walnut/assessor.html",
        "parsed_29_records": [
            {
                "parcel_id":             "128.0-0003-0012.0",
                "location":              "29 WALNUT ST",
                "owner":                 "GHAI JESSICA & SANDEEP",
                "built_type":            "1927 Old Style",
                "total_value":           "$1,002,300",
                "beds_baths":            "3 1",
                "lot_size_fin_area":     "3,023 1,490",
                "luc_description":       "101 One Family",
                "nhood":                 "9",
                "sale_date_sale_price":  "6/13/ 2017 $750,000",
                "book_page":             "69423-104",
                "te_source":             "arlington-ma-tax-assessor",
                "te_geo_hash":           "drt2zh",
            },
        ],
    }
    (bronze_dir / "assessor.json").write_text(json.dumps(payload))
    return tmp_path


class TestEndToEndPromote:
    """
    Use the real arlington-ma config (so source mappings + column maps
    stay zero-hardcoded) and verify a full sidecar → property.parquet
    pipeline produces a row with every Patriot field correctly routed.
    """

    def test_29_walnut_sidecar_lands_in_property_parquet(
        self, synthetic_29_walnut_sidecar: pathlib.Path,
    ):
        promoter = PropertySidecarPromoter(
            town_slug="arlington-ma",
            config_base_dir=str(PROJECT_CONFIGS_DIR),
            data_dir="data",
            gold_dir="data/gold",
        )
        summary = promoter.run()
        assert summary["files_scanned"] == 1
        assert summary["records_promoted"] == 1
        assert summary["parcel_ids"] == ["128.0-0003-0012.0"]

        df = pd.read_parquet(
            synthetic_29_walnut_sidecar / "data" / "gold" / "arlington-ma" / "property.parquet"
        )
        assert len(df) == 1
        row = df.iloc[0]
        assert row["parcel_id"] == "128.0-0003-0012.0"
        assert row["address"] == "29 WALNUT ST"
        assert row["owner_name"] == "GHAI JESSICA & SANDEEP"
        assert int(row["year_built"]) == 1927
        assert row["building_type"] == "Old Style"
        assert row["luc"] == "101"
        assert row["luc_description"] == "One Family"
        assert int(row["beds"]) == 3
        assert float(row["baths"]) == pytest.approx(1.0)
        assert float(row["lot_size_sqft"]) == pytest.approx(3023.0)
        assert float(row["assessed_value"]) == pytest.approx(1002300.0)

        md = row["metadata"]
        if isinstance(md, str):
            md = json.loads(md)
        elif hasattr(md, "tolist"):
            md = dict(md)
        assert md["finished_area_sqft"] == pytest.approx(1490.0)
        assert md["last_sale_date"] == "2017-06-13"
        assert md["last_sale_price"] == pytest.approx(750000.0)
        assert md["book_page"] == "69423-104"

    def test_sidecar_merge_preserves_other_parcels(
        self, synthetic_29_walnut_sidecar: pathlib.Path,
    ):
        """Re-running the promoter does not duplicate rows or drop neighbours."""
        # Pre-seed property.parquet with a different parcel that should be preserved.
        seed_dir = synthetic_29_walnut_sidecar / "data" / "gold" / "arlington-ma"
        seed_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{
            "te_id":            "stub-1",
            "te_source":        "arlington-ma-tax-assessor",
            "te_confidence":    1.0,
            "te_timestamp":     pd.Timestamp("2026-01-01"),
            "te_version":       "1.0.0",
            "te_geo_hash":      "drt2zh",
            "te_updated_by":    "TEST",
            "te_property_pk":   1,
            "parcel_id":        "OTHER-PARCEL",
            "address":          "999 Other St",
            "zone_code":        None,
            "assessed_value":   500000.0,
            "year_built":       1900,
            "building_type":    "Stub",
            "lot_size_sqft":    5000.0,
            "luc":              "101",
            "luc_description":  "One Family",
            "beds":             2,
            "baths":            1.0,
            "owner_name":       "OTHER OWNER",
            "te_party_pk":      1,
            "metadata":         {"_source": "seed"},
        }]).to_parquet(seed_dir / "property.parquet")

        promoter = PropertySidecarPromoter(
            town_slug="arlington-ma",
            config_base_dir=str(PROJECT_CONFIGS_DIR),
            data_dir="data",
            gold_dir="data/gold",
        )
        promoter.run()
        # Run a second time — must be idempotent.
        promoter.run()

        df = pd.read_parquet(
            synthetic_29_walnut_sidecar / "data" / "gold" / "arlington-ma" / "property.parquet"
        )
        ids = sorted(df["parcel_id"].astype(str).tolist())
        assert ids == ["128.0-0003-0012.0", "OTHER-PARCEL"]
        assert len(df) == 2  # No duplicates after re-running.

    def test_record_filtered_when_te_source_mismatch(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """A sidecar record from a different town is not promoted."""
        monkeypatch.chdir(tmp_path)
        sidecar_dir = tmp_path / "data" / "stranger"
        sidecar_dir.mkdir(parents=True)
        (sidecar_dir / "assessor.json").write_text(json.dumps([
            {
                "parcel_id": "X-1",
                "location":  "1 Stranger Ln",
                "owner":     "STRANGER",
                "te_source": "some-other-town-assessor",
            },
        ]))
        promoter = PropertySidecarPromoter(
            town_slug="arlington-ma",
            config_base_dir=str(PROJECT_CONFIGS_DIR),
            data_dir="data",
            gold_dir="data/gold",
        )
        summary = promoter.run()
        assert summary["records_promoted"] == 0

    def test_sidecar_record_missing_id_is_skipped(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        sidecar_dir = tmp_path / "data" / "broken"
        sidecar_dir.mkdir(parents=True)
        (sidecar_dir / "assessor.json").write_text(json.dumps([
            {"location": "no parcel id here", "owner": "X"},
        ]))
        promoter = PropertySidecarPromoter(
            town_slug="arlington-ma",
            config_base_dir=str(PROJECT_CONFIGS_DIR),
            data_dir="data",
            gold_dir="data/gold",
        )
        summary = promoter.run()
        assert summary["records_promoted"] == 0
