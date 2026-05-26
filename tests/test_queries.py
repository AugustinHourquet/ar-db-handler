"""Tests for the queries.filings read helpers."""

from __future__ import annotations

from ar_db_handler import (
    CompanyRecord,
    RunRecord,
    get_file,
    get_scraped_files,
    get_scraped_pairs,
    list_companies,
    make_file_id,
    make_run_id,
    upsert_company,
    upsert_file,
    upsert_run,
)
from tests.conftest import make_file_record

# ---------------------------------------------------------------------------
# get_file
# ---------------------------------------------------------------------------


class TestGetFile:
    def test_returns_dict_for_existing(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
            ),
        )
        fid = make_file_id(company_id, "acc-1", "PDF")
        row = get_file(conn, fid)
        assert row is not None
        assert row["file_id"] == fid
        assert row["source_filing_id"] == "acc-1"

    def test_returns_none_for_missing(self, seeded_db):
        conn, _, _ = seeded_db
        assert get_file(conn, "deadbeef00000000") is None


# ---------------------------------------------------------------------------
# get_scraped_files
# ---------------------------------------------------------------------------


class TestGetScrapedFiles:
    def _seed_multi_country(self, conn, scraper_id_us, scraper_id_jp):
        """One US row + one JP row + one FAILED US row."""
        upsert_company(
            conn,
            CompanyRecord(
                company_id=200,
                fs_ticker="TYO",
                country_code="JP",
                country="Japan",
                country_id="JP",
                file_name="tyo",
                coverage_status="LAFA",
                start_year_force=2008,
            ),
        )
        # US: SUCCESS
        upsert_file(
            conn,
            make_file_record(
                company_id=100,
                scraper_id=scraper_id_us,
                source_filing_id="acc-us-1",
                file_type="PDF",
                status="SUCCESS",
            ),
        )
        # US: FAILED — must NOT appear in skip-set
        upsert_file(
            conn,
            make_file_record(
                company_id=100,
                scraper_id=scraper_id_us,
                source_filing_id="acc-us-2",
                file_type="PDF",
                status="FAILED",
                gcs_path=None,
                error_message="404",
            ),
        )
        # JP: SUCCESS
        rec = make_file_record(
            company_id=200,
            scraper_id=scraper_id_jp,
            source_filing_id="S100ABCD",
            file_type="XBRL",
            status="SUCCESS",
        )
        rec.country_code = "JP"  # override
        upsert_file(conn, rec)

    def test_returns_only_success_rows(self, seeded_db):
        conn, scraper_id, _ = seeded_db
        # Add a second scraper for JP
        scraper_jp = make_run_id()
        upsert_run(
            conn,
            RunRecord(
                scraper_id=scraper_jp,
                country_code="JP",
                workers_count=3,
                source_file=None,
                log_path=None,
                version=None,
                started_at="2026-05-22T10:00:00+00:00",
                status="RUNNING",
                metadata=None,
            ),
        )
        self._seed_multi_country(conn, scraper_id, scraper_jp)

        all_files = get_scraped_files(conn)
        # FAILED row is excluded, SUCCESS rows kept → 2 entries
        assert len(all_files) == 2

    def test_returns_tuples_of_three(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
            ),
        )
        out = get_scraped_files(conn)
        assert len(out) == 1
        tup = next(iter(out))
        assert isinstance(tup, tuple)
        assert len(tup) == 3
        cid, sfid, ftype = tup
        assert (cid, sfid, ftype) == (company_id, "acc-1", "PDF")

    def test_fiscal_year_is_not_in_tuple(self, seeded_db):
        """Even when fiscal_year is set, it must not leak into the skip-set tuple."""
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                fiscal_year=2024,
            ),
        )
        tup = next(iter(get_scraped_files(conn)))
        # If fiscal_year had leaked in, tuple length would be 4.
        assert len(tup) == 3
        # And the year value should not be among the tuple elements.
        assert 2024 not in tup

    def test_country_code_filter(self, seeded_db):
        conn, scraper_id, _ = seeded_db
        scraper_jp = make_run_id()
        upsert_run(
            conn,
            RunRecord(
                scraper_id=scraper_jp,
                country_code="JP",
                workers_count=3,
                source_file=None,
                log_path=None,
                version=None,
                started_at="2026-05-22T10:00:00+00:00",
                status="RUNNING",
                metadata=None,
            ),
        )
        self._seed_multi_country(conn, scraper_id, scraper_jp)

        us_only = get_scraped_files(conn, country_code="US")
        assert len(us_only) == 1
        assert next(iter(us_only))[0] == 100

        jp_only = get_scraped_files(conn, country_code="JP")
        assert len(jp_only) == 1
        assert next(iter(jp_only))[0] == 200

    def test_company_id_filter(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        # Two filings for the same company
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="PDF",
            ),
        )
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="XBRL",
            ),
        )
        out = get_scraped_files(conn, company_id=company_id)
        assert len(out) == 2
        # And a wrong company_id returns nothing
        assert get_scraped_files(conn, company_id=999) == set()


