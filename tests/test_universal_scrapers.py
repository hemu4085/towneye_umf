# [FILE PATH]: tests/test_universal_scrapers.py
# Patch #186 (migrated from test_arlington_scraper.py — Patch #163)
# Execution Mode: Universal Scraper Unit Tests (Bronze → Gold)
# Date: 2026-03-01

"""
Unit tests for scrapers.property_scraper.ArlingtonPropertyScraper.

All HTTP I/O is mocked via a fake requests.Session injected at construction
time.  All database I/O is mocked via a fake PartyLinker injected at
construction time.  No live network or database connections are made.

Test matrix
-----------
  - parse_records: well-formed HTML table → correct list of Bronze dicts
  - parse_records: HTML with no <table> → empty list
  - parse_records: header-only table → empty list
  - _has_next_page: page with "Next" link → True
  - _has_next_page: page without "Next" link → False
  - _has_next_page: case-insensitive "NEXT PAGE" → True
  - _promote_to_gold: linker.resolve called with correct (te_source, source_id)
  - _promote_to_gold: te_party_pk from linker is in the Gold record
  - _promote_to_gold: legal_name mapped from owner column
  - _promote_to_gold: non-consumed fields land in metadata
  - run (single page): parquet file created with correct suffix
  - run (single page): output path parent directory contains town_slug
  - run (single page): row count matches Bronze record count
  - run (single page): te_source column present with correct value
  - run (single page): te_party_pk column present (Gold record present)
  - run (single page): output dir created if missing
  - run (multi-page): both pages aggregated into single parquet
  - run (zero records): ValueError raised before linker is ever touched
"""

import pathlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.identity_linker import PartyLinker
from scrapers.property_scraper import ArlingtonPropertyScraper


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

_HTML_TWO_RECORDS = """
<html><body>
<table>
  <tr>
    <th>Parcel ID</th>
    <th>Owner</th>
    <th>Address</th>
    <th>Assessed Value</th>
  </tr>
  <tr>
    <td>001-001-001</td>
    <td>DOE, JOHN</td>
    <td>1 MAIN ST</td>
    <td>500000</td>
  </tr>
  <tr>
    <td>001-001-002</td>
    <td>SMITH, JANE</td>
    <td>2 ELM ST</td>
    <td>600000</td>
  </tr>
</table>
</body></html>
"""

_HTML_NO_TABLE = "<html><body><p>No results found.</p></body></html>"

_HTML_HEADER_ONLY = """
<html><body>
<table>
  <tr><th>Parcel ID</th><th>Owner</th></tr>
</table>
</body></html>
"""

# Pagination fixtures include Owner so _promote_to_gold has valid legal_name
_HTML_WITH_NEXT = """
<html><body>
<table>
  <tr><th>Parcel ID</th><th>Owner</th></tr>
  <tr><td>001-001-003</td><td>JONES, ALICE</td></tr>
</table>
<a href="?Page=2">Next</a>
</body></html>
"""

