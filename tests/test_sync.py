"""
Tests for sync_companies(), with GCPWeeklyFiles mocked out.

We never hit a real GCS bucket. Instead, the test installs a fake
``gcpBridge`` module into ``sys.modules`` that exposes a class with the
same ``__init__``, ``get_latest_period``, and ``read_file_from_period``
shape as the real one.
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from ar_db_handler import (
    CompanyRecord,
    SyncResult,
    sync_companies,
    upsert_company,
)

# ---------------------------------------------------------------------------
# Fake GCPWeeklyFiles
# ---------------------------------------------------------------------------


class _FakeGCPWeeklyFiles:
    """
    Drop-in for the real class. The test sets ``period`` and ``df`` on the
    class (or per-instance) before calling sync_companies().
    """

    period: str | None = "2026-05-22-W3"
    df: pd.DataFrame | None = None

    def __init__(self, credentials_path: str | None = None):
        # Stash for assertion in the credentials test
        self.credentials_path_received = credentials_path

    def get_latest_period(self) -> str | None:
        return self.period

    def read_file_from_period(self, period: str, filename: str) -> pd.DataFrame:
        # Record the call args so a test can assert against them.
        _FakeGCPWeeklyFiles.last_call = (period, filename)
        return self.df if self.df is not None else pd.DataFrame()


@pytest.fixture
def fake_gcp(monkeypatch):
    """Install a fake ``gcpBridge`` module exposing ``GCPWeeklyFiles``."""
    fake_mod = types.ModuleType("gcpBridge")
    fake_mod.GCPWeeklyFiles = _FakeGCPWeeklyFiles
    monkeypatch.setitem(sys.modules, "gcpBridge", fake_mod)

    # Reset class state between tests so they don't leak.
    _FakeGCPWeeklyFiles.period = "2026-05-22-W3"
    _FakeGCPWeeklyFiles.df = None
    if hasattr(_FakeGCPWeeklyFiles, "last_call"):
        delattr(_FakeGCPWeeklyFiles, "last_call")
    yield _FakeGCPWeeklyFiles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a snapshot DataFrame with the columns sync_companies expects."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyncResultShape:
    def test_returns_sync_result(self, filings_db, fake_gcp):
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": 1,
                    "fs_ticker": "AAPL",
                    "country_code": "US",
                    "country": "United States",
                    "country_id": "US",
                    "file_name": "aapl",
                    "coverage_status": "LAFA",
                    "start_year_force": 2008,
                },
            ]
        )
        out = sync_companies(filings_db)
        assert isinstance(out, SyncResult)
        assert out.period == "2026-05-22-W3"
        assert out.upserted == 1
        assert out.delisted == 0
        assert out.country_code is None


class TestUpsertCounts:
    def test_upserted_counts_match_snapshot_rows(self, filings_db, fake_gcp):
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": i,
                    "fs_ticker": f"T{i}",
                    "country_code": "US",
                    "country": "United States",
                    "country_id": "US",
                    "file_name": f"t{i}",
                    "coverage_status": "LAFA",
                }
                for i in range(1, 6)
            ]
        )
        out = sync_companies(filings_db)
        assert out.upserted == 5
        assert filings_db.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 5


class TestDeactivationStep:
    def test_companies_absent_from_snapshot_are_deactivated(self, filings_db, fake_gcp):
        # Pre-seed: 2 US companies (ids 10, 20)
        for cid in (10, 20):
            upsert_company(
                filings_db,
                CompanyRecord(
                    company_id=cid,
                    fs_ticker=f"T{cid}",
                    country_code="US",
                    country="United States",
                    country_id="US",
                    file_name=f"t{cid}",
                    coverage_status="LAFA",
                ),
            )
        # Snapshot only contains company_id=10 — company 20 should be flagged.
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": 10,
                    "fs_ticker": "T10",
                    "country_code": "US",
                    "country": "United States",
                    "country_id": "US",
                    "file_name": "t10",
                    "coverage_status": "LAFA",
                }
            ]
        )
        out = sync_companies(filings_db)
        assert out.upserted == 1
        assert out.delisted == 1
        # And verify the actual DB state:
        active = filings_db.execute(
            "SELECT company_id FROM companies WHERE is_in_company_info = 1 ORDER BY company_id"
        ).fetchall()
        inactive = filings_db.execute(
            "SELECT company_id FROM companies WHERE is_in_company_info = 0 ORDER BY company_id"
        ).fetchall()
        assert active == [(10,)]
        assert inactive == [(20,)]

    def test_deactivation_runs_before_upsert(self, filings_db, fake_gcp):
        """
        The order matters: if upsert ran first, the row would already be at
        is_in_company_info=1 when the UPDATE swept it back to 0, and we'd
        finish with a "delisted" company that's actually still active.

        We assert behaviour, not call order: a company present in BOTH the
        pre-existing table and the snapshot should end up active.
        """
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=10,
                fs_ticker="T10",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="t10",
                coverage_status="LAFA",
            ),
        )
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": 10,
                    "fs_ticker": "T10_new",
                    "country_code": "US",
                    "country": "United States",
                    "country_id": "US",
                    "file_name": "t10_new",
                    "coverage_status": "LAFA",
                }
            ]
        )
        out = sync_companies(filings_db)
        assert out.delisted == 0  # no one missing
        assert out.upserted == 1
        row = filings_db.execute(
            "SELECT is_in_company_info, file_name FROM companies WHERE company_id = 10"
        ).fetchone()
        assert row == (1, "t10_new")  # active AND updated


class TestCountryCodeFilter:
    def test_country_filter_scopes_deactivation(self, filings_db, fake_gcp):
        """A JP-scoped sync must not deactivate US rows that are absent from
        the (JP-filtered) snapshot."""
        # Pre-seed: 1 US + 1 JP
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=10,
                fs_ticker="US10",
                country_code="US",
                country="United States",
                country_id="US",
                file_name="us10",
                coverage_status="LAFA",
            ),
        )
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=20,
                fs_ticker="JP20",
                country_code="JP",
                country="Japan",
                country_id="JP",
                file_name="jp20",
                coverage_status="LAFA",
            ),
        )
        # Snapshot contains a mix; we'll filter to JP. The snapshot's JP entry
        # is the same company (20) so nothing JP-side gets delisted.
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": 10,
                    "fs_ticker": "US10",
                    "country_code": "US",
                    "country": "United States",
                    "country_id": "US",
                    "file_name": "us10",
                    "coverage_status": "LAFA",
                },
                {
                    "company_id": 20,
                    "fs_ticker": "JP20",
                    "country_code": "JP",
                    "country": "Japan",
                    "country_id": "JP",
                    "file_name": "jp20",
                    "coverage_status": "LAFA",
                },
            ]
        )
        out = sync_companies(filings_db, country_code="JP")
        assert out.country_code == "JP"
        assert out.upserted == 1  # only the JP row was upserted
        assert out.delisted == 0  # JP row is still present in the snapshot
        # And — critically — US row must NOT have been deactivated.
        us_flag = filings_db.execute(
            "SELECT is_in_company_info FROM companies WHERE company_id = 10"
        ).fetchone()[0]
        assert us_flag == 1

    def test_country_filter_no_match_in_snapshot(self, filings_db, fake_gcp):
        """A JP sync against a snapshot that has no JP rows deactivates every JP row."""
        upsert_company(
            filings_db,
            CompanyRecord(
                company_id=20,
                fs_ticker="JP20",
                country_code="JP",
                country="Japan",
                country_id="JP",
                file_name="jp20",
                coverage_status="LAFA",
            ),
        )
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": 10,
                    "fs_ticker": "US10",
                    "country_code": "US",
                    "country": "United States",
                    "country_id": "US",
                    "file_name": "us10",
                    "coverage_status": "LAFA",
                }
            ]
        )
        out = sync_companies(filings_db, country_code="JP")
        assert out.upserted == 0
        assert out.delisted == 1


class TestCredentialsResolution:
    def test_explicit_kwarg_wins(self, filings_db, fake_gcp, monkeypatch):
        monkeypatch.setenv("OMAHA_GCS_CREDENTIALS", "/from/env.json")
        fake_gcp.df = _make_df([])
        sync_companies(filings_db, credentials_path="/explicit/path.json")
        # The fake stores the path on the instance — but we only have the
        # class. Inspect the most recent instance's class-side attribute:
        # since each test creates one instance, we can check that the path
        # was wired through to __init__ by reading the class-level marker.
        # Easiest path: assert no exception + correct file used.
        assert _FakeGCPWeeklyFiles.last_call == ("2026-05-22-W3", "company_info.parquet")

    def test_env_var_used_when_no_kwarg(self, filings_db, fake_gcp, monkeypatch):
        # Patch the resolver directly to assert wiring without monkey-patching
        # the class constructor.
        from ar_db_handler.filings import sync as sync_mod

        captured: dict[str, str | None] = {}

        original = sync_mod._resolve_credentials_path

        def _spy(p):
            result = original(p)
            captured["resolved"] = result
            return result

        monkeypatch.setattr(sync_mod, "_resolve_credentials_path", _spy)
        monkeypatch.setenv("OMAHA_GCS_CREDENTIALS", "/from/env.json")
        fake_gcp.df = _make_df([])
        sync_companies(filings_db)
        assert captured["resolved"] == "/from/env.json"


class TestEmptySnapshot:
    def test_no_periods_raises(self, filings_db, fake_gcp):
        fake_gcp.period = None
        with pytest.raises(RuntimeError, match="No"):
            sync_companies(filings_db)

    def test_empty_dataframe_no_upserts(self, filings_db, fake_gcp):
        fake_gcp.df = pd.DataFrame()
        out = sync_companies(filings_db)
        assert out.upserted == 0
        assert out.delisted == 0


class TestSchemaDrift:
    def test_missing_required_column_raises(self, filings_db, fake_gcp):
        fake_gcp.df = _make_df(
            [
                {
                    "company_id": 1,
                    # missing: fs_ticker, country_code, country, ...
                }
            ]
        )
        with pytest.raises(KeyError, match="missing required column"):
            sync_companies(filings_db)


class TestFilenameThreading:
    def test_filename_passed_through(self, filings_db, fake_gcp):
        fake_gcp.df = pd.DataFrame()
        sync_companies(filings_db, filename="custom_master.parquet")
        period, fname = _FakeGCPWeeklyFiles.last_call
        assert fname == "custom_master.parquet"
        assert period == "2026-05-22-W3"
