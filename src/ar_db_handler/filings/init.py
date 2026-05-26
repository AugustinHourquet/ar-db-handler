"""
``filings.db`` initialisation.

Thin wrapper around ``ar_db_handler.connection._init_db`` that targets the
filings schema package.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..connection import _init_db


def init_filings_db(path: str | Path) -> sqlite3.Connection:
    """
    Create (or open) ``filings.db`` at ``path`` and return a connection.

    The schema (``schema.sql`` in this package) is applied via
    ``CREATE TABLE IF NOT EXISTS``, so calling this on an existing database
    is a no-op for the tables themselves. WAL mode and foreign-key
    enforcement are enabled on the returned connection.

    Args:
        path: Filesystem path to the SQLite database file.

    Returns:
        Open ``sqlite3.Connection``.
    """
    return _init_db(path, schema_package="ar_db_handler.filings")
