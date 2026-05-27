"""
Canonical GCS blob-path scheme for the annual report pipeline.

The scheme
----------
::

    rawdata/{country_code}/{company_id}/{fiscal_year}/{file_type}_{form_type}_{reporting_date}{extension}

Worked examples:

* ``rawdata/US/14778/2023/PDF_10-K_2023-12-31.pdf``
* ``rawdata/US/14778/2023/XBRL_10-K_2023-12-31.zip``
* ``rawdata/JP/200042/2023/PDF_ASR_2024-03-31.pdf``

This module is pure — no DB access, no I/O, no logging beyond what
errors carry in their messages. It also does NOT import from
``gcs-handler``; the path is just a string. ``GCSClient`` is bound to
a bucket at construction time, so the bucket name is not part of
this blob path.

The three public entry points:

* ``make_blob_path(...)``       — pure path builder from raw arguments
* ``resolve_gcs_path(record)``  — convenience wrapper over a ``FileRecord``
* ``derive_fiscal_year(date)``  — H2/H1 fiscal-year rule helper

``make_blob_path`` trusts ``fiscal_year`` as stored on the record.
The H2/H1 derivation is the scrapers' responsibility at record-building
time; ``derive_fiscal_year`` is exposed here as the single source of
truth for the rule.
"""

from __future__ import annotations

import re

from ._models import FileRecord, MissingFiscalYearError
from .ids import EXTENSION_MAP, resolve_extension

# Module-level constant so the prefix can't drift between callers.
_RAW_PREFIX = "rawdata"

# Reporting-date regex: strict YYYY-MM-DD. We do NOT validate semantic
# date correctness (e.g. 2023-02-30) — that's the scraper's job at
# record-building time. The shape check here is enough to keep the
# bucket layout consistent.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_non_blank(value: str | None, field_name: str) -> str:
    """
    Return ``value`` if it's a non-empty, non-whitespace string;
    otherwise raise ``ValueError`` naming the offending field.

    Centralised so every component check produces the same message
    shape, which makes the test assertions trivial.
    """
    if value is None or not str(value).strip():
        raise ValueError(
            f"make_blob_path: {field_name} must be a non-empty string " f"(got {value!r})"
        )
    return str(value)


def make_blob_path(
    country_code: str,
    company_id: int,
    fiscal_year: int,
    file_type: str,
    form_type: str,
    reporting_date: str,
    extension: str,
) -> str:
    """
    Compose the canonical GCS blob path from filing metadata.

    Returns:
        ``rawdata/{country_code}/{company_id}/{fiscal_year}/{file_type}_{form_type}_{reporting_date}{extension}``

    Raises:
        ValueError:              if any required component is empty,
                                 whitespace-only, or malformed.
        MissingFiscalYearError:  if ``fiscal_year is None``.
    """
    # ---- fiscal_year is special: missing year is the same invariant
    # ---- enforced by upsert_file, so we raise the SAME exception type.
    if fiscal_year is None:
        raise MissingFiscalYearError(
            "make_blob_path: fiscal_year must not be None — "
            "derive it from reporting_date before building the path."
        )

    # ---- Required string components. Each check names its field so
    # ---- the caller knows what to fix without parsing the message.
    country_code = _require_non_blank(country_code, "country_code")
    if any(c.isspace() for c in country_code):
        raise ValueError(
            f"make_blob_path: country_code must not contain whitespace " f"(got {country_code!r})"
        )

    file_type = _require_non_blank(file_type, "file_type")
    if file_type not in EXTENSION_MAP:
        valid = ", ".join(sorted(EXTENSION_MAP))
        raise ValueError(
            f"make_blob_path: file_type {file_type!r} is not in EXTENSION_MAP "
            f"(expected one of: {valid})"
        )

    # form_type post-normalisation is never empty — _normalise_form_type
    # in upsert_file produces 'UNKNOWN' for blank input. So this check
    # only fires on programming errors (caller built the path without
    # going through upsert_file's normalisation).
    form_type = _require_non_blank(form_type, "form_type")

    reporting_date = _require_non_blank(reporting_date, "reporting_date")
    if not _DATE_RE.match(reporting_date):
        raise ValueError(
            f"make_blob_path: reporting_date must match YYYY-MM-DD " f"(got {reporting_date!r})"
        )

    # extension is stored WITH a leading dot (".pdf", ".zip"). We check
    # both shape requirements explicitly so a future change to
    # EXTENSION_MAP that drops the dot fails loud here.
    if not extension or not extension.startswith("."):
        raise ValueError(
            f"make_blob_path: extension must be non-empty and start with '.' "
            f"(got {extension!r})"
        )

    return (
        f"{_RAW_PREFIX}/"
        f"{country_code}/"
        f"{company_id}/"
        f"{fiscal_year}/"
        f"{file_type}_{form_type}_{reporting_date}{extension}"
    )


