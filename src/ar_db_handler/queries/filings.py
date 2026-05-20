"""Read helpers for filings.db."""

from __future__ import annotations

import logging
import sqlite3

from ..records import (
    CompanyRecord,
    FilingFileRecord,
    FilingRecord,
    ScrapedPair,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-row lookups
# ---------------------------------------------------------------------------


def get_filing(
    conn: sqlite3.Connection,
    *,
    filing_id: str | None = None,
    company_id: str | None = None,
    fiscal_year: int | None = None,
) -> FilingRecord | None:
    """Return a single filing row, or None.

    Look up by `filing_id` (most direct), or by the natural key
    `(company_id, fiscal_year)`. Exactly one of these two routes must
    be specified.
    """
    if filing_id is not None:
        row = conn.execute(
            """
            SELECT filing_id, company_id, fiscal_year,
                   filing_date, reporting_date, reporting_period
            FROM filings
            WHERE filing_id = ?
            """,
            (filing_id,),
        ).fetchone()
    elif company_id is not None and fiscal_year is not None:
        row = conn.execute(
            """
            SELECT filing_id, company_id, fiscal_year,
                   filing_date, reporting_date, reporting_period
            FROM filings
            WHERE company_id = ? AND fiscal_year = ?
            """,
            (company_id, fiscal_year),
        ).fetchone()
    else:
        raise ValueError("get_filing requires either filing_id or (company_id, fiscal_year)")

    if row is None:
        return None
    return FilingRecord(
        filing_id=row["filing_id"],
        company_id=row["company_id"],
        fiscal_year=row["fiscal_year"],
        filing_date=row["filing_date"],
        reporting_date=row["reporting_date"],
        reporting_period=row["reporting_period"],
    )


def get_filing_file(
    conn: sqlite3.Connection,
    filing_id: str,
    file_type: str,
    form_type: str | None = None,
) -> FilingFileRecord | None:
    """Return a single filing_files row, or None.

    Look-up is on `(filing_id, file_type, form_type)`. `form_type=None`
    matches a NULL `form_type` (uses `IS` to handle NULL equality).
    """
    row = conn.execute(
        """
        SELECT file_id, filing_id, run_id, worker_id,
               file_type, form_type, gcs_path, url,
               scrape_status, scraped_at
        FROM filing_files
        WHERE filing_id = ?
          AND file_type = ?
          AND form_type IS ?
        """,
        (filing_id, file_type, form_type),
    ).fetchone()

    if row is None:
        return None
    return FilingFileRecord(
        file_id=row["file_id"],
        filing_id=row["filing_id"],
        run_id=row["run_id"],
        worker_id=row["worker_id"],
        file_type=row["file_type"],
        form_type=row["form_type"],
        gcs_path=row["gcs_path"],
        url=row["url"],
        scrape_status=row["scrape_status"],
        scraped_at=row["scraped_at"],
    )


# ---------------------------------------------------------------------------
# Bulk reads
# ---------------------------------------------------------------------------


def list_companies(conn: sqlite3.Connection) -> list[CompanyRecord]:
    """Return all rows from `companies`, ordered by company_id."""
    rows = conn.execute(
        """
        SELECT company_id, name, ticker, exchange, country, updated_at
        FROM companies
        ORDER BY company_id
        """
    ).fetchall()
    return [
        CompanyRecord(
            company_id=r["company_id"],
            name=r["name"],
            ticker=r["ticker"],
            exchange=r["exchange"],
            country=r["country"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def get_scraped_pairs(
    conn: sqlite3.Connection,
    company_id: str | None = None,
    fiscal_year: int | None = None,
) -> list[ScrapedPair]:
    """Return filings for which BOTH PDF and XBRL are SCRAPED.

    This is the primary discovery query used by the evaluator: it
    answers "which filings can I evaluate right now?". The join makes a
    pair-existence assertion at the SQL level — there is no Python-side
    filtering involved beyond the optional `company_id` / `fiscal_year`
    narrowing.

    Both filters are optional and combine with AND.
    """
    sql = """
        SELECT
            f.filing_id,
            f.company_id,
            f.fiscal_year,
            ff_pdf.gcs_path  AS pdf_gcs_path,
            ff_xbrl.gcs_path AS xbrl_gcs_path
        FROM filings f
        JOIN filing_files ff_pdf
            ON ff_pdf.filing_id = f.filing_id
            AND ff_pdf.file_type = 'PDF'
            AND ff_pdf.scrape_status = 'SCRAPED'
        JOIN filing_files ff_xbrl
            ON ff_xbrl.filing_id = f.filing_id
            AND ff_xbrl.file_type = 'XBRL'
            AND ff_xbrl.scrape_status = 'SCRAPED'
    """
    where: list[str] = []
    params: list[object] = []
    if company_id is not None:
        where.append("f.company_id = ?")
        params.append(company_id)
    if fiscal_year is not None:
        where.append("f.fiscal_year = ?")
        params.append(fiscal_year)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY f.company_id, f.fiscal_year"

    rows = conn.execute(sql, params).fetchall()
    return [
        ScrapedPair(
            filing_id=r["filing_id"],
            company_id=r["company_id"],
            fiscal_year=r["fiscal_year"],
            pdf_gcs_path=r["pdf_gcs_path"],
            xbrl_gcs_path=r["xbrl_gcs_path"],
        )
        for r in rows
    ]
