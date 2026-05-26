"""
ar-db-handler — SQLite database layer for the annual report pipeline.

This package owns ``filings.db`` (scrapers write, evaluator reads) and
``metrics.db`` (evaluator writes). It is a pure data-access module — it has
no knowledge of EDGAR, scraping logic, or evaluation logic.

Public API (everything below is also importable straight from
``ar_db_handler``):

* Database init:        ``init_filings_db``, ``init_metrics_db``
* ID generation:        ``make_file_id``, ``make_run_id``, ``EXTENSION_MAP``
* Filings write API:    ``upsert_run``, ``update_run_finished``,
                        ``upsert_company``, ``upsert_file``,
                        ``sync_companies``
* Filings read API:     ``get_file``, ``get_scraped_files``,
                        ``get_scraped_pairs``, ``list_companies``
* Error recording:      ``record_error``, ``get_scraper_errors``,
                        ``ErrorRecord``, ``ERROR_*`` constants,
                        ``SYSTEM_SCRAPER_ID``
* Exceptions:           ``ArDbHandlerError`` (base), ``AlreadyScrapedError``,
                        ``MissingFiscalYearError``
* Metrics write API:    ``write_metric`` (stub)
* Dataclasses:          ``CompanyRecord``, ``RunRecord``, ``FileRecord``,
                        ``ScrapedPair``, ``SyncResult``
"""

from __future__ import annotations

__version__ = "0.2.1"

# --- Dataclasses + exceptions + error-type constants ----------------------
from ._models import (
    ERROR_ALREADY_SCRAPED,
    ERROR_CHECK_VIOLATION,
    ERROR_FK_VIOLATION,
    ERROR_MISSING_FISCAL_YEAR,
    ERROR_SNAPSHOT_SCHEMA_DRIFT,
    ERROR_SYNC_NO_PERIOD,
    ERROR_UNKNOWN_FILE_TYPE,
    SYSTEM_SCRAPER_ID,
    AlreadyScrapedError,
    ArDbHandlerError,
    CompanyRecord,
    ErrorRecord,
    FileRecord,
    MissingFiscalYearError,
    RunRecord,
    ScrapedPair,
    SyncResult,
)

# --- Database init + filings write/error API ------------------------------
from .filings import (
    get_scraper_errors,
    init_filings_db,
    record_error,
    sync_companies,
    update_run_finished,
    upsert_company,
    upsert_file,
    upsert_run,
)

# --- ID generation --------------------------------------------------------
from .ids import EXTENSION_MAP, make_file_id, make_run_id
from .metrics import init_metrics_db, write_metric

# --- Read helpers ---------------------------------------------------------
from .queries import get_file, get_metric, get_scraped_files, get_scraped_pairs, list_companies

__all__ = [
    "__version__",
    # Database init
    "init_filings_db",
    "init_metrics_db",
    # ID generation
    "make_file_id",
    "make_run_id",
    "EXTENSION_MAP",
    # Filings write API
    "upsert_run",
    "update_run_finished",
    "upsert_company",
    "upsert_file",
    "sync_companies",
    # Filings read API
    "get_file",
    "get_scraped_files",
    "get_scraped_pairs",
    "list_companies",
    # Error recording
    "record_error",
    "get_scraper_errors",
    "ErrorRecord",
    "SYSTEM_SCRAPER_ID",
    "ERROR_UNKNOWN_FILE_TYPE",
    "ERROR_MISSING_FISCAL_YEAR",
    "ERROR_ALREADY_SCRAPED",
    "ERROR_FK_VIOLATION",
    "ERROR_CHECK_VIOLATION",
    "ERROR_SNAPSHOT_SCHEMA_DRIFT",
    "ERROR_SYNC_NO_PERIOD",
    # Exceptions
    "ArDbHandlerError",
    "AlreadyScrapedError",
    "MissingFiscalYearError",
    # Metrics API (stubs)
    "write_metric",
    "get_metric",
    # Dataclasses
    "CompanyRecord",
    "RunRecord",
    "FileRecord",
    "ScrapedPair",
    "SyncResult",
]