def resolve_gcs_path(record: FileRecord) -> str:
    """
    Build the canonical GCS blob path for a ``FileRecord``.

    Pulls the seven path components off the record (resolving
    ``extension`` from ``file_type`` via :func:`resolve_extension`)
    and delegates to :func:`make_blob_path`. The record's
    ``fiscal_year`` is trusted as stored — see the module docstring.

    Raises:
        ValueError:              same conditions as ``make_blob_path``.
        MissingFiscalYearError:  if ``record.fiscal_year is None``.
    """
    # extension is never on the dataclass — it's a DB-only column
    # derived from file_type. So we always resolve it here.
    extension = resolve_extension(record.file_type) if record.file_type else ""

    return make_blob_path(
        country_code=record.country_code or "",
        company_id=record.company_id,
        fiscal_year=record.fiscal_year,
        file_type=record.file_type or "",
        form_type=record.form_type or "",
        reporting_date=record.reporting_date or "",
        extension=extension,
    )


def derive_fiscal_year(reporting_date: str) -> int:
    """
    Apply the H2/H1 rule to derive a fiscal year from a period-end date.

    The convention: a fiscal year is named by the calendar year that
    contains its H2 (months July–December). So:

    * period-end in months 07–12 → ``fiscal_year = year(reporting_date)``
    * period-end in months 01–06 → ``fiscal_year = year(reporting_date) - 1``

    Examples:

    +-------------------+-------------+
    | ``reporting_date``| fiscal_year |
    +===================+=============+
    | 2023-12-31        | 2023        |
    +-------------------+-------------+
    | 2023-09-30        | 2023        |
    +-------------------+-------------+
    | 2023-07-31        | 2023        |
    +-------------------+-------------+
    | 2023-06-30        | 2022        |
    +-------------------+-------------+
    | 2023-03-31        | 2022        |
    +-------------------+-------------+
    | 2024-01-31        | 2023        |
    +-------------------+-------------+

    Exposed as a helper for scrapers to call when *building* a
    ``FileRecord``. ``make_blob_path`` itself does NOT call this —
    it trusts the value already on the record. One source of truth
    for the rule, lives here.

    Args:
        reporting_date: A ``YYYY-MM-DD`` string.

    Returns:
        4-digit fiscal year.

    Raises:
        ValueError: if ``reporting_date`` is malformed.
    """
    if reporting_date is None or not str(reporting_date).strip():
        raise ValueError(
            f"derive_fiscal_year: reporting_date must be a non-empty string "
            f"(got {reporting_date!r})"
        )

    if not _DATE_RE.match(reporting_date):
        raise ValueError(
            f"derive_fiscal_year: reporting_date must match YYYY-MM-DD " f"(got {reporting_date!r})"
        )

    # Split rather than strptime — we deliberately accept dates like
    # 2023-02-30 that strptime would reject. The scraper should have
    # validated semantic correctness already; this helper only applies
    # the H2/H1 rule.
    year_str, month_str, _ = reporting_date.split("-")
    year = int(year_str)
    month = int(month_str)

    if not 1 <= month <= 12:
        raise ValueError(f"derive_fiscal_year: month {month} out of range in {reporting_date!r}")

    # H2 (Jul–Dec): fiscal year matches calendar year.
    # H1 (Jan–Jun): fiscal year is the previous calendar year.
    return year if month >= 7 else year - 1
