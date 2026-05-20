"""Initialise filings.db.

Creates the file if it does not exist, applies the schema, enables WAL
mode, and turns on FK enforcement. The schema uses `CREATE TABLE IF NOT
EXISTS`, so calling this on an already-initialised file is a safe no-op.
"""

from __future__ import annotations

import logging
import sqlite3
from importlib.resources import files
from pathlib import Path

from ..connection import apply_schema, open_connection

logger = logging.getLogger(__name__)


def _read_schema() -> str:
    return files("ar_db_handler.filings").joinpath("schema.sql").read_text()


def init_filings_db(path: str | Path) -> sqlite3.Connection:
    """Initialise filings.db and return an open connection.

    Parameters
    ----------
    path:
        Filesystem path to the SQLite file. Parent directories must
        already exist.

    Returns
    -------
    sqlite3.Connection
        An open connection to the database. The caller is responsible
        for closing it.
    """
    conn = open_connection(path)
    apply_schema(conn, _read_schema())
    logger.info("Initialised filings.db at %s", path)
    return conn
