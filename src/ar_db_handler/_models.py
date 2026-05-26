"""
Dataclasses and custom exceptions shared across the package.

Kept in one module so both ``filings`` and ``queries`` can import them
without creating an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ArDbHandlerError(Exception):
    """Base class so callers can ``except ArDbHandlerError:`` to catch all."""


class AlreadyScrapedError(ArDbHandlerError):
    """
    Raised by ``upsert_file`` when a row with ``status = 'SUCCESS'`` already
    exists for the natural key and ``force=False``.

    The scraper should have called ``get_scraped_files()`` to build a
    skip-set before attempting downloads; this exception is a secondary
    guard, not the primary control flow.

    Also recorded to ``scraper_errors`` (``error_type='ALREADY_SCRAPED'``)
    before being raised — see ``upsert_file`` docs.
    """


class MissingFiscalYearError(ArDbHandlerError):
    """
    Raised by ``upsert_file`` when ``status='SUCCESS'`` but
    ``fiscal_year is None``.

    Every regulator we target exposes the period-end on the filing
    metadata (EDGAR ``reportDate``, EDINET ``periodEnd``, ...), so a
    successful scrape with no derivable year indicates a scraper bug,
    not a data limitation. The DB-level CHECK constraint enforces the
    same invariant — this Python-side check fails earlier with a clearer
    message.

    Also recorded to ``scraper_errors`` (``error_type='MISSING_FISCAL_YEAR'``)
    before being raised.
    """


# ---------------------------------------------------------------------------
# Error-type constants
#
# Centralised so callers can ``except ardb.AlreadyScrapedError`` for the
# Python side AND ``WHERE error_type = ardb.ERROR_ALREADY_SCRAPED`` for the
# DB side, with no spelling drift between them.
# ---------------------------------------------------------------------------

ERROR_UNKNOWN_FILE_TYPE = "UNKNOWN_FILE_TYPE"
ERROR_MISSING_FISCAL_YEAR = "MISSING_FISCAL_YEAR"
ERROR_ALREADY_SCRAPED = "ALREADY_SCRAPED"
ERROR_FK_VIOLATION = "FK_VIOLATION"
ERROR_CHECK_VIOLATION = "CHECK_VIOLATION"
ERROR_SNAPSHOT_SCHEMA_DRIFT = "SNAPSHOT_SCHEMA_DRIFT"
ERROR_SYNC_NO_PERIOD = "SYNC_NO_PERIOD"

# Sentinel scraper_id used when the error didn't originate from a scraper run
# (e.g. sync_companies failures, ad-hoc maintenance scripts).
SYSTEM_SCRAPER_ID = "SYSTEM"


# ---------------------------------------------------------------------------
# Records — match the on-disk schema column-for-column
# ---------------------------------------------------------------------------


@dataclass
class CompanyRecord:
    """Row from the ``companies`` table."""

    company_id: int
    fs_ticker: str
    country_code: str
    country: str
    country_id: str | None
    file_name: str
    coverage_status: str
    start_year_force: int = 2008
    is_in_company_info: int = 1
    last_synced_at: str | None = None


@dataclass
class RunRecord:
    """Row from ``scraper_runs``, inserted once at run start (status='RUNNING')."""

    scraper_id: str  # from make_run_id()
    country_code: str
    workers_count: int  # default 3, set by the caller
    source_file: str | None
    log_path: str | None
    version: str | None
    started_at: str
    status: str  # RUNNING | SUCCESS | FAILED
    metadata: str | None = None  # raw JSON string


@dataclass
class FileRecord:
    """
    Row from the ``files`` table.

    The following columns are derived automatically inside ``upsert_file()``
    and MUST NOT be set by the caller:

    * ``file_id``    — ``make_file_id(company_id, source_filing_id, file_type)``
    * ``extension``  — ``EXTENSION_MAP[file_type]``

    INVARIANT (enforced by ``upsert_file`` AND a CHECK constraint on the
    table): if ``status == 'SUCCESS'`` then ``fiscal_year`` MUST NOT be
    ``None``. The scraper derives ``fiscal_year`` from ``reporting_date``
    (always available from the source API). ``PENDING`` and ``FAILED``
    rows may have ``fiscal_year=None`` since they don't represent
    committed work.
    """

    company_id: int
    scraper_id: str
    status: str  # SUCCESS | FAILED | PENDING
    country_code: str
    file_type: str  # PDF | XBRL
    source_filing_id: str  # regulator-assigned ID — never derived
    form_type: str | None  # None → normalised to 'UNKNOWN' by upsert_file()
    fiscal_year: int | None  # MUST be set when status='SUCCESS'
    reporting_date: str | None  # the year-derivation source
    filing_date: str | None
    gcs_path: str | None
    url: str | None
    scraped_at: str | None
    error_message: str | None


@dataclass
class ErrorRecord:
    """
    Row from the ``scraper_errors`` table.

    Used by ``record_error()``. The helpers (``upsert_file``,
    ``sync_companies``) build this record internally before raising.
    """

    scraper_id: str  # run UUID or SYSTEM_SCRAPER_ID
    error_type: str  # one of the ERROR_* constants, or a caller-defined string
    error_message: str
    company_id: int | None = None
    source_filing_id: str | None = None
    file_type: str | None = None
    payload: str | None = None  # caller-serialised JSON
    recorded_at: str | None = None  # filled in by record_error() if None


@dataclass
class ScrapedPair:
    """
    A matched (PDF, XBRL) pair for the same ``(company_id, fiscal_year)``.

    Returned by ``get_scraped_pairs()``. Multiple form-type combinations may
    coexist for the same ``(company_id, fiscal_year)`` (e.g. 10-K + 10-KA) —
    the caller applies its own priority logic.
    """

    file_id_pdf: str
    file_id_xbrl: str
    company_id: int
    fiscal_year: int
    pdf_gcs_path: str
    xbrl_gcs_path: str
    pdf_form_type: str
    xbrl_form_type: str


@dataclass
class SyncResult:
    """Returned by ``sync_companies()``."""

    period: str
    upserted: int
    delisted: int
    country_code: str | None
