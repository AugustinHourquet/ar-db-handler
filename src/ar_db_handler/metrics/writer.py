"""
Write helpers for ``metrics.db``.

Currently a stub — the ``metrics`` table schema is not yet finalised. The
``write_metric()`` signature is intentionally permissive (``**columns``) so
new columns can be added in ``schema.sql`` without breaking callers that
were already passing keyword arguments.
"""

from __future__ import annotations

import sqlite3
import uuid


def write_metric(
    conn: sqlite3.Connection,
    file_id: str | None = None,
    evaluation_id: str | None = None,
    **columns: object,
) -> str:
    """
    Insert a row into the ``metrics`` table.

    Args:
        conn:          Open connection to ``metrics.db``.
        file_id:       Cross-DB reference to ``filings.db.files.file_id``.
                       Not enforced as a FK (SQLite can't enforce cross-DB
                       FKs and we don't want that coupling).
        evaluation_id: Optional explicit primary key. If omitted, a UUID4
                       is generated. Useful for tests that want
                       reproducible IDs.
        **columns:     Additional column=value pairs. Names must match
                       columns in ``schema.sql``. Unknown columns raise
                       ``sqlite3.OperationalError`` from SQLite directly —
                       we don't silently drop them.

    Returns:
        The ``evaluation_id`` of the inserted row.
    """
    eid = evaluation_id or str(uuid.uuid4())

    cols = ["evaluation_id", "file_id", *columns.keys()]
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    values: list[object] = [eid, file_id, *columns.values()]

    conn.execute(
        f"INSERT INTO metrics ({col_list}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return eid
