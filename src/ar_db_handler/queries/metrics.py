"""
Read helpers for ``metrics.db``.

Stub — the ``metrics`` table schema isn't finalised yet. The single helper
here just returns rows by primary key so the package has a query module
ready for when the column set is defined.
"""

from __future__ import annotations

import sqlite3


def get_metric(conn: sqlite3.Connection, evaluation_id: str) -> dict | None:
    """
    Return one ``metrics`` row by ``evaluation_id``, or ``None`` if absent.
    """
    cur = conn.execute("SELECT * FROM metrics WHERE evaluation_id = ?", (evaluation_id,))
    row = cur.fetchone()
    if row is None:
        return None
    columns = [d[0] for d in cur.description]
    return dict(zip(columns, row, strict=False))
