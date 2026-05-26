"""
Shared SQLite connection helpers.

Both `init_filings_db()` and `init_metrics_db()` delegate to `_init_db()` here
to ensure consistent pragma settings (WAL mode, FK enforcement) and consistent
schema-loading behaviour across the two databases.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def _init_db(db_path: str | Path, schema_package: str) -> sqlite3.Connection:
    """
    Open (or create) a SQLite database at ``db_path``, apply the schema, and
    return a connection with WAL mode enabled and foreign-key enforcement on.

    The schema is loaded as a package resource so the SQL file is shipped
    inside the installed wheel — no fragile filesystem lookups at runtime.

    Args:
        db_path:        Filesystem path to the SQLite database file. Parent
                        directories are created if missing.
        schema_package: Dotted package path that contains a ``schema.sql``
                        resource (e.g. ``"ar_db_handler.filings"``).

    Returns:
        Open ``sqlite3.Connection`` with WAL mode and FK enforcement enabled.
        The schema has been applied (DDL is ``CREATE TABLE IF NOT EXISTS``,
        so re-opening an existing DB is a no-op).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))

    # FK enforcement is per-connection in SQLite — set it BEFORE the caller
    # starts any transaction.
    conn.execute("PRAGMA foreign_keys = ON;")

    # WAL mode is per-database (persists once set) but is cheap to set again.
    # journal_mode is a query, not a no-result PRAGMA.
    conn.execute("PRAGMA journal_mode = WAL;").fetchone()

    schema_sql = resources.files(schema_package).joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()

    return conn
