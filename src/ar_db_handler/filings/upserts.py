"""Write helpers for filings.db.

All functions take an open `sqlite3.Connection` as their first argument
and do not own it — the caller is responsible for transactions, commits,
and closing.

These helpers do commit (each call is a single logical write), but they
operate within the connection passed in, so a caller that wants larger
transactional units can wrap several calls in a `with conn:` block.

Upsert semantics (enforced here in Python, not via SQL triggers):

* `upsert_run`, `upsert_worker`, `upsert_company`, `upsert_filing`
  use `INSERT OR IGNORE` — once written, the row is immutable from
  this helper's perspective.

* `upsert_filing_file` is the only non-trivial case:
    - if a SCRAPED row already exists for the same
      (filing_id, file_type, form_type) and `force=False`, raise
      `AlreadyScrapedError`;
    - otherwise `INSERT OR REPLACE`.

  When `force=True`, the SCRAPED check is bypassed and the row is
  always replaced. This is intended for re-scraping flows.
"""

from __future__ import annotations

import logging
import sqlite3

from ..exceptions import AlreadyScrapedError
from ..records import (
    CompanyRecord,
    FilingFileRecord,
    FilingRecord,
    RunRecord,
    WorkerRecord,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# scraper_runs
# ---------------------------------------------------------------------------


def upsert_run(conn: sqlite3.Connection, record: RunRecord) -> None:
    """Insert a parent run row (worker_id IS NULL).

    `INSERT OR IGNORE` on conflict with `run_id`. Existing rows are not
    overwritten — a run record, once created, is immutable through this
    helper.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO scraper_runs (
            run_id, parent_run_id, worker_id, country,
            started_at, finished_at, status,
            files_scraped, config, worker_count
        ) VALUES (?, ?, NULL, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            record.run_id,
            record.parent_run_id,
            record.country,
            record.started_at,
            record.finished_at,
            record.status,
            record.config,
            record.worker_count,
        ),
    )
    conn.commit()


def upsert_worker(conn: sqlite3.Connection, record: WorkerRecord) -> None:
    """Insert a worker row under an existing run.

    Worker rows have a non-NULL `worker_id` and NULL `country`/`config`.
    The parent run row must already exist (FK constraint on
    `parent_run_id` if set, and conceptually on `run_id` — note that the
    schema stores worker rows in the same table keyed by `run_id`, so
    the worker's `run_id` should be a *distinct* primary key from the
    parent's; the parent is referenced via `parent_run_id`).

    `INSERT OR IGNORE` on conflict with `run_id`.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO scraper_runs (
            run_id, parent_run_id, worker_id, country,
            started_at, finished_at, status,
            files_scraped, config, worker_count
        ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL)
        """,
        (
            record.run_id,
            record.parent_run_id,
            record.worker_id,
            record.started_at,
            record.finished_at,
            record.status,
            record.files_scraped,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------


def upsert_company(conn: sqlite3.Connection, record: CompanyRecord) -> None:
    """Insert a company row.

    `INSERT OR IGNORE` on conflict with `company_id`. To update company
    metadata, callers should delete + re-insert explicitly; this helper
    will not overwrite.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO companies (
            company_id, name, ticker, exchange, country, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            record.company_id,
            record.name,
            record.ticker,
            record.exchange,
            record.country,
            record.updated_at,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# filings
# ---------------------------------------------------------------------------


def upsert_filing(conn: sqlite3.Connection, record: FilingRecord) -> None:
    """Insert a filing row.

    `INSERT OR IGNORE` on conflict with `(company_id, fiscal_year)`.
    The filing event is immutable: an existing row is never overwritten.
    This is intentional — a company can have only one 10-K filing for a
    given fiscal year, and that filing's identifying metadata (filing
    date, reporting date) should not silently change.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO filings (
            filing_id, company_id, fiscal_year,
            filing_date, reporting_date, reporting_period
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            record.filing_id,
            record.company_id,
            record.fiscal_year,
            record.filing_date,
            record.reporting_date,
            record.reporting_period,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# filing_files
# ---------------------------------------------------------------------------


def upsert_filing_file(
    conn: sqlite3.Connection,
    record: FilingFileRecord,
    force: bool = False,
) -> None:
    """Upsert a filing_files row with status-aware semantics.

    Behaviour
    ---------
    Look up the existing row, if any, on
    `(filing_id, file_type, form_type)`:

    * No existing row → `INSERT OR REPLACE` (effectively INSERT).
    * Existing row, status != SCRAPED → `INSERT OR REPLACE`.
    * Existing row, status == SCRAPED, `force=False` → raise
      `AlreadyScrapedError`. The scraper is expected to have
      checked `get_filing_file()` before attempting the download.
    * Existing row, status == SCRAPED, `force=True` → `INSERT OR
      REPLACE`. Used for explicit re-scraping flows.

    Raises
    ------
    AlreadyScrapedError
        When the SCRAPED row conflict is hit and `force` is False.
    """
    if not force:
        existing = conn.execute(
            """
            SELECT scrape_status
            FROM filing_files
            WHERE filing_id = ?
              AND file_type = ?
              AND form_type IS ?
            """,
            (record.filing_id, record.file_type, record.form_type),
        ).fetchone()

        if existing is not None and existing["scrape_status"] == "SCRAPED":
            raise AlreadyScrapedError(
                f"filing_files row already SCRAPED for "
                f"filing_id={record.filing_id!r}, file_type={record.file_type!r}, "
                f"form_type={record.form_type!r}"
            )

    conn.execute(
        """
        INSERT OR REPLACE INTO filing_files (
            file_id, filing_id, run_id, worker_id,
            file_type, form_type, gcs_path, url,
            scrape_status, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.file_id,
            record.filing_id,
            record.run_id,
            record.worker_id,
            record.file_type,
            record.form_type,
            record.gcs_path,
            record.url,
            record.scrape_status,
            record.scraped_at,
        ),
    )
    conn.commit()
