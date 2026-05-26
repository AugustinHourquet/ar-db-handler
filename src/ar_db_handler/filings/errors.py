"""
Error-recording helper.

Every helper in ``ar_db_handler.filings`` that raises an exception ALSO
records the failure to ``scraper_errors`` first, via ``record_error()``.
The scraper can additionally call ``record_error()`` directly for any
arbitrary download/parse failure that didn't go through one of the
helpers.

Design note: the recording path itself MUST NOT raise on edge cases
(unknown ``scraper_id``, missing tables, etc.) — the whole point is
to be a durable audit trail. If recording somehow fails, we swallow
the secondary exception and log a warning rather than masking the
original problem the caller is trying to report.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from .._models import SYSTEM_SCRAPER_ID, ErrorRecord

logger = logging.getLogger("ar_db_handler.errors")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def record_error(conn: sqlite3.Connection, record: ErrorRecord) -> int | None:
    """
    Insert a row into ``scraper_errors``.

    Best-effort: a failure during recording is logged at WARNING level
    and silently swallowed. Callers should never have to wrap this in
    try/except themselves — they're already in an exception handler when
    they call it, and a second exception there would mask the first.

    Returns:
        The new ``error_id``, or ``None`` if the recording itself failed.
    """
    try:
        cur = conn.execute(
            """
            INSERT INTO scraper_errors (
                scraper_id, error_type, error_message,
                company_id, source_filing_id, file_type,
                payload, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.scraper_id or SYSTEM_SCRAPER_ID,
                record.error_type,
                record.error_message,
                record.company_id,
                record.source_filing_id,
                record.file_type,
                record.payload,
                record.recorded_at or _utc_now_iso(),
            ),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.Error as exc:  # pragma: no cover — best-effort path
        # Don't re-raise: the caller is mid-exception-handling and the
        # original error is what matters. Just log so the failure-to-log
        # is itself discoverable.
        logger.warning(
            "Failed to record scraper_errors row " "(error_type=%s, scraper_id=%s, message=%r): %s",
            record.error_type,
            record.scraper_id,
            record.error_message,
            exc,
        )
        return None


def get_scraper_errors(
    conn: sqlite3.Connection,
    scraper_id: str | None = None,
    error_type: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Return rows from ``scraper_errors``, ordered newest-first.

    Args:
        scraper_id: If set, restrict to errors from this run. Pass
                    ``SYSTEM_SCRAPER_ID`` to see system-level errors
                    (sync failures, etc.).
        error_type: If set, restrict to one error category — use the
                    ``ERROR_*`` constants from ``ar_db_handler``.
        limit:      Optional row cap.

    Returns:
        List of dicts (one per row). Empty list if nothing matches.
    """
    where: list[str] = []
    params: list = []
    if scraper_id is not None:
        where.append("scraper_id = ?")
        params.append(scraper_id)
    if error_type is not None:
        where.append("error_type = ?")
        params.append(error_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"SELECT * FROM scraper_errors {where_sql} " f"ORDER BY error_id DESC"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    cur = conn.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]
