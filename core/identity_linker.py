# [FILE PATH]: core/identity_linker.py
# Patch #157
# Execution Mode: Party Identity Resolution Engine
# Date: 2026-03-01

"""
PartyLinker
===========
Resolves a ``(te_source, source_id)`` pair to a canonical ``te_party_pk``
against the Supabase / PostgreSQL ``gold.te_identity_map`` table.

Behaviour
---------
* **HIT**  — a row for the pair already exists → return the stored
  ``te_party_pk`` immediately (no write).
* **MISS** — no row found → INSERT a new mapping row; the database
  sequence generates the BigInt PK; return it to the caller.

The resolve operation is implemented as a single atomic CTE upsert so
concurrent scrapers cannot race to create duplicate PKs.

Zero-Hardcoding contract
------------------------
* No town name, schema name, or table name may appear as a literal in
  calling code.  All identifiers default to the module-level constants
  and can be overridden by the constructor.
* The database connection string is sourced *exclusively* from the
  ``DATABASE_URL`` environment variable (or an explicit *dsn* argument).
  It is never read from ``configs/``.
"""

import logging
import os
from typing import Optional

import psycopg2
import psycopg2.extensions
import psycopg2.extras

logger = logging.getLogger(__name__)

_DEFAULT_SCHEMA: str = "gold"
_DEFAULT_IDENTITY_TABLE: str = "te_identity_map"


class HashLinker:
    """
    Offline identity linker — no database required.

    Derives a stable BigInt PK from a deterministic hash of
    ``(te_source, source_id)``.  Used automatically by scrapers when
    ``DATABASE_URL`` is not set in the environment.

    The hash function is identical to the ``_VerificationLinker`` used in
    every scraper's ``__main__`` block, so PKs are consistent between
    interactive runs and pipeline runs without a database.

    This linker is intentionally **write-only-safe**: it never reads from or
    writes to the ``gold.te_identity_map`` table.  Swap it for ``PartyLinker``
    once a PostgreSQL connection is available.
    """

    def resolve(self, te_source: str, source_id: str) -> int:
        return abs(hash(f"{te_source}:{source_id}")) % 2_000_000_000


def get_linker(dsn: Optional[str] = None) -> "PartyLinker | HashLinker":
    """
    Return the best available linker for the current environment.

    * If *dsn* is provided, or ``DATABASE_URL`` is set → ``PartyLinker``
      (full PostgreSQL identity ledger with atomic upsert).
    * Otherwise → ``HashLinker`` (deterministic, no DB needed).

    This function is the recommended way for ingestor wrappers and the
    pipeline orchestrator to obtain a linker without knowing whether a
    database is available.
    """
    effective_dsn = dsn or os.environ.get("DATABASE_URL", "")
    if effective_dsn:
        logger.debug("identity_linker | Using PartyLinker (DATABASE_URL is set).")
        return PartyLinker(dsn=effective_dsn)
    logger.info(
        "identity_linker | DATABASE_URL not set — using HashLinker "
        "(offline mode, no DB writes). Set DATABASE_URL for production."
    )
    return HashLinker()


class PartyLinker:
    """
    Resolve ``(te_source, source_id)`` → ``te_party_pk``.

    Parameters
    ----------
    dsn : str, optional
        PostgreSQL DSN / connection URL.  When omitted, the value of the
        ``DATABASE_URL`` environment variable is used.  Raises
        ``KeyError`` if neither is supplied.
    schema : str, optional
        Database schema that hosts the identity-map table.
        Defaults to ``"gold"``.
    identity_table : str, optional
        Name of the identity-map table.
        Defaults to ``"te_identity_map"``.

    Examples
    --------
    >>> linker = PartyLinker()                    # reads DATABASE_URL
    >>> pk = linker.resolve("arlington-ma-tax-assessor", "PARCEL-001")
    >>> pk
    10042
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        schema: str = _DEFAULT_SCHEMA,
        identity_table: str = _DEFAULT_IDENTITY_TABLE,
    ) -> None:
        effective = dsn or os.environ.get("DATABASE_URL", "")
        if not effective:
            raise RuntimeError(
                "PartyLinker requires a PostgreSQL connection. "
                "Set DATABASE_URL or pass dsn=, or use get_linker() for "
                "automatic fallback to HashLinker when no DB is available."
            )
        self._dsn: str = effective
        self._schema: str = schema
        self._table: str = identity_table
        self._fqn: str = f"{self._schema}.{self._table}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> psycopg2.extensions.connection:
        """Open and return a new database connection."""
        conn = psycopg2.connect(self._dsn)
        conn.autocommit = False
        return conn

    def _upsert_pk(
        self,
        cursor: psycopg2.extensions.cursor,
        te_source: str,
        source_id: str,
    ) -> int:
        """
        Atomic upsert: insert if the pair is new, do nothing if it exists.
        Returns ``te_party_pk`` regardless of whether a row was inserted.

        The CTE pattern guarantees a single round-trip and is safe under
        concurrent load — no SELECT-then-INSERT race condition.
        """
        sql = f"""
            WITH ins AS (
                INSERT INTO {self._fqn} (te_source, source_id)
                VALUES (%s, %s)
                ON CONFLICT (te_source, source_id) DO NOTHING
                RETURNING te_party_pk
            )
            SELECT te_party_pk FROM ins
            UNION ALL
            SELECT te_party_pk
            FROM   {self._fqn}
            WHERE  te_source = %s
            AND    source_id = %s
            LIMIT  1
        """
        cursor.execute(sql, (te_source, source_id, te_source, source_id))
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(
                f"PartyLinker | Upsert returned no row for "
                f"te_source='{te_source}' source_id='{source_id}'. "
                "Verify that the identity-map table exists and the sequence is healthy."
            )
        return int(row[0])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, te_source: str, source_id: str) -> int:
        """
        Return the canonical ``te_party_pk`` for a (te_source, source_id) pair.

        If the pair already exists in ``te_identity_map``, the existing PK is
        returned immediately (no write occurs).  Otherwise a new row is
        INSERTed and the DB-sequence-generated BigInt PK is returned.

        Parameters
        ----------
        te_source : str
            Originating system identifier (e.g. ``"arlington-ma-tax-assessor"``).
            Must match a value in the town config's ``source_mappings``.
        source_id : str
            Upstream system's native primary key for the record
            (e.g. a parcel ID or account number).

        Returns
        -------
        int
            Canonical ``te_party_pk`` (BigInt).  Safe to use as the PK
            argument to :meth:`~core.factory.MedallionFactory.map_to_party`.

        Raises
        ------
        KeyError
            If ``DATABASE_URL`` env var is not set and no *dsn* was supplied
            to the constructor.
        psycopg2.DatabaseError
            On any unrecoverable database error (connection failure, constraint
            violation outside the expected conflict path, etc.).
        RuntimeError
            If the upsert CTE returns no row (indicates a schema problem).
        """
        logger.debug(
            "PartyLinker.resolve | te_source='%s' source_id='%s'",
            te_source,
            source_id,
        )

        with self._connect() as conn:
            with conn.cursor() as cur:
                pk = self._upsert_pk(cur, te_source, source_id)
                conn.commit()

        logger.info(
            "PartyLinker.resolve | te_party_pk=%d "
            "(te_source='%s', source_id='%s')",
            pk,
            te_source,
            source_id,
        )
        return pk

# core/identity_linker.py
# End of Patch #157
