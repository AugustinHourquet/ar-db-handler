"""
Write helpers for ``filings.db``.

These functions enforce the project's upsert rules in Python rather than
via SQL triggers — easier to test, easier to reason about, and avoids
trigger compatibility quirks across SQLite versions.

Error-handling contract
-----------------------
Every helper here that rejects a row both **raises** an exception AND
**records** the rejection to ``scraper_errors`` first. This means:

* The caller can ``except`` to handle the failure inline.
* The error is durable even if the caller swallows the exception.
* The recording uses the same connection — same transaction, no chance
  of a partial state where the SQL row went in but the error row didn't.

The five categories recorded:

================================  ========================================
Trigger                           ``error_type``
================================  ========================================
unknown ``file_type``             ``ERROR_UNKNOWN_FILE_TYPE``
SUCCESS row, ``fiscal_year=None`` ``ERROR_MISSING_FISCAL_YEAR``
SUCCESS row exists, ``force=F``   ``ERROR_ALREADY_SCRAPED``
bogus ``company_id``/scraper_id   ``ERROR_FK_VIOLATION``
other CHECK constraint failure    ``ERROR_CHECK_VIOLATION``
================================  ========================================
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone

from .._models import (
    ERROR_ALREADY_SCRAPED,
    ERROR_CHECK_VIOLATION,
    ERROR_FK_VIOLATION,
    ERROR_MISSING_FISCAL_YEAR,
    ERROR_UNKNOWN_FILE_TYPE,
    AlreadyScrapedError,
    CompanyRecord,
    ErrorRecord,
    FileRecord,
    MissingFiscalYearError,
    RunRecord,
)
from ..ids import make_file_id, resolve_extension
from .errors import record_error

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise_form_type(raw: str | None) -> str:
    """
    Map ``None`` / ``""`` / whitespace to ``"UNKNOWN"``.

    Centralised here so ``upsert_file()`` is the single point where the
    normalisation happens — callers never need to handle it themselves.
    """
    if raw is None:
        return "UNKNOWN"
    stripped = raw.strip()
    return stripped if stripped else "UNKNOWN"


def _utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _record_for_file(record: FileRecord, error_type: str, message: str) -> ErrorRecord:
    """Build an ErrorRecord pre-populated from a FileRecord's context."""
    # Strip the bulkier fields out of the payload — the audit table doesn't
    # need scraped_at / url / gcs_path for diagnostics, and keeping the
    # payload small keeps the table manageable across many failures.
    payload_dict = asdict(record)
    return ErrorRecord(
        scraper_id=record.scraper_id,
        error_type=error_type,
        error_message=message,
        company_id=record.company_id,
        source_filing_id=record.source_filing_id,
        file_type=record.file_type,
        payload=json.dumps(payload_dict, default=str),
    )


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------


