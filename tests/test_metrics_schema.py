"""Schema-level tests for metrics.db."""

from __future__ import annotations

import sqlite3

import pytest


def test_tables_created(metrics_db):
    rows = metrics_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert {"evaluations", "evaluation_scores_by_statement"} <= names


def test_wal_mode_is_on(metrics_db):
    mode = metrics_db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_fk_from_scores_to_evaluations_enforced(metrics_db):
    # Inserting a score row for a non-existent evaluation_id must fail.
    with pytest.raises(sqlite3.IntegrityError):
        metrics_db.execute(
            """
            INSERT INTO evaluation_scores_by_statement (
                evaluation_id, statement,
                coverage, precision, recall, f1,
                exact_match_rate, within_1pct_rate, within_5pct_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("nonexistent", "IncomeStatement", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        )
        metrics_db.commit()


def test_idempotent_init(tmp_path):
    from ar_db_handler import init_metrics_db

    path = tmp_path / "metrics.db"
    c1 = init_metrics_db(path)
    c1.close()
    c2 = init_metrics_db(path)
    c2.close()
