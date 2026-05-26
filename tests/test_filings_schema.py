"""Tests for the filings.db schema, pragmas, and column metadata."""

from __future__ import annotations

import sqlite3

import pytest


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    """Return ``{column_name: {type, notnull, dflt_value, ...}}`` for a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    return {
        r[1]: {"type": r[2], "notnull": bool(r[3]), "dflt_value": r[4], "pk": bool(r[5])}
        for r in rows
    }


class TestTablesExist:
    def test_companies_table_exists(self, filings_db):
        cols = _columns(filings_db, "companies")
        assert "company_id" in cols
        assert "fs_ticker" in cols

    def test_scraper_runs_table_exists(self, filings_db):
        cols = _columns(filings_db, "scraper_runs")
        assert "scraper_id" in cols

    def test_files_table_exists(self, filings_db):
        cols = _columns(filings_db, "files")
        assert "file_id" in cols
        assert "extension" in cols  # the prompt explicitly requires this
        assert "form_type" in cols
        assert "source_filing_id" in cols
        # fiscal_year_status was removed in v0.2 — the CHECK constraint
        # below carries the invariant instead.
        assert "fiscal_year_status" not in cols

    def test_scraper_errors_table_exists(self, filings_db):
        cols = _columns(filings_db, "scraper_errors")
        # Every column that record_error() writes must be present.
        for required in (
            "error_id",
            "scraper_id",
            "error_type",
            "error_message",
            "company_id",
            "source_filing_id",
            "file_type",
            "payload",
            "recorded_at",
        ):
            assert required in cols, f"scraper_errors missing column {required}"


class TestPragmas:
    def test_wal_mode_enabled(self, filings_db):
        mode = filings_db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_enabled(self, filings_db):
        fk = filings_db.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


class TestFormTypeColumn:
    """form_type must be NOT NULL with DEFAULT 'UNKNOWN'."""

    def test_form_type_is_not_null(self, filings_db):
        cols = _columns(filings_db, "files")
        assert cols["form_type"]["notnull"] is True

    def test_form_type_default_is_unknown(self, filings_db):
        cols = _columns(filings_db, "files")
        # SQLite stores defaults as the literal text including quotes
        dflt = cols["form_type"]["dflt_value"]
        assert dflt is not None
        assert dflt.strip("'\"") == "UNKNOWN"

    def test_extension_is_not_null(self, filings_db):
        cols = _columns(filings_db, "files")
        assert cols["extension"]["notnull"] is True


class TestUniqueConstraint:
    """UNIQUE on (company_id, source_filing_id, file_type).

    SQLite creates one ``sqlite_autoindex_files_*`` per implicit index:
    one for the PRIMARY KEY on ``file_id`` and a second for the UNIQUE
    constraint we care about here. We locate the right one by inspecting
    the columns rather than relying on the numeric suffix (which is
    fragile across SQLite versions and DDL ordering).
    """

    @staticmethod
    def _autoindex_columns(conn) -> list[list[str]]:
        """Return the column lists of every auto-index on ``files``."""
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='files' "
            "AND name LIKE 'sqlite_autoindex_files_%'"
        ).fetchall()
        out = []
        for r in rows:
            cols = conn.execute(f"PRAGMA index_info({r[0]})").fetchall()
            out.append([c[2] for c in cols])
        return out

    def test_unique_index_present(self, filings_db):
        all_autoindex_cols = self._autoindex_columns(filings_db)
        assert ["company_id", "source_filing_id", "file_type"] in all_autoindex_cols, (
            f"Expected the natural-key UNIQUE auto-index to exist; "
            f"got these auto-index column sets: {all_autoindex_cols}"
        )

    def test_fiscal_year_is_NOT_in_unique_constraint(self, filings_db):
        # No auto-index — primary key OR unique — should include fiscal_year.
        for cols in self._autoindex_columns(filings_db):
            assert "fiscal_year" not in cols, (
                f"fiscal_year leaked into an auto-index: {cols}. "
                f"It must remain derived metadata, not a uniqueness anchor."
            )


class TestIdempotentInit:
    def test_init_filings_db_twice_does_not_fail(self, tmp_path):
        from ar_db_handler import init_filings_db

        db = tmp_path / "x.db"
        c1 = init_filings_db(db)
        c1.close()
        # Second init should be a no-op.
        c2 = init_filings_db(db)
        c2.close()


class TestFiscalYearCheckConstraint:
    """
    `CHECK (status != 'SUCCESS' OR fiscal_year IS NOT NULL)` must reject
    a raw INSERT (i.e. one that bypasses the Python-side check in
    upsert_file). We hit the DB directly so any future helper that takes
    a shortcut around upsert_file still fails the invariant at the SQL
    layer.
    """

    def test_raw_insert_success_with_null_fy_is_rejected(self, seeded_db):
        import sqlite3

        conn, scraper_id, company_id = seeded_db
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(
                """
                INSERT INTO files (
                    file_id, company_id, scraper_id, status,
                    country_code, file_type, extension, form_type,
                    source_filing_id, fiscal_year,
                    reporting_date, filing_date, gcs_path, url,
                    scraped_at, error_message
                ) VALUES (
                    'rawhash', ?, ?, 'SUCCESS',
                    'US', 'PDF', '.pdf', '10-K',
                    'raw-test', NULL,
                    NULL, NULL, 'gs://x', NULL, NULL, NULL
                )
                """,
                (company_id, scraper_id),
            )

    def test_raw_insert_pending_with_null_fy_is_allowed(self, seeded_db):
        """PENDING rows are exempt from the invariant."""
        conn, scraper_id, company_id = seeded_db
        conn.execute(
            """
            INSERT INTO files (
                file_id, company_id, scraper_id, status,
                country_code, file_type, extension, form_type,
                source_filing_id, fiscal_year,
                reporting_date, filing_date, gcs_path, url,
                scraped_at, error_message
            ) VALUES (
                'rawpend', ?, ?, 'PENDING',
                'US', 'PDF', '.pdf', '10-K',
                'raw-pend', NULL,
                NULL, NULL, NULL, NULL, NULL, NULL
            )
            """,
            (company_id, scraper_id),
        )
        # No exception — the CHECK passes because status != 'SUCCESS'.
