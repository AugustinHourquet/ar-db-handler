"""Pytest fixtures shared across test modules."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from ar_db_handler import (
    CompanyRecord,
    FileRecord,
    RunRecord,
    init_filings_db,
    init_metrics_db,
    make_run_id,
    upsert_company,
    upsert_run,
)


@pytest.fixture
def filings_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A fresh filings.db on disk for one test."""
    conn = init_filings_db(tmp_path / "filings.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def metrics_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A fresh metrics.db on disk for one test."""
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seeded_db(filings_db: sqlite3.Connection) -> tuple[sqlite3.Connection, str, int]:
    """
    A filings.db pre-loaded with one company and one (RUNNING) scraper_run.

    Returns the connection plus the IDs the upsert helpers need so each test
    isn't writing the same boilerplate.
    """
    company_id = 100
    upsert_company(
        filings_db,
        CompanyRecord(
            company_id=company_id,
            fs_ticker="AAPL",
            country_code="US",
            country="United States",
            country_id="US",
            file_name="aapl",
            coverage_status="LAFA",
            start_year_force=2008,
        ),
    )

    scraper_id = make_run_id()
    upsert_run(
        filings_db,
        RunRecord(
            scraper_id=scraper_id,
            country_code="US",
            workers_count=3,
            source_file="scripts/scrape_us.py",
            log_path="/tmp/scrape_us.log",
            version="1.0.0",
            started_at="2026-05-22T10:00:00+00:00",
            status="RUNNING",
            metadata=None,
        ),
    )
    return filings_db, scraper_id, company_id


def make_file_record(
    *,
    company_id: int,
    scraper_id: str,
    source_filing_id: str,
    file_type: str = "PDF",
    status: str = "SUCCESS",
    form_type: str | None = "10-K",
    fiscal_year: int | None = 2024,
    gcs_path: str | None = "gs://bucket/path/file.pdf",
    error_message: str | None = None,
) -> FileRecord:
    """Convenience builder so test assertions stay short and intentional."""
    return FileRecord(
        company_id=company_id,
        scraper_id=scraper_id,
        status=status,
        country_code="US",
        file_type=file_type,
        source_filing_id=source_filing_id,
        form_type=form_type,
        fiscal_year=fiscal_year,
        reporting_date="2024-09-28",
        filing_date="2024-11-01",
        gcs_path=gcs_path,
        url="https://example.com/filing",
        scraped_at="2026-05-22T10:01:00+00:00",
        error_message=error_message,
    )
