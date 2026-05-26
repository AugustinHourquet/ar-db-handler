"""Tests for the metrics.db write helper (stub)."""

from __future__ import annotations

import uuid

import pytest

from ar_db_handler import get_metric, write_metric


class TestWriteMetric:
    def test_returns_uuid_when_none_provided(self, metrics_db):
        eid = write_metric(metrics_db, file_id="deadbeef0000")
        # Must be a valid UUID and the returned id must match the stored row.
        uuid.UUID(eid)
        row = get_metric(metrics_db, eid)
        assert row is not None
        assert row["file_id"] == "deadbeef0000"

    def test_explicit_evaluation_id_used(self, metrics_db):
        eid = write_metric(metrics_db, file_id="x", evaluation_id="my-fixed-id")
        assert eid == "my-fixed-id"
        row = get_metric(metrics_db, "my-fixed-id")
        assert row is not None
        assert row["file_id"] == "x"

    def test_get_metric_returns_none_for_missing(self, metrics_db):
        assert get_metric(metrics_db, "nope") is None

    def test_unknown_column_kwarg_raises_operational_error(self, metrics_db):
        """Schema-drift safety: unknown columns aren't silently dropped."""
        import sqlite3

        with pytest.raises(sqlite3.OperationalError):
            write_metric(metrics_db, file_id="x", undefined_column=42)
