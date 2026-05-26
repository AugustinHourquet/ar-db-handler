"""Tests for the filings.db upsert helpers."""

from __future__ import annotations

import pytest

from ar_db_handler import (
    AlreadyScrapedError,
    CompanyRecord,
    make_file_id,
    update_run_finished,
    upsert_company,
    upsert_file,
)
from tests.conftest import make_file_record

# ---------------------------------------------------------------------------
# upsert_file — the rich case
# ---------------------------------------------------------------------------


class TestUpsertFileBasics:
    def test_inserts_new_row(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
            ),
        )
        rows = conn.execute("SELECT COUNT(*) FROM files").fetchone()
        assert rows[0] == 1

    def test_file_id_is_derived(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="PDF",
            ),
        )
        expected = make_file_id(company_id, "acc-1", "PDF")
        actual = conn.execute("SELECT file_id FROM files").fetchone()[0]
        assert actual == expected

    def test_extension_auto_resolved_for_pdf(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="PDF",
            ),
        )
        ext = conn.execute("SELECT extension FROM files").fetchone()[0]
        assert ext == ".pdf"

    def test_extension_auto_resolved_for_xbrl(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                file_type="XBRL",
            ),
        )
        ext = conn.execute("SELECT extension FROM files").fetchone()[0]
        assert ext == ".zip"

    def test_raises_value_error_on_unknown_file_type(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        with pytest.raises(ValueError, match="Unknown file_type"):
            upsert_file(
                conn,
                make_file_record(
                    company_id=company_id,
                    scraper_id=scraper_id,
                    source_filing_id="acc-1",
                    file_type="HTML",
                ),
            )

    def test_no_row_inserted_when_file_type_invalid(self, seeded_db):
        """ValueError fires BEFORE the INSERT, so the table stays empty."""
        conn, scraper_id, company_id = seeded_db
        try:
            upsert_file(
                conn,
                make_file_record(
                    company_id=company_id,
                    scraper_id=scraper_id,
                    source_filing_id="acc-1",
                    file_type="HTML",
                ),
            )
        except ValueError:
            pass
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0


class TestFormTypeNormalisation:
    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_none_or_empty_becomes_unknown(self, seeded_db, raw):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                form_type=raw,
            ),
        )
        ft = conn.execute("SELECT form_type FROM files").fetchone()[0]
        assert ft == "UNKNOWN"

    def test_explicit_form_type_preserved(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                form_type="10-K",
            ),
        )
        ft = conn.execute("SELECT form_type FROM files").fetchone()[0]
        assert ft == "10-K"


class TestFiscalYearInvariant:
    """status='SUCCESS' requires fiscal_year — Python check AND DB CHECK constraint."""

    def test_success_with_fy_is_stored(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="SUCCESS",
                fiscal_year=2024,
            ),
        )
        row = conn.execute("SELECT fiscal_year FROM files").fetchone()
        assert row[0] == 2024

    def test_success_with_null_fy_raises_missing_fiscal_year_error(self, seeded_db):
        from ar_db_handler import MissingFiscalYearError

        conn, scraper_id, company_id = seeded_db
        with pytest.raises(MissingFiscalYearError, match="fiscal_year"):
            upsert_file(
                conn,
                make_file_record(
                    company_id=company_id,
                    scraper_id=scraper_id,
                    source_filing_id="acc-1",
                    status="SUCCESS",
                    fiscal_year=None,
                ),
            )

    def test_no_row_inserted_when_invariant_fails(self, seeded_db):
        from ar_db_handler import MissingFiscalYearError

        conn, scraper_id, company_id = seeded_db
        with pytest.raises(MissingFiscalYearError):
            upsert_file(
                conn,
                make_file_record(
                    company_id=company_id,
                    scraper_id=scraper_id,
                    source_filing_id="acc-1",
                    status="SUCCESS",
                    fiscal_year=None,
                ),
            )
        # Nothing in files — the check ran BEFORE the INSERT.
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0

    def test_pending_with_null_fy_is_allowed(self, seeded_db):
        """PENDING rows may have NULL fiscal_year — work isn't committed yet."""
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="PENDING",
                fiscal_year=None,
                gcs_path=None,
            ),
        )
        row = conn.execute("SELECT status, fiscal_year FROM files").fetchone()
        assert row == ("PENDING", None)

    def test_failed_with_null_fy_is_allowed(self, seeded_db):
        """FAILED rows may have NULL fiscal_year — couldn't resolve, that's fine."""
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="FAILED",
                fiscal_year=None,
                gcs_path=None,
                error_message="404",
            ),
        )
        row = conn.execute("SELECT status, fiscal_year FROM files").fetchone()
        assert row == ("FAILED", None)