_HTML_NO_NEXT = """
<html><body>
<table>
  <tr><th>Parcel ID</th><th>Owner</th></tr>
  <tr><td>001-001-004</td><td>BROWN, BOB</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

TOWN_SLUG = "arlington-ma"
CONFIG_BASE = "configs"

# Expected values sourced from configs/arlington-ma/config.yaml
EXPECTED_TE_SOURCE = "arlington-ma-tax-assessor"
EXPECTED_GEO_HASH = "drt2zh"
MOCK_PARTY_PK = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(html_pages: list[str]) -> MagicMock:
    """
    Build a fake requests.Session whose .get() returns HTML pages in order.
    """
    session = MagicMock()
    responses = []
    for html in html_pages:
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        responses.append(resp)
    session.get.side_effect = responses
    return session


def _mock_linker(pk: int = MOCK_PARTY_PK) -> MagicMock:
    """Return a PartyLinker mock whose resolve() always returns *pk*."""
    linker = MagicMock(spec=PartyLinker)
    linker.resolve.return_value = pk
    return linker


def _make_scraper(
    html_pages: list[str],
    linker: MagicMock | None = None,
) -> ArlingtonPropertyScraper:
    session = _make_session(html_pages)
    return ArlingtonPropertyScraper(
        town_slug=TOWN_SLUG,
        config_base_dir=CONFIG_BASE,
        session=session,
        linker=linker,
    )


# ---------------------------------------------------------------------------
# parse_records — Bronze layer (no linker / factory involved)
# ---------------------------------------------------------------------------

class TestParseRecords:
    def test_two_data_rows_parsed(self):
        scraper = _make_scraper([_HTML_TWO_RECORDS])
        records = scraper.parse_records(_HTML_TWO_RECORDS)

        assert len(records) == 2

    def test_column_names_normalised(self):
        scraper = _make_scraper([_HTML_TWO_RECORDS])
        records = scraper.parse_records(_HTML_TWO_RECORDS)

        assert "parcel_id" in records[0]
        assert "owner" in records[0]
        assert "address" in records[0]
        assert "assessed_value" in records[0]

    def test_te_source_stamped(self):
        scraper = _make_scraper([_HTML_TWO_RECORDS])
        records = scraper.parse_records(_HTML_TWO_RECORDS)

        for rec in records:
            assert rec["te_source"] == EXPECTED_TE_SOURCE

    def test_te_geo_hash_stamped(self):
        scraper = _make_scraper([_HTML_TWO_RECORDS])
        records = scraper.parse_records(_HTML_TWO_RECORDS)

        for rec in records:
            assert rec["te_geo_hash"] == EXPECTED_GEO_HASH

    def test_no_table_returns_empty_list(self):
        scraper = _make_scraper([_HTML_NO_TABLE])
        assert scraper.parse_records(_HTML_NO_TABLE) == []

    def test_header_only_table_returns_empty_list(self):
        scraper = _make_scraper([_HTML_HEADER_ONLY])
        assert scraper.parse_records(_HTML_HEADER_ONLY) == []

    def test_cell_values_extracted_correctly(self):
        scraper = _make_scraper([_HTML_TWO_RECORDS])
        records = scraper.parse_records(_HTML_TWO_RECORDS)

        assert records[0]["parcel_id"] == "001-001-001"
        assert records[0]["owner"] == "DOE, JOHN"
        assert records[1]["assessed_value"] == "600000"


# ---------------------------------------------------------------------------
# _has_next_page
# ---------------------------------------------------------------------------

class TestHasNextPage:
    def test_next_link_present(self):
        scraper = _make_scraper([_HTML_WITH_NEXT])
        assert scraper._has_next_page(_HTML_WITH_NEXT) is True

    def test_no_next_link(self):
        scraper = _make_scraper([_HTML_NO_NEXT])
        assert scraper._has_next_page(_HTML_NO_NEXT) is False

    def test_case_insensitive(self):
        html = (
            "<html><body>"
            "<table><tr><th>X</th></tr><tr><td>1</td></tr></table>"
            "<a href='#'>NEXT PAGE</a>"
            "</body></html>"
        )
        scraper = _make_scraper([html])
        assert scraper._has_next_page(html) is True


# ---------------------------------------------------------------------------
# _promote_to_gold — identity resolution + MedallionFactory integration
# ---------------------------------------------------------------------------

class TestPromoteToGold:
    def _bronze_record(self) -> dict:
        return {
            "parcel_id": "001-001-001",
            "owner": "DOE, JOHN",
            "address": "1 MAIN ST",
            "assessed_value": "500000",
            "te_source": EXPECTED_TE_SOURCE,
            "te_geo_hash": EXPECTED_GEO_HASH,
        }

    def test_linker_called_with_te_source_and_source_id(self):
        linker = _mock_linker()
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        scraper._promote_to_gold(self._bronze_record(), linker)

        linker.resolve.assert_called_once_with(EXPECTED_TE_SOURCE, "001-001-001")

    def test_gold_record_has_correct_te_party_pk(self):
        linker = _mock_linker(pk=99)
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        gold = scraper._promote_to_gold(self._bronze_record(), linker)

        assert gold["te_party_pk"] == 99

    def test_legal_name_mapped_from_owner_column(self):
        linker = _mock_linker()
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        gold = scraper._promote_to_gold(self._bronze_record(), linker)

        assert gold["legal_name"] == "DOE, JOHN"

    def test_non_consumed_fields_in_metadata(self):
        linker = _mock_linker()
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        gold = scraper._promote_to_gold(self._bronze_record(), linker)

        assert gold["metadata"]["address"] == "1 MAIN ST"
        assert gold["metadata"]["assessed_value"] == "500000"

    def test_consumed_fields_not_duplicated_in_metadata(self):
        """parcel_id, owner, te_source, te_geo_hash must not appear in metadata."""
        linker = _mock_linker()
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        gold = scraper._promote_to_gold(self._bronze_record(), linker)

        metadata_keys = set(gold["metadata"].keys())
        assert "parcel_id" not in metadata_keys
        assert "owner" not in metadata_keys
        assert "te_source" not in metadata_keys
        assert "te_geo_hash" not in metadata_keys

    def test_gold_record_passes_audit_shield(self):
        """All 7 mandatory audit fields must be present in the Gold record."""
        linker = _mock_linker()
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        gold = scraper._promote_to_gold(self._bronze_record(), linker)

        for field in ("te_id", "te_source", "te_confidence", "te_timestamp",
                      "te_version", "te_geo_hash", "te_updated_by"):
            assert field in gold, f"Audit field '{field}' missing from Gold record"

    def test_party_type_is_individual(self):
        linker = _mock_linker()
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=linker)

        gold = scraper._promote_to_gold(self._bronze_record(), linker)

        assert gold["party_type"] == "INDIVIDUAL"


# ---------------------------------------------------------------------------
# run — single page (linker injected)
# ---------------------------------------------------------------------------

class TestRunSinglePage:
    def test_parquet_file_created(self, tmp_path):
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=_mock_linker())
        out = scraper.run(output_dir=str(tmp_path))

        assert out.exists()
        assert out.suffix == ".parquet"

    def test_output_path_parent_contains_town_slug(self, tmp_path):
        """Partitioned layout: town_slug lives in the parent dir, not the filename."""
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=_mock_linker())
        out = scraper.run(output_dir=str(tmp_path))

        assert TOWN_SLUG in str(out.parent)

    def test_parquet_row_count_matches(self, tmp_path):
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=_mock_linker())
        out = scraper.run(output_dir=str(tmp_path))

        df = pd.read_parquet(out)
        assert len(df) == 2

    def test_parquet_contains_te_source_column(self, tmp_path):
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=_mock_linker())
        out = scraper.run(output_dir=str(tmp_path))

        df = pd.read_parquet(out)
        assert "te_source" in df.columns
        assert (df["te_source"] == EXPECTED_TE_SOURCE).all()

    def test_parquet_contains_te_party_pk_column(self, tmp_path):
        """Gold records must carry te_party_pk from the identity linker."""
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=_mock_linker(pk=MOCK_PARTY_PK))
        out = scraper.run(output_dir=str(tmp_path))

        df = pd.read_parquet(out)
        assert "te_party_pk" in df.columns
        assert (df["te_party_pk"] == MOCK_PARTY_PK).all()

    def test_output_dir_created_if_missing(self, tmp_path):
        new_dir = tmp_path / "nested" / "bronze"
        scraper = _make_scraper([_HTML_TWO_RECORDS], linker=_mock_linker())
        scraper.run(output_dir=str(new_dir))

        assert new_dir.exists()


# ---------------------------------------------------------------------------
# run — multi-page (linker injected)
# ---------------------------------------------------------------------------

class TestRunMultiPage:
    def test_two_pages_aggregated(self, tmp_path):
        """Page 1 has a 'Next' link; page 2 does not → 2 Gold rows total."""
        scraper = _make_scraper(
            [_HTML_WITH_NEXT, _HTML_NO_NEXT], linker=_mock_linker()
        )
        out = scraper.run(output_dir=str(tmp_path))

        df = pd.read_parquet(out)
        assert len(df) == 2


# ---------------------------------------------------------------------------
# run — zero records (no linker needed; ValueError raised first)
# ---------------------------------------------------------------------------

class TestRunZeroRecords:
    def test_raises_value_error_on_empty_result(self, tmp_path):
        """ValueError is raised before the linker is ever touched."""
        scraper = _make_scraper([_HTML_NO_TABLE])
        with pytest.raises(ValueError, match="0 records scraped"):
            scraper.run(output_dir=str(tmp_path))

# tests/test_universal_scrapers.py
# End of Patch #186
