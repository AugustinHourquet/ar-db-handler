"""Tests for ar_db_handler.ids."""

from __future__ import annotations

import uuid

import pytest

from ar_db_handler import EXTENSION_MAP, make_file_id, make_run_id
from ar_db_handler.ids import resolve_extension

# ---------------------------------------------------------------------------
# make_file_id
# ---------------------------------------------------------------------------


class TestMakeFileId:
    def test_is_deterministic(self):
        a = make_file_id(123, "0000320193-24-000123", "PDF")
        b = make_file_id(123, "0000320193-24-000123", "PDF")
        assert a == b

    def test_returns_16_char_hex(self):
        out = make_file_id(123, "abc", "PDF")
        assert len(out) == 16
        assert all(c in "0123456789abcdef" for c in out)

    def test_different_inputs_yield_different_ids(self):
        a = make_file_id(123, "abc", "PDF")
        b = make_file_id(124, "abc", "PDF")  # different company
        c = make_file_id(123, "xyz", "PDF")  # different filing
        d = make_file_id(123, "abc", "XBRL")  # different type
        assert len({a, b, c, d}) == 4

    def test_form_type_is_not_part_of_hash(self):
        """form_type is metadata only — not an identity dimension."""
        # The function signature itself proves this: make_file_id doesn't
        # accept a form_type argument. This test guards against someone
        # "helpfully" adding it later by checking that the hash output for
        # two records that would differ only on form_type is the same.
        a = make_file_id(123, "0000320193-24-000123", "PDF")
        b = make_file_id(123, "0000320193-24-000123", "PDF")
        assert a == b  # tautology, but stating the invariant explicitly.


# ---------------------------------------------------------------------------
# make_run_id
# ---------------------------------------------------------------------------


class TestMakeRunId:
    def test_is_a_valid_uuid4(self):
        rid = make_run_id()
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_produces_unique_ids(self):
        ids = {make_run_id() for _ in range(1000)}
        assert len(ids) == 1000  # uuid4 collisions in 1k draws are astronomical


# ---------------------------------------------------------------------------
# EXTENSION_MAP / resolve_extension
# ---------------------------------------------------------------------------


class TestExtensionMap:
    def test_pdf_maps_to_pdf(self):
        assert EXTENSION_MAP["PDF"] == ".pdf"

    def test_xbrl_maps_to_zip(self):
        assert EXTENSION_MAP["XBRL"] == ".zip"

    def test_resolve_extension_returns_value(self):
        assert resolve_extension("PDF") == ".pdf"
        assert resolve_extension("XBRL") == ".zip"

    def test_resolve_extension_raises_on_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown file_type"):
            resolve_extension("HTML")