# ---------------------------------------------------------------------------
# AlreadyScrapedError and force=
# ---------------------------------------------------------------------------


class TestAlreadyScrapedError:
    def test_success_then_no_force_raises(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        rec = make_file_record(
            company_id=company_id,
            scraper_id=scraper_id,
            source_filing_id="acc-1",
            status="SUCCESS",
        )
        upsert_file(conn, rec)
        with pytest.raises(AlreadyScrapedError):
            upsert_file(conn, rec, force=False)

    def test_success_then_force_overwrites(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        # First write at fiscal_year=2024
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="SUCCESS",
                fiscal_year=2024,
            ),
        )
        # Overwrite at fiscal_year=2023 with force=True
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="SUCCESS",
                fiscal_year=2023,
            ),
            force=True,
        )
        fy = conn.execute("SELECT fiscal_year FROM files").fetchone()[0]
        assert fy == 2023

    def test_pending_overwritten_without_force(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="PENDING",
            ),
        )
        # Without force=True: should overwrite cleanly.
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="SUCCESS",
            ),
        )
        status = conn.execute("SELECT status FROM files").fetchone()[0]
        assert status == "SUCCESS"

    def test_failed_overwritten_without_force(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="FAILED",
                error_message="404 not found",
                gcs_path=None,
            ),
        )
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-1",
                status="SUCCESS",
                error_message=None,
            ),
        )
        rows = conn.execute("SELECT status, error_message FROM files").fetchall()
        assert len(rows) == 1
        assert rows[0] == ("SUCCESS", None)


class TestAmendmentsCoexist:
    """Two filings with the same fiscal_year but different source_filing_id stay separate."""

    def test_10k_and_10ka_coexist(self, seeded_db):
        conn, scraper_id, company_id = seeded_db
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-10k",
                form_type="10-K",
                fiscal_year=2024,
                file_type="PDF",
            ),
        )
        upsert_file(
            conn,
            make_file_record(
                company_id=company_id,
                scraper_id=scraper_id,
                source_filing_id="acc-10ka",
                form_type="10-KA",
                fiscal_year=2024,
                file_type="PDF",
            ),
        )
        rows = conn.execute("SELECT form_type FROM files ORDER BY form_type").fetchall()
        assert [r[0] for r in rows] == ["10-K", "10-KA"]


# ---------------------------------------------------------------------------
# upsert_company
# ---------------------------------------------------------------------------


class TestUpsertCompany:
    def test_sets_is_in_company_info_to_1(self, filings_db):
        # Even if the caller hands in 0, the helper forces it to 1.
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=42,
                fs_ticker="MSFT",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="msft",
                coverage_status="LAFA",
                start_year_force=2010,
                is_in_company_info=0,
            ),
        )
        flag = filings_db.execute(
            "SELECT is_in_company_info FROM companies WHERE company_id = 42"
        ).fetchone()[0]
        assert flag == 1

    def test_sets_last_synced_at(self, filings_db):
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=42,
                fs_ticker="MSFT",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="msft",
                coverage_status="LAFA",
                start_year_force=2010,
            ),
        )
        ts = filings_db.execute(
            "SELECT last_synced_at FROM companies WHERE company_id = 42"
        ).fetchone()[0]
        assert ts is not None and "T" in ts  # ISO-ish

    def test_replace_overwrites(self, filings_db):
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=42,
                fs_ticker="MSFT",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="msft",
                coverage_status="LAFA",
                start_year_force=2010,
            ),
        )
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=42,
                fs_ticker="MSFT",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="msft_v2",
                coverage_status="LANA",
                start_year_force=2012,
            ),
        )
        rows = filings_db.execute(
            "SELECT file_name, coverage_status, start_year_force FROM companies"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == ("msft_v2", "LANA", 2012)


# ---------------------------------------------------------------------------
# update_run_finished
# ---------------------------------------------------------------------------


class TestUpdateRunFinished:
    def test_updates_all_count_columns(self, seeded_db):
        conn, scraper_id, _ = seeded_db
        update_run_finished(
            conn,
            scraper_id=scraper_id,
            status="SUCCESS",
            finished_at="2026-05-22T11:00:00+00:00",
            elapsed_time=3600.5,
            scraped_files=120,
            xbrl_count=60,
            pdf_count=60,
            fail_count=2,
        )
        row = conn.execute(
            """
            SELECT status, finished_at, elapsed_time,
                   scraped_files, xbrl_count, pdf_count, fail_count
            FROM scraper_runs WHERE scraper_id = ?
            """,
            (scraper_id,),
        ).fetchone()
        assert row == (
            "SUCCESS",
            "2026-05-22T11:00:00+00:00",
            3600.5,
            120,
            60,
            60,
            2,
        )
