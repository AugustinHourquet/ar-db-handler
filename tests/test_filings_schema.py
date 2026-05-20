"""Schema-level tests for filings.db."""

from __future__ import annotations

import sqlite3

import pytest


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_tables_created(filings_db):
    names = _table_names(filings_db)
    assert {"scraper_runs", "companies", "filings", "filing_files"} <= names


def test_wal_mode_is_on(filings_db):
    mode = filings_db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_foreign_keys_pragma_on(filings_db):
    fk = filings_db.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_filings_unique_constraint(filings_db, seeded_filings_db):
    # A second filing with the same (company_id, fiscal_year) should
    # be silently ignored by INSERT OR IGNORE — we test that path
    # explicitly in test_filings_upserts; here we assert the constraint
    # exists at the schema level.
    info = filings_db.execute("PRAGMA index_list('filings')").fetchall()
    has_unique = any(row["unique"] == 1 for row in info)
    assert has_unique, "filings table should have a UNIQUE index"


def test_filing_files_fk_to_filings(filings_db):
    # Inserting a filing_files row referencing a non-existent filing_id
    # must fail with an IntegrityError because FKs are on.
    with pytest.raises(sqlite3.IntegrityError):
        filings_db.execute(
            """
            INSERT INTO filing_files (
                file_id, filing_id, run_id, worker_id,
                file_type, form_type, gcs_path, url,
                scrape_status, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ff-1",
                "nonexistent-filing",
                "nonexistent-run",
                1,
                "PDF",
                "10-K",
                "gs://x",
                "https://x",
                "PENDING",
                None,
            ),
        )
        filings_db.commit()


def test_idempotent_init(tmp_path):
    """Calling init_filings_db twice on the same path must not error."""
    from ar_db_handler import init_filings_db

    path = tmp_path / "filings.db"
    c1 = init_filings_db(path)
    c1.close()
    c2 = init_filings_db(path)  # should be a no-op
    c2.close()
