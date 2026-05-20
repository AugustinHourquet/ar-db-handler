"""Shared connection helpers.

This module is intentionally minimal: it knows how to open a SQLite
connection with the project's pragmas (WAL journal mode, foreign-key
enforcement) and how to apply a schema DDL file against an existing
connection.

It does not know anything about the contents of the schema or about
which database it is opening — that is the job of `filings.init` and
`metrics.init`.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def open_connection(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with the project's standard pragmas.

    Pragmas applied:
      * `journal_mode = WAL`  — concurrent readers + single writer
      * `foreign_keys = ON`   — FK constraints are enforced
      * `row_factory = sqlite3.Row` — column access by name

    Parameters
    ----------
    path:
        Filesystem path to the SQLite file. Parent directories must
        already exist; this function does not create them.

    Returns
    -------
    sqlite3.Connection
        An open connection. The caller owns it and is responsible for
        closing it.
    """
    path = Path(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # journal_mode is a PRAGMA that returns a row; consume it.
    cur = conn.execute("PRAGMA journal_mode = WAL")
    cur.fetchone()
    conn.execute("PRAGMA foreign_keys = ON")
    logger.debug("Opened SQLite connection: %s (WAL, FK on)", path)
    return conn


def apply_schema(conn: sqlite3.Connection, schema_sql: str) -> None:
    """Execute a multi-statement DDL script against the connection.

    Uses `executescript`, which implicitly commits before running. All
    statements in `schema_sql` should be idempotent (`CREATE TABLE IF
    NOT EXISTS`, etc.) so that calling `init_*_db` on an existing file
    is a no-op.
    """
    conn.executescript(schema_sql)
    conn.commit()
