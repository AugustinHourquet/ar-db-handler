"""
Tests for ``ar_db_handler.paths``.

The path builder is pure (no DB, no I/O), so these tests assert
strings — they never check GCS state.
"""

from __future__ import annotations

import pytest

from ar_db_handler import (
    FileRecord,
    MissingFiscalYearError,
    derive_fiscal_year,
    make_blob_path,
    resolve_gcs_path,
)

# ---------------------------------------------------------------------------
# make_blob_path — happy paths
# ---------------------------------------------------------------------------


class TestMakeBlobPathHappyPath:
    def test_canonical_pdf_10k(self):
        path = make_blob_path(
            country_code="US",
            company_id=14778,
            fiscal_year=2023,
            file_type="PDF",
            form_type="10-K",
            reporting_date="2023-12-31",
            extension=".pdf",
        )
        assert path == "rawdata/US/14778/2023/PDF_10-K_2023-12-31.pdf"

    def test_canonical_xbrl_10k(self):
        path = make_blob_path(
            country_code="US",
            company_id=14778,
            fiscal_year=2023,
            file_type="XBRL",
            form_type="10-K",
            reporting_date="2023-12-31",
            extension=".zip",
        )
        assert path == "rawdata/US/14778/2023/XBRL_10-K_2023-12-31.zip"

    def test_jp_asr(self):
        path = make_blob_path(
            country_code="JP",
            company_id=200042,
            fiscal_year=2023,
            file_type="PDF",
            form_type="ASR",
            reporting_date="2024-03-31",
            extension=".pdf",
        )
        assert path == "rawdata/JP/200042/2023/PDF_ASR_2024-03-31.pdf"

    def test_form_type_unknown_is_accepted(self):
        """'UNKNOWN' is a recognised value, not a missing one."""
        path = make_blob_path(
            country_code="US",
            company_id=100,
            fiscal_year=2024,
            file_type="PDF",
            form_type="UNKNOWN",
            reporting_date="2024-12-31",
            extension=".pdf",
        )
        assert path == "rawdata/US/100/2024/PDF_UNKNOWN_2024-12-31.pdf"


# ---------------------------------------------------------------------------
# make_blob_path — validation
# ---------------------------------------------------------------------------


def _valid_kwargs(**overrides):
    """A full set of valid kwargs we can perturb one field at a time."""
    base = dict(
        country_code="US",
        company_id=100,
        fiscal_year=2023,
        file_type="PDF",
        form_type="10-K",
        reporting_date="2023-12-31",
        extension=".pdf",
    )
    base.update(overrides)
    return base


class TestMakeBlobPathValidation:
    """One test per offending field, each asserting the message names it."""

    @pytest.mark.parametrize("bad", [None, "", "   ", "\t"])
    def test_blank_country_code_raises(self, bad):
        with pytest.raises(ValueError, match="country_code"):
            make_blob_path(**_valid_kwargs(country_code=bad))

    def test_country_code_with_whitespace_raises(self):
        with pytest.raises(ValueError, match="country_code"):
            make_blob_path(**_valid_kwargs(country_code="US X"))

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_blank_file_type_raises(self, bad):
        with pytest.raises(ValueError, match="file_type"):
            make_blob_path(**_valid_kwargs(file_type=bad))

    def test_unknown_file_type_raises(self):
        with pytest.raises(ValueError, match="file_type"):
            make_blob_path(**_valid_kwargs(file_type="HTML"))

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_blank_form_type_raises(self, bad):
        with pytest.raises(ValueError, match="form_type"):
            make_blob_path(**_valid_kwargs(form_type=bad))

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_blank_reporting_date_raises(self, bad):
        with pytest.raises(ValueError, match="reporting_date"):
            make_blob_path(**_valid_kwargs(reporting_date=bad))

    @pytest.mark.parametrize(
        "bad",
        [
            "2023/12/31",  # wrong separator
            "31-12-2023",  # day-first
            "2023-1-31",  # single-digit month
            "2023-12-1",  # single-digit day
            "20231231",  # no separators
            "2023-12-31T00:00:00",  # extra trailer
        ],
    )
    def test_malformed_reporting_date_raises(self, bad):
        with pytest.raises(ValueError, match="reporting_date"):
            make_blob_path(**_valid_kwargs(reporting_date=bad))

    def test_empty_extension_raises(self):
        with pytest.raises(ValueError, match="extension"):
            make_blob_path(**_valid_kwargs(extension=""))

    def test_extension_without_leading_dot_raises(self):
        with pytest.raises(ValueError, match="extension"):
            make_blob_path(**_valid_kwargs(extension="pdf"))

    def test_none_fiscal_year_raises_missing_fiscal_year_error(self):
        """fiscal_year is special: same invariant as upsert_file."""
        with pytest.raises(MissingFiscalYearError, match="fiscal_year"):
            make_blob_path(**_valid_kwargs(fiscal_year=None))


