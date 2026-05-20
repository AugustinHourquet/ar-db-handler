"""Upsert-rule tests for filings.db."""

from __future__ import annotations

import pytest

from ar_db_handler import (
    AlreadyScrapedError,
    CompanyRecord,
    FilingFileRecord,
    FilingRecord,
    RunRecord,
    WorkerRecord,
    get_filing,
    get_filing_file,
    upsert_company,
    upsert_filing,
    upsert_filing_file,
    upsert_run,
    upsert_worker,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ff(
    *,
    file_id: str = "ff-1",
    filing_id: str = "f-1",
    run_id: str = "run-1",
    worker_id: int | None = 1,
    file_type: str = "PDF",
    form_type: str | None = "10-K",
    gcs_path: str | None = "gs://b/p.pdf",
    url: str | None = "https://x",
    scrape_status: str = "PENDING",
    scraped_at: str | None = None,
) -> FilingFileRecord:
    return FilingFileRecord(
        file_id=file_id,
        filing_id=filing_id,
        run_id=run_id,
        worker_id=worker_id,
        file_type=file_type,
        form_type=form_type,
        gcs_path=gcs_path,
        url=url,
        scrape_status=scrape_status,
        scraped_at=scraped_at,
    )


# ---------------------------------------------------------------------------
# scraper_runs
# ---------------------------------------------------------------------------


def test_upsert_run_inserts_parent_row(filings_db):
    upsert_run(
        filings_db,
        RunRecord(
            run_id="run-1",
            parent_run_id=None,
            country="US",
            started_at="2026-01-01T00:00:00",
            finished_at=None,
            status="RUNNING",
            config='{"k": 1}',
            worker_count=2,
        ),
    )
    row = filings_db.execute("SELECT * FROM scraper_runs WHERE run_id='run-1'").fetchone()
    assert row["worker_id"] is None
    assert row["country"] == "US"
    assert row["status"] == "RUNNING"
    assert row["config"] == '{"k": 1}'
    assert row["worker_count"] == 2


def test_upsert_run_is_insert_or_ignore(filings_db):
    rec = RunRecord(
        run_id="run-1",
        parent_run_id=None,
        country="US",
        started_at="2026-01-01T00:00:00",
        finished_at=None,
        status="RUNNING",
        config=None,
        worker_count=1,
    )
    upsert_run(filings_db, rec)
    # Re-insert with different status — original row must survive.
    upsert_run(
        filings_db,
        RunRecord(
            run_id="run-1",
            parent_run_id=None,
            country="US",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T01:00:00",
            status="SUCCESS",
            config=None,
            worker_count=1,
        ),
    )
    row = filings_db.execute(
        "SELECT status, finished_at FROM scraper_runs WHERE run_id='run-1'"
    ).fetchone()
    assert row["status"] == "RUNNING"
    assert row["finished_at"] is None


def test_upsert_worker_inserts_worker_row(filings_db):
    upsert_run(
        filings_db,
        RunRecord(
            run_id="run-1",
            parent_run_id=None,
            country="US",
            started_at="2026-01-01T00:00:00",
            finished_at=None,
            status="RUNNING",
            config=None,
            worker_count=1,
        ),
    )
    upsert_worker(
        filings_db,
        WorkerRecord(
            run_id="run-1-w1",
            parent_run_id="run-1",
            worker_id=1,
            started_at="2026-01-01T00:00:00",
            finished_at=None,
            status="RUNNING",
            files_scraped=0,
        ),
    )
    row = filings_db.execute("SELECT * FROM scraper_runs WHERE run_id='run-1-w1'").fetchone()
    assert row["worker_id"] == 1
    assert row["country"] is None
    assert row["config"] is None
    assert row["parent_run_id"] == "run-1"


# ---------------------------------------------------------------------------
# companies / filings
# ---------------------------------------------------------------------------


def test_upsert_company_is_insert_or_ignore(filings_db):
    upsert_company(
        filings_db,
        CompanyRecord("C001", "Acme", "ACME", "NASDAQ", "US", "2026-01-01"),
    )
    upsert_company(
        filings_db,
        CompanyRecord("C001", "Other Name", "X", "Y", "FR", "2026-02-02"),
    )
    row = filings_db.execute(
        "SELECT name, ticker, country FROM companies WHERE company_id='C001'"
    ).fetchone()
    assert row["name"] == "Acme"
    assert row["ticker"] == "ACME"
    assert row["country"] == "US"


def test_upsert_filing_is_insert_or_ignore_on_natural_key(filings_db):
    upsert_company(
        filings_db,
        CompanyRecord("C001", "Acme", None, None, "US", None),
    )
    upsert_filing(
        filings_db,
        FilingRecord("f-1", "C001", 2024, "2025-02-15", "2024-12-31", "FY"),
    )
    # Second insert with same (company_id, fiscal_year), different filing_id:
    # must be ignored, original row preserved.
    upsert_filing(
        filings_db,
        FilingRecord("f-2", "C001", 2024, "2099-01-01", "2099-01-01", "OTHER"),
    )
    row = get_filing(filings_db, company_id="C001", fiscal_year=2024)
    assert row is not None
    assert row.filing_id == "f-1"
    assert row.filing_date == "2025-02-15"
    assert row.reporting_period == "FY"


# ---------------------------------------------------------------------------
# filing_files
# ---------------------------------------------------------------------------


def test_filing_file_insert_then_scrape(seeded_filings_db):
    """PENDING row → SCRAPED row: the second call replaces the first."""
    conn = seeded_filings_db
    upsert_filing_file(conn, _ff(scrape_status="PENDING", gcs_path=None))
    upsert_filing_file(
        conn,
        _ff(
            file_id="ff-1",
            scrape_status="SCRAPED",
            gcs_path="gs://b/p.pdf",
            scraped_at="2026-01-02T00:00:00",
        ),
    )
    row = get_filing_file(conn, "f-1", "PDF", "10-K")
    assert row is not None
    assert row.scrape_status == "SCRAPED"
    assert row.gcs_path == "gs://b/p.pdf"


def test_filing_file_scraped_then_blocked(seeded_filings_db):
    conn = seeded_filings_db
    upsert_filing_file(
        conn,
        _ff(scrape_status="SCRAPED", scraped_at="2026-01-02T00:00:00"),
    )
    with pytest.raises(AlreadyScrapedError):
        upsert_filing_file(
            conn,
            _ff(file_id="ff-2", scrape_status="SCRAPED"),
        )


def test_filing_file_force_overrides_scraped(seeded_filings_db):
    conn = seeded_filings_db
    upsert_filing_file(
        conn,
        _ff(
            scrape_status="SCRAPED",
            gcs_path="gs://b/first.pdf",
            scraped_at="2026-01-02T00:00:00",
        ),
    )
    upsert_filing_file(
        conn,
        _ff(
            file_id="ff-2",
            scrape_status="SCRAPED",
            gcs_path="gs://b/second.pdf",
            scraped_at="2026-02-02T00:00:00",
        ),
        force=True,
    )
    row = get_filing_file(conn, "f-1", "PDF", "10-K")
    assert row is not None
    assert row.file_id == "ff-2"
    assert row.gcs_path == "gs://b/second.pdf"


def test_filing_file_failed_overwritten_without_force(seeded_filings_db):
    conn = seeded_filings_db
    upsert_filing_file(conn, _ff(scrape_status="FAILED"))
    upsert_filing_file(
        conn,
        _ff(
            file_id="ff-2",
            scrape_status="SCRAPED",
            scraped_at="2026-01-02T00:00:00",
        ),
    )
    row = get_filing_file(conn, "f-1", "PDF", "10-K")
    assert row is not None
    assert row.scrape_status == "SCRAPED"
    assert row.file_id == "ff-2"


def test_filing_file_pending_overwritten_without_force(seeded_filings_db):
    conn = seeded_filings_db
    upsert_filing_file(conn, _ff(scrape_status="PENDING"))
    upsert_filing_file(
        conn,
        _ff(
            file_id="ff-2",
            scrape_status="PENDING",
            gcs_path="gs://b/p2.pdf",
        ),
    )
    row = get_filing_file(conn, "f-1", "PDF", "10-K")
    assert row is not None
    assert row.file_id == "ff-2"


def test_filing_file_form_type_null_handled(seeded_filings_db):
    """A NULL form_type must round-trip via the IS NULL lookup."""
    conn = seeded_filings_db
    upsert_filing_file(conn, _ff(file_type="XBRL", form_type=None))
    row = get_filing_file(conn, "f-1", "XBRL", None)
    assert row is not None
    assert row.form_type is None


def test_filing_file_distinct_form_types_coexist(seeded_filings_db):
    """Same filing_id + file_type but different form_type → two rows."""
    conn = seeded_filings_db
    upsert_filing_file(
        conn,
        _ff(file_id="ff-a", file_type="PDF", form_type="10-K"),
    )
    upsert_filing_file(
        conn,
        _ff(file_id="ff-b", file_type="PDF", form_type="10-K/A"),
    )
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM filing_files WHERE filing_id='f-1' AND file_type='PDF'"
    ).fetchone()["n"]
    assert count == 2
