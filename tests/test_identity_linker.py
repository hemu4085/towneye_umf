# [FILE PATH]: tests/test_identity_linker.py
# Patch #160
# Execution Mode: PartyLinker Unit Tests
# Date: 2026-03-01

"""
Unit tests for core.identity_linker.PartyLinker.

All PostgreSQL I/O is fully mocked — no live database required.
Test matrix:
  - HIT:  (te_source, source_id) exists → existing pk returned, no INSERT
  - MISS: pair is new → upsert CTE inserts a row, new pk returned
  - ENV:  DATABASE_URL environment variable is used when no dsn kwarg supplied
  - KEY:  KeyError raised when neither dsn nor DATABASE_URL is present
"""

import os
from unittest.mock import MagicMock, call, patch

import pytest

from core.identity_linker import PartyLinker, _DEFAULT_IDENTITY_TABLE, _DEFAULT_SCHEMA


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DSN = "postgresql://user:pass@localhost:5432/testdb"
TE_SOURCE = "arlington-ma-tax-assessor"
SOURCE_ID = "PARCEL-001"
EXISTING_PK = 42
NEW_PK = 99


def _make_linker(dsn: str = TEST_DSN) -> PartyLinker:
    return PartyLinker(dsn=dsn)


def _mock_connection(fetchone_return):
    """
    Build a layered mock that satisfies psycopg2's context-manager protocol:
        with conn as conn:
            with conn.cursor() as cur:
                cur.execute(...)
                cur.fetchone()  → fetchone_return
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_return
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# HIT: existing record found
# ---------------------------------------------------------------------------

class TestResolveHit:
    def test_returns_existing_pk(self):
        """CTE returns a row → existing pk is returned, commit is called."""
        mock_conn, mock_cursor = _mock_connection((EXISTING_PK,))

        with patch("core.identity_linker.psycopg2.connect", return_value=mock_conn):
            linker = _make_linker()
            result = linker.resolve(TE_SOURCE, SOURCE_ID)

        assert result == EXISTING_PK

    def test_commit_called_on_hit(self):
        mock_conn, _ = _mock_connection((EXISTING_PK,))

        with patch("core.identity_linker.psycopg2.connect", return_value=mock_conn):
            _make_linker().resolve(TE_SOURCE, SOURCE_ID)

        mock_conn.commit.assert_called_once()

    def test_execute_called_with_correct_params(self):
        mock_conn, mock_cursor = _mock_connection((EXISTING_PK,))

        with patch("core.identity_linker.psycopg2.connect", return_value=mock_conn):
            _make_linker().resolve(TE_SOURCE, SOURCE_ID)

        mock_cursor.execute.assert_called_once()
        # call_args unpacks as (positional_args_tuple, kwargs_dict).
        # Destructure both levels in one step to avoid indexing ambiguity:
        #   (sql_str, bound_values), kwargs = call_args
        (_, bound_values), _kwargs = mock_cursor.execute.call_args
        assert TE_SOURCE in bound_values
        assert SOURCE_ID in bound_values


# ---------------------------------------------------------------------------
# MISS: new record created
# ---------------------------------------------------------------------------

class TestResolveMiss:
    def test_returns_new_pk(self):
        """CTE inserts a new row → freshly generated pk is returned."""
        mock_conn, mock_cursor = _mock_connection((NEW_PK,))

        with patch("core.identity_linker.psycopg2.connect", return_value=mock_conn):
            result = _make_linker().resolve(TE_SOURCE, SOURCE_ID)

        assert result == NEW_PK

    def test_commit_called_on_miss(self):
        mock_conn, _ = _mock_connection((NEW_PK,))

        with patch("core.identity_linker.psycopg2.connect", return_value=mock_conn):
            _make_linker().resolve(TE_SOURCE, SOURCE_ID)

        mock_conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Schema / table name configuration
# ---------------------------------------------------------------------------

class TestFqnConstruction:
    def test_default_fqn(self):
        linker = _make_linker()
        assert linker._fqn == f"{_DEFAULT_SCHEMA}.{_DEFAULT_IDENTITY_TABLE}"

    def test_custom_schema_and_table(self):
        linker = PartyLinker(
            dsn=TEST_DSN,
            schema="public",
            identity_table="custom_map",
        )
        assert linker._fqn == "public.custom_map"


# ---------------------------------------------------------------------------
# Environment variable DSN
# ---------------------------------------------------------------------------

class TestDsnFromEnv:
    def test_uses_database_url_env_var(self, monkeypatch):
        """When no dsn kwarg is given, DATABASE_URL env var must be used."""
        monkeypatch.setenv("DATABASE_URL", TEST_DSN)
        linker = PartyLinker()
        assert linker._dsn == TEST_DSN

    def test_raises_key_error_without_dsn_or_env(self, monkeypatch):
        """Missing DATABASE_URL and no dsn → KeyError."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(KeyError):
            PartyLinker()


# ---------------------------------------------------------------------------
# RuntimeError when upsert returns None
# ---------------------------------------------------------------------------

class TestUpsertNoneGuard:
    def test_runtime_error_on_none_row(self):
        """If the CTE returns no row, RuntimeError must be raised."""
        mock_conn, mock_cursor = _mock_connection(None)

        with patch("core.identity_linker.psycopg2.connect", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="Upsert returned no row"):
                _make_linker().resolve(TE_SOURCE, SOURCE_ID)

# tests/test_identity_linker.py
# End of Patch #160