# ---------------------------------------------------------------------------
# resolve_gcs_path
# ---------------------------------------------------------------------------


class TestResolveGcsPath:
    def test_end_to_end_on_full_record(self):
        record = FileRecord(
            company_id=14778,
            scraper_id="run-x",
            status="SUCCESS",
            file_type="PDF",
            source_filing_id="acc-1",
            country_code="US",
            form_type="10-K",
            fiscal_year=2023,
            reporting_date="2023-12-31",
        )
        assert resolve_gcs_path(record) == "rawdata/US/14778/2023/PDF_10-K_2023-12-31.pdf"

    def test_resolves_extension_from_file_type(self):
        """extension is NOT on the dataclass — resolve_gcs_path looks it up."""
        record = FileRecord(
            company_id=42,
            scraper_id="run-x",
            status="SUCCESS",
            file_type="XBRL",
            source_filing_id="acc-1",
            country_code="JP",
            form_type="ASR",
            fiscal_year=2024,
            reporting_date="2024-03-31",
        )
        # XBRL → .zip, never .xbrl
        assert resolve_gcs_path(record).endswith(".zip")

    def test_missing_fiscal_year_raises(self):
        record = FileRecord(
            company_id=42,
            scraper_id="run-x",
            status="PENDING",  # PENDING allows None fiscal_year
            file_type="PDF",
            source_filing_id="acc-1",
            country_code="US",
            form_type="10-K",
            fiscal_year=None,
            reporting_date="2023-12-31",
        )
        with pytest.raises(MissingFiscalYearError):
            resolve_gcs_path(record)

    def test_missing_reporting_date_raises_value_error(self):
        record = FileRecord(
            company_id=42,
            scraper_id="run-x",
            status="SUCCESS",
            file_type="PDF",
            source_filing_id="acc-1",
            country_code="US",
            form_type="10-K",
            fiscal_year=2023,
            reporting_date=None,
        )
        with pytest.raises(ValueError, match="reporting_date"):
            resolve_gcs_path(record)

    def test_missing_country_code_raises_value_error(self):
        record = FileRecord(
            company_id=42,
            scraper_id="run-x",
            status="SUCCESS",
            file_type="PDF",
            source_filing_id="acc-1",
            country_code=None,
            form_type="10-K",
            fiscal_year=2023,
            reporting_date="2023-12-31",
        )
        with pytest.raises(ValueError, match="country_code"):
            resolve_gcs_path(record)


# ---------------------------------------------------------------------------
# derive_fiscal_year
# ---------------------------------------------------------------------------


class TestDeriveFiscalYear:
    @pytest.mark.parametrize(
        "date,expected",
        [
            # H2 (Jul–Dec): fiscal year matches calendar year.
            ("2023-07-01", 2023),
            ("2023-07-31", 2023),
            ("2023-09-30", 2023),
            ("2023-12-31", 2023),
            # H1 (Jan–Jun): previous calendar year.
            ("2023-01-01", 2022),
            ("2023-03-31", 2022),
            ("2023-06-30", 2022),
            # Year-boundary spot checks.
            ("2024-01-01", 2023),
            ("2024-01-31", 2023),
            ("2024-06-30", 2023),
            ("2024-07-01", 2024),
        ],
    )
    def test_boundary_cases(self, date, expected):
        assert derive_fiscal_year(date) == expected

    @pytest.mark.parametrize(
        "bad",
        [
            None,
            "",
            "   ",
            "2023/12/31",
            "31-12-2023",
            "2023-13-01",  # month out of range
            "2023-00-15",  # month out of range
        ],
    )
    def test_malformed_raises(self, bad):
        with pytest.raises(ValueError):
            derive_fiscal_year(bad)
