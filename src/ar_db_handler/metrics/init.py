"""``metrics.db`` initialisation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..connection import _init_db


def init_metrics_db(path: str | Path) -> sqlite3.Connection:
    """
    Create (or open) ``metrics.db`` at ``path`` and return a connection.

    See ``init_filings_db`` for the pragma details — both functions share the
    same underlying helper. The ``metrics`` table is currently a stub; the
    full column set is to be defined by the evaluator team.
    """
    return _init_db(path, schema_package="ar_db_handler.metrics")
