"""Tests for the metrics.db schema (stub)."""

from __future__ import annotations


class TestMetricsSchema:
    def test_metrics_table_exists(self, metrics_db):
        rows = metrics_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metrics'"
        ).fetchall()
        assert len(rows) == 1

    def test_evaluation_id_is_pk(self, metrics_db):
        cols = metrics_db.execute("PRAGMA table_info(metrics)").fetchall()
        # PRAGMA returns: cid, name, type, notnull, dflt_value, pk
        col_by_name = {c[1]: c for c in cols}
        assert col_by_name["evaluation_id"][5] == 1  # pk flag

    def test_file_id_column_present(self, metrics_db):
        cols = metrics_db.execute("PRAGMA table_info(metrics)").fetchall()
        names = [c[1] for c in cols]
        assert "file_id" in names

    def test_wal_mode_enabled(self, metrics_db):
        mode = metrics_db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_enabled(self, metrics_db):
        # No FKs in metrics.db today, but the pragma is on for consistency
        # with filings.db (and in case metrics grows local FKs later).
        fk = metrics_db.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
