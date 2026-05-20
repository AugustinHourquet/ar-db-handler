"""Query tests for filings.db read helpers."""

from __future__ import annotations

import pytest

from ar_db_handler import (
    CompanyRecord,
    FilingFileRecord,
    FilingRecord,
    RunRecord,
    get_filing,
    get_scraped_pairs,
    list_companies,
    upsert_company,
    upsert_filing,
    upsert_filing_file,
    upsert_run,
)


def _setup_two_companies_two_years(conn):
    upsert_run(
        conn,
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
    upsert_company(conn, CompanyRecord("C001", "Acme", None, None, "US", None))
    upsert_company(conn, CompanyRecord("C002", "Beta", None, None, "US", None))

    upsert_filing(conn, FilingRecord("f-001-2023", "C001", 2023, None, None, None))
    upsert_filing(conn, FilingRecord("f-001-2024", "C001", 2024, None, None, None))
    upsert_filing(conn, FilingRecord("f-002-2024", "C002", 2024, None, None, None))


def _ff(
    *,
    file_id: str,
    filing_id: str,
    file_type: str,
    scrape_status: str,
    form_type: str | None = "10-K",
    gcs_path: str | None = None,
):
    return FilingFileRecord(
        file_id=file_id,
        filing_id=filing_id,
        run_id="run-1",
        worker_id=1,
        file_type=file_type,
        form_type=form_type,
        gcs_path=gcs_path,
        url=None,
        scrape_status=scrape_status,
        scraped_at="2026-01-02" if scrape_status == "SCRAPED" else None,
    )


# ---------------------------------------------------------------------------
# get_filing
# ---------------------------------------------------------------------------


def test_get_filing_by_id(seeded_filings_db):
    rec = get_filing(seeded_filings_db, filing_id="f-1")
    assert rec is not None
    assert rec.company_id == "C001"
    assert rec.fiscal_year == 2024


def test_get_filing_by_natural_key(seeded_filings_db):
    rec = get_filing(seeded_filings_db, company_id="C001", fiscal_year=2024)
    assert rec is not None
    assert rec.filing_id == "f-1"


def test_get_filing_missing_returns_none(seeded_filings_db):
    assert get_filing(seeded_filings_db, filing_id="nope") is None


def test_get_filing_requires_some_key(seeded_filings_db):
    with pytest.raises(ValueError):
        get_filing(seeded_filings_db)


# ---------------------------------------------------------------------------
# list_companies
# ---------------------------------------------------------------------------


def test_list_companies(filings_db):
    upsert_company(filings_db, CompanyRecord("C002", "Beta", None, None, "US", None))
    upsert_company(filings_db, CompanyRecord("C001", "Acme", None, None, "US", None))
    companies = list_companies(filings_db)
    assert [c.company_id for c in companies] == ["C001", "C002"]


# ---------------------------------------------------------------------------
# get_scraped_pairs
# ---------------------------------------------------------------------------


def test_get_scraped_pairs_only_returns_full_pairs(filings_db):
    """A filing with only one of PDF/XBRL scraped must NOT appear."""
    _setup_two_companies_two_years(filings_db)

    # C001/2023 — both SCRAPED → should appear
    upsert_filing_file(
        filings_db,
        _ff(
            file_id="pdf-001-2023",
            filing_id="f-001-2023",
            file_type="PDF",
            scrape_status="SCRAPED",
            gcs_path="gs://b/p1.pdf",
        ),
    )
    upsert_filing_file(
        filings_db,
        _ff(
            file_id="xbrl-001-2023",
            filing_id="f-001-2023",
            file_type="XBRL",
            scrape_status="SCRAPED",
            gcs_path="gs://b/x1.zip",
        ),
    )

    # C001/2024 — PDF SCRAPED, XBRL PENDING → must NOT appear
    upsert_filing_file(
        filings_db,
        _ff(
            file_id="pdf-001-2024",
            filing_id="f-001-2024",
            file_type="PDF",
            scrape_status="SCRAPED",
            gcs_path="gs://b/p2.pdf",
        ),
    )
    upsert_filing_file(
        filings_db,
        _ff(
            file_id="xbrl-001-2024",
            filing_id="f-001-2024",
            file_type="XBRL",
            scrape_status="PENDING",
        ),
    )

    # C002/2024 — XBRL SCRAPED, PDF FAILED → must NOT appear
    upsert_filing_file(
        filings_db,
        _ff(
            file_id="pdf-002-2024",
            filing_id="f-002-2024",
            file_type="PDF",
            scrape_status="FAILED",
        ),
    )
    upsert_filing_file(
        filings_db,
        _ff(
            file_id="xbrl-002-2024",
            filing_id="f-002-2024",
            file_type="XBRL",
            scrape_status="SCRAPED",
            gcs_path="gs://b/x3.zip",
        ),
    )

    pairs = get_scraped_pairs(filings_db)
    assert len(pairs) == 1
    p = pairs[0]
    assert p.filing_id == "f-001-2023"
    assert p.company_id == "C001"
    assert p.fiscal_year == 2023
    assert p.pdf_gcs_path == "gs://b/p1.pdf"
    assert p.xbrl_gcs_path == "gs://b/x1.zip"


def test_get_scraped_pairs_company_filter(filings_db):
    _setup_two_companies_two_years(filings_db)
    for fid in ["f-001-2023", "f-001-2024", "f-002-2024"]:
        upsert_filing_file(
            filings_db,
            _ff(
                file_id=f"pdf-{fid}",
                filing_id=fid,
                file_type="PDF",
                scrape_status="SCRAPED",
                gcs_path=f"gs://b/{fid}.pdf",
            ),
        )
        upsert_filing_file(
            filings_db,
            _ff(
                file_id=f"xbrl-{fid}",
                filing_id=fid,
                file_type="XBRL",
                scrape_status="SCRAPED",
                gcs_path=f"gs://b/{fid}.zip",
            ),
        )

    pairs = get_scraped_pairs(filings_db, company_id="C001")
    assert {p.company_id for p in pairs} == {"C001"}
    assert len(pairs) == 2


def test_get_scraped_pairs_year_filter(filings_db):
    _setup_two_companies_two_years(filings_db)
    for fid in ["f-001-2023", "f-001-2024", "f-002-2024"]:
        upsert_filing_file(
            filings_db,
            _ff(
                file_id=f"pdf-{fid}",
                filing_id=fid,
                file_type="PDF",
                scrape_status="SCRAPED",
                gcs_path=f"gs://b/{fid}.pdf",
            ),
        )
        upsert_filing_file(
            filings_db,
            _ff(
                file_id=f"xbrl-{fid}",
                filing_id=fid,
                file_type="XBRL",
                scrape_status="SCRAPED",
                gcs_path=f"gs://b/{fid}.zip",
            ),
        )
    pairs = get_scraped_pairs(filings_db, fiscal_year=2024)
    assert {p.fiscal_year for p in pairs} == {2024}
    assert len(pairs) == 2


def test_get_scraped_pairs_both_filters(filings_db):
    _setup_two_companies_two_years(filings_db)
    for fid in ["f-001-2023", "f-001-2024", "f-002-2024"]:
        upsert_filing_file(
            filings_db,
            _ff(
                file_id=f"pdf-{fid}",
                filing_id=fid,
                file_type="PDF",
                scrape_status="SCRAPED",
                gcs_path=f"gs://b/{fid}.pdf",
            ),
        )
        upsert_filing_file(
            filings_db,
            _ff(
                file_id=f"xbrl-{fid}",
                filing_id=fid,
                file_type="XBRL",
                scrape_status="SCRAPED",
                gcs_path=f"gs://b/{fid}.zip",
            ),
        )
    pairs = get_scraped_pairs(filings_db, company_id="C001", fiscal_year=2024)
    assert len(pairs) == 1
    assert pairs[0].filing_id == "f-001-2024"


def test_get_scraped_pairs_empty(filings_db):
    assert get_scraped_pairs(filings_db) == []