def upsert_file(
    conn: sqlite3.Connection,
    record: FileRecord,
    force: bool = False,
) -> None:
    """
    Insert or replace a row in ``files``.

    Derivation done here (callers do not set these):
      * ``file_id``  — ``make_file_id(company_id, source_filing_id, file_type)``
      * ``extension`` — ``EXTENSION_MAP[file_type]`` (raises ``ValueError``
        on unknown ``file_type``)
      * ``form_type`` — ``None`` / ``""`` normalised to ``"UNKNOWN"``

    Invariant enforced (Python-side check + DB CHECK constraint):
      * if ``status='SUCCESS'`` then ``fiscal_year`` MUST NOT be ``None``

    Upsert rules:
      * No existing row matching the natural key            → ``INSERT``
      * Existing row, ``status='SUCCESS'``, ``force=False`` → raise
        ``AlreadyScrapedError``
      * Existing row, ``status='PENDING'`` or ``'FAILED'``  → ``INSERT OR REPLACE``
      * Any existing row with ``force=True``                → ``INSERT OR REPLACE``

    Every rejection path records to ``scraper_errors`` before raising.

    Raises:
        ValueError:              when ``file_type`` is not in ``EXTENSION_MAP``.
        MissingFiscalYearError:  when ``status='SUCCESS'`` and ``fiscal_year is None``.
        AlreadyScrapedError:     when blocked by the SUCCESS+force=False rule.
        sqlite3.IntegrityError:  FK or CHECK violations — re-raised after
                                 being recorded.
    """
    # ---- Pre-flight 1: file_type → extension. Cheapest check; do it first. ----
    try:
        extension = resolve_extension(record.file_type)
    except ValueError as exc:
        record_error(
            conn,
            _record_for_file(record, ERROR_UNKNOWN_FILE_TYPE, str(exc)),
        )
        raise

    # ---- Pre-flight 2: SUCCESS → fiscal_year MUST be set. ----
    if record.status == "SUCCESS" and record.fiscal_year is None:
        message = (
            f"upsert_file: status='SUCCESS' requires fiscal_year != None. "
            f"company_id={record.company_id}, "
            f"source_filing_id={record.source_filing_id!r}, "
            f"file_type={record.file_type!r}. "
            f"Derive fiscal_year from reporting_date in the scraper before calling."
        )
        record_error(
            conn,
            _record_for_file(record, ERROR_MISSING_FISCAL_YEAR, message),
        )
        raise MissingFiscalYearError(message)

    form_type = _normalise_form_type(record.form_type)
    file_id = make_file_id(record.company_id, record.source_filing_id, record.file_type)

    # ---- Pre-flight 3: SUCCESS-guard (only when force=False) ----
    if not force:
        existing = conn.execute(
            """
            SELECT status FROM files
            WHERE company_id = ?
              AND source_filing_id = ?
              AND file_type = ?
            """,
            (record.company_id, record.source_filing_id, record.file_type),
        ).fetchone()

        if existing is not None and existing[0] == "SUCCESS":
            message = (
                f"File already scraped (status=SUCCESS) for "
                f"company_id={record.company_id}, "
                f"source_filing_id={record.source_filing_id!r}, "
                f"file_type={record.file_type!r}. "
                f"Pass force=True to overwrite."
            )
            record_error(
                conn,
                _record_for_file(record, ERROR_ALREADY_SCRAPED, message),
            )
            raise AlreadyScrapedError(message)

    # ---- INSERT OR REPLACE — IntegrityError → record + re-raise ----
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO files (
                file_id, company_id, scraper_id, status,
                country_code, file_type, extension, form_type,
                source_filing_id, fiscal_year,
                reporting_date, filing_date, gcs_path, url,
                scraped_at, error_message
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                file_id,
                record.company_id,
                record.scraper_id,
                record.status,
                record.country_code,
                record.file_type,
                extension,
                form_type,
                record.source_filing_id,
                record.fiscal_year,
                record.reporting_date,
                record.filing_date,
                record.gcs_path,
                record.url,
                record.scraped_at,
                record.error_message,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        # Heuristic: FK errors mention "FOREIGN KEY", CHECK errors mention
        # "CHECK constraint". Distinguishing them in the audit log helps
        # the caller spot upstream data drift vs. invariant bugs.
        message = str(exc)
        if "FOREIGN KEY" in message.upper():
            err_type = ERROR_FK_VIOLATION
        else:
            err_type = ERROR_CHECK_VIOLATION
        record_error(conn, _record_for_file(record, err_type, message))
        raise


# ---------------------------------------------------------------------------
# scraper_runs
# ---------------------------------------------------------------------------


def upsert_run(conn: sqlite3.Connection, record: RunRecord) -> None:
    """
    ``INSERT OR IGNORE`` a row in ``scraper_runs``.

    Called once at the start of a scraper run with ``status = 'RUNNING'``.
    The IGNORE behaviour means re-issuing the same ``scraper_id`` (which
    shouldn't happen — UUID4) silently does nothing rather than failing the
    scraper at startup.

    Use ``update_run_finished()`` to mark the run complete.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO scraper_runs (
            scraper_id, country_code, workers_count, source_file,
            log_path, version, started_at, status, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.scraper_id,
            record.country_code,
            record.workers_count,
            record.source_file,
            record.log_path,
            record.version,
            record.started_at,
            record.status,
            record.metadata,
        ),
    )
    conn.commit()


def update_run_finished(
    conn: sqlite3.Connection,
    scraper_id: str,
    status: str,
    finished_at: str,
    elapsed_time: float,
    scraped_files: int,
    xbrl_count: int,
    pdf_count: int,
    fail_count: int,
) -> None:
    """
    Close out a ``scraper_runs`` row at run end.

    Updates ``finished_at``, ``elapsed_time``, ``status``, and the four
    count columns. ``status`` should be ``'SUCCESS'`` or ``'FAILED'`` —
    leaving a row at ``'RUNNING'`` after the process exits is a bug.
    """
    conn.execute(
        """
        UPDATE scraper_runs
        SET status        = ?,
            finished_at   = ?,
            elapsed_time  = ?,
            scraped_files = ?,
            xbrl_count    = ?,
            pdf_count     = ?,
            fail_count    = ?
        WHERE scraper_id = ?
        """,
        (
            status,
            finished_at,
            elapsed_time,
            scraped_files,
            xbrl_count,
            pdf_count,
            fail_count,
            scraper_id,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------


def upsert_company(conn: sqlite3.Connection, record: CompanyRecord) -> None:
    """
    ``INSERT OR REPLACE`` a row in ``companies``.

    Always overrides ``is_in_company_info`` to ``1`` and ``last_synced_at``
    to the current UTC datetime — this is the success path of
    ``sync_companies()``. Companies that are no longer in the snapshot are
    deactivated in a separate sweep (``is_in_company_info = 0``) before
    this function is called.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO companies (
            company_id, fs_ticker, country_code, country, country_id,
            file_name, coverage_status, start_year_force,
            is_in_company_info, last_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.company_id,
            record.fs_ticker,
            record.country_code,
            record.country,
            record.country_id,
            record.file_name,
            record.coverage_status,
            record.start_year_force,
            1,  # always active on successful upsert
            _utc_now_iso(),
        ),
    )
    conn.commit()
