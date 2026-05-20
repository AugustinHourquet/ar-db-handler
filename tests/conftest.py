"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from ar_db_handler import (
    CompanyRecord,
    FilingRecord,
    RunRecord,
    init_filings_db,
    init_metrics_db,
    upsert_company,
    upsert_filing,
    upsert_run,
)


@pytest.fixture
def filings_db(tmp_path: Path):
    """Yield an open, initialised connection to a fresh filings.db."""
    conn = init_filings_db(tmp_path / "filings.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def metrics_db(tmp_path: Path):
    """Yield an open, initialised connection to a fresh metrics.db."""
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seeded_filings_db(filings_db):
    """A filings.db pre-populated with one run, one company, one filing.

    Useful for filing_file tests that need referential parents to exist.
    """
    upsert_run(
        filings_db,
        RunRecord(
            run_id="run-1",
            parent_run_id=None,
            country="US",
            started_at="2026-01-01T00:00:00",
            finished_at=None,
            status="RUNNING",
            config='{"foo": "bar"}',
            worker_count=2,
        ),
    )
    upsert_company(
        filings_db,
        CompanyRecord(
            company_id="C001",
            name="Acme Corp",
            ticker="ACME",
            exchange="NASDAQ",
            country="US",
            updated_at="2026-01-01T00:00:00",
        ),
    )
    upsert_filing(
        filings_db,
        FilingRecord(
            filing_id="f-1",
            company_id="C001",
            fiscal_year=2024,
            filing_date="2025-02-15",
            reporting_date="2024-12-31",
            reporting_period="FY",
        ),
    )
    return filings_db
