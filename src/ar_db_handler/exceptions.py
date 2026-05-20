"""Exceptions raised by ar_db_handler."""

from __future__ import annotations


class AlreadyScrapedError(Exception):
    """Raised when attempting to overwrite a SCRAPED filing_files row.

    Raised by `upsert_filing_file` when an existing row with status
    `SCRAPED` is found for the same `(filing_id, file_type, form_type)`
    triple and `force=False`. The scraper is expected to check
    `get_filing_file()` before attempting a download.

    Pass `force=True` to `upsert_filing_file` to bypass this check and
    unconditionally replace the existing row.
    """
