"""
Read helpers for ``filings.db``.

The two important entry points are:

* ``get_scraped_files()`` — built once at scraper start, used as a fast
  O(1) skip-set keyed on the natural unique key.
* ``get_scraped_pairs()`` — evaluator entry point, returns every
  ``(PDF, XBRL)`` pair for a given company/fiscal-year without applying
  any priority logic. ar-db-handler is country-agnostic and has no
  knowledge of which form_type should take precedence over another.
"""

from __future__ import annotations

import sqlite3

from .._models import ScrapedPair

# ---------------------------------------------------------------------------
# Single-row lookups
# ---------------------------------------------------------------------------


def get_file(conn: sqlite3.Connection, file_id: str) -> dict | None:
    """
    Return one ``files`` row as a dict, or ``None`` if no such ``file_id``.
    """
    cur = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,))
    row = cur.fetchone()
    if row is None:
        return None
    columns = [d[0] for d in cur.description]
    return dict(zip(columns, row, strict=False))


# ---------------------------------------------------------------------------
# Scraper-facing skip-set
# ---------------------------------------------------------------------------


def get_scraped_files(
    conn: sqlite3.Connection,
    country_code: str | None = None,
    company_id: int | None = None,
) -> set[tuple[int, str, str]]:
    """
    Return the set of ``(company_id, source_filing_id, file_type)`` for every
    row with ``status = 'SUCCESS'``.

    The scraper builds this once at startup and treats it as an O(1) membership
    check before every download attempt:

        already = get_scraped_files(conn, country_code="US")
        if (company_id, source_filing_id, file_type) in already:
            continue  # skip

    ``fiscal_year`` is intentionally NOT part of the tuple — it is derived
    metadata and may be ``NULL`` for unresolvable filings. Using it as a
    skip anchor would cause false misses for rows where derivation failed
    (the second-attempt scrape would re-download the same file).

    Args:
        country_code: Optional filter — pass the scraper's country to avoid
                      loading irrelevant rows.
        company_id:   Optional filter — useful in single-company CLI mode.

    Returns:
        ``set[tuple[int, str, str]]``.
    """
    cur = conn.execute(
        """
        SELECT company_id, source_filing_id, file_type
        FROM files
        WHERE status = 'SUCCESS'
          AND (country_code = :cc OR :cc IS NULL)
          AND (company_id  = :cid OR :cid IS NULL)
        """,
        {"cc": country_code, "cid": company_id},
    )
    return {(int(cid), str(sfid), str(ftype)) for (cid, sfid, ftype) in cur.fetchall()}


# ---------------------------------------------------------------------------
# Evaluator-facing pair join
# ---------------------------------------------------------------------------


def get_scraped_pairs(
    conn: sqlite3.Connection,
    company_id: int | None = None,
    fiscal_year: int | None = None,
) -> list[ScrapedPair]:
    """
    Return every SUCCESS (PDF, XBRL) pair sharing a ``(company_id, fiscal_year)``.

    No priority or form-type filtering is applied — ar-db-handler is
    country-agnostic and does not know whether (for example) a 10-K should
    beat a 10-KA. When multiple form types exist for the same
    ``(company_id, fiscal_year, file_type)``, all combinations are returned
    and the caller (country-specific scraper or evaluator) selects.

    Rows with ``fiscal_year IS NULL`` (PENDING or FAILED rows — the CHECK
    constraint forbids NULL fiscal_year on SUCCESS rows) are excluded —
    they would produce a cartesian explosion via the SQL join and have
    nothing to evaluate anyway.
    """
    cur = conn.execute(
        """
        SELECT
            f_pdf.file_id        AS file_id_pdf,
            f_xbrl.file_id       AS file_id_xbrl,
            f_pdf.company_id     AS company_id,
            f_pdf.fiscal_year    AS fiscal_year,
            f_pdf.gcs_path       AS pdf_gcs_path,
            f_xbrl.gcs_path      AS xbrl_gcs_path,
            f_pdf.form_type      AS pdf_form_type,
            f_xbrl.form_type     AS xbrl_form_type
        FROM files f_pdf
        JOIN files f_xbrl
            ON  f_xbrl.company_id  = f_pdf.company_id
            AND f_xbrl.fiscal_year = f_pdf.fiscal_year
            AND f_xbrl.file_type   = 'XBRL'
            AND f_xbrl.status      = 'SUCCESS'
        WHERE f_pdf.file_type      = 'PDF'
          AND f_pdf.status         = 'SUCCESS'
          AND f_pdf.fiscal_year IS NOT NULL
          AND (f_pdf.company_id  = :cid OR :cid IS NULL)
          AND (f_pdf.fiscal_year = :fy  OR :fy  IS NULL)
        """,
        {"cid": company_id, "fy": fiscal_year},
    )
    return [
        ScrapedPair(
            file_id_pdf=row[0],
            file_id_xbrl=row[1],
            company_id=int(row[2]),
            fiscal_year=int(row[3]),
            pdf_gcs_path=row[4],
            xbrl_gcs_path=row[5],
            pdf_form_type=row[6],
            xbrl_form_type=row[7],
        )
        for row in cur.fetchall()
    ]


# ---------------------------------------------------------------------------
# Companies listing
# ---------------------------------------------------------------------------


def list_companies(
    conn: sqlite3.Connection,
    country_code: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """
    Return rows from ``companies``, optionally filtered by country and active flag.

    Args:
        country_code: If set, restricts to one country.
        active_only:  When ``True`` (the default), only returns rows with
                      ``is_in_company_info = 1``. The scraper almost always
                      wants this — delisted companies should not be re-scraped.
    """
    where: list[str] = []
    params: dict[str, object] = {}
    if country_code is not None:
        where.append("country_code = :cc")
        params["cc"] = country_code
    if active_only:
        where.append("is_in_company_info = 1")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur = conn.execute(f"SELECT * FROM companies {where_sql} ORDER BY company_id", params)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]