# ---------------------------------------------------------------------------
# get_scraped_pairs
# ---------------------------------------------------------------------------


class TestGetScrapedPairs:
    def test_returns_all_combinations_no_priority_applied(self, seeded_db):
        """For 1 company, 1 fiscal_year, with 2 form types per file_type → 2x2 = 4 pairs."""
        conn, scraper_id, company_id = seeded_db
        # 10-K PDF + 10-KA PDF
        for sfid, form in [("pdf-10k", "10-K"), ("pdf-10ka", "10-KA")]:
            upsert_file(
                conn,
                make_file_record(
                    company_id=company_id,
                    scraper_id=scraper_id,
                    source_filing_id=sfid,
                    file_type="PDF",
                    form_type=form,
                    fiscal_year=2024,
                ),
            )
        # 10-K XBRL + 10-KA XBRL
        for sfid, form in [("xbrl-10k", "10-K"), ("xbrl-10ka", "10-KA")]:
            upsert_file(
                conn,
                make_file_record(
                    company_id=company_id,
                    scraper_id=scraper_id,
                    source_filing_id=sfid,
                    file_type="XBRL",
                    form_type=form,
                    fiscal_year=2024,
                ),
            )

        pairs = get_scraped_pairs(conn)
        # 2 PDFs × 2 XBRLs = 4 combinations; ar-db-handler doesn't pick.
        assert len(pairs) == 4
        # And every pair carries both form types so the caller can priority-sort.
        form_combos = {(p.pdf_form_type, p.xbrl_form_type) for p in pairs}
        assert form_combos == {
            ("10-K", "10-K"),
            ("10-K", "10-KA"),
            ("10-KA", "10-K"),
            ("10-KA", "10-KA"),
        }

    def test_no_result_when_only_one_file_type_is_success(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        # Only a PDF — no XBRL counterpart
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="pdf-only",
                file_type="PDF",
                fiscal_year=2024,
            ),
        )
        assert get_scraped_pairs(conn) == []

        # Add an XBRL but mark it FAILED
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="xbrl-failed",
                file_type="XBRL",
                fiscal_year=2024,
                status="FAILED",
                gcs_path=None,
                error_message="404",
            ),
        )
        assert get_scraped_pairs(conn) == []

    def test_company_id_filter(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        # Seed PDF+XBRL for our company
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="PDF",
                fiscal_year=2024,
            ),
        )
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="XBRL",
                fiscal_year=2024,
            ),
        )
        assert len(get_scraped_pairs(conn, company_id=company_id)) == 1
        assert get_scraped_pairs(conn, company_id=999) == []

    def test_fiscal_year_filter(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        for fy in (2023, 2024):
            for ft in ("PDF", "XBRL"):
                upsert_file(
                    conn,
                    make_file_record(
                        company_id=company_id,
                        scraper_id=scraper_id,
                        source_filing_id=f"acc-{fy}-{ft.lower()}",
                        file_type=ft,
                        fiscal_year=fy,
                    ),
                )
        all_pairs = get_scraped_pairs(conn)
        assert len(all_pairs) == 2

        only_2024 = get_scraped_pairs(conn, fiscal_year=2024)
        assert len(only_2024) == 1
        assert only_2024[0].fiscal_year == 2024

    def test_pending_rows_with_null_fy_do_not_produce_pairs(self, seeded_db):
        """
        Under the v0.2 invariant, NULL fiscal_year can only occur on PENDING
        or FAILED rows (the CHECK constraint forbids it on SUCCESS). Those
        rows are excluded from pairs by the ``status='SUCCESS'`` filter, and
        even if they somehow leaked through, the ``IS NOT NULL`` filter on
        fiscal_year is a second line of defence.
        """
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="PDF",
                status="PENDING",
                fiscal_year=None,
                gcs_path=None,
            ),
        )
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="XBRL",
                status="PENDING",
                fiscal_year=None,
                gcs_path=None,
            ),
        )
        assert get_scraped_pairs(conn) == []


# ---------------------------------------------------------------------------
# list_companies
# ---------------------------------------------------------------------------


class TestListCompanies:
    def test_active_only_default(self, filings_db):
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=1,
                fs_ticker="A",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="a",
                coverage_status="LAFA",
            ),
        )
        # Now manually mark it inactive (mimicking deactivation step).
        filings_db.execute("UPDATE companies SET is_in_company_info = 0 WHERE company_id = 1")
        filings_db.commit()
        assert list_companies(filings_db) == []
        assert len(list_companies(filings_db, active_only=False)) == 1

    def test_country_filter(self, filings_db):
        for cid, cc in [(1, "US"), (2, "JP")]:
            upsert_company(
                filings_db,
                CompanyRecord(
                    company_id=cid,
                    fs_ticker=f"T{cid}",
                    country_code=cc,
                    country=cc,
                    country_id=cc,
                    file_name=f"t{cid}",
                    coverage_status="LAFA",
                ),
            )
        us = list_companies(filings_db, country_code="US")
        assert len(us) == 1 and us[0]["country_code"] == "US"
