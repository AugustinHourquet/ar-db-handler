"""Write-helper tests for metrics.db."""

from __future__ import annotations

import sqlite3

import pytest

from ar_db_handler import (
    EvaluationRecord,
    StatementScoreRecord,
    write_evaluation,
    write_evaluation_scores_by_statement,
)


def _eval(evaluation_id: str = "e-1") -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_id=evaluation_id,
        filing_id="f-1",
        company_id="C001",
        fiscal_year=2024,
        evaluated_at="2026-02-01T00:00:00",
        pdf_source="gs://b/p.pdf",
        xbrl_source="gs://b/x.zip",
        scope='["IncomeStatement","BalanceSheet"]',
        xbrl_facts_scope=120,
        pdf_facts_scope=110,
        matched=100,
        missed=10,
        spurious=5,
        tier1_matches=80,
        tier2_matches=20,
        coverage=0.91,
        precision=0.95,
        recall=0.90,
        f1=0.92,
        exact_match_rate=0.85,
        within_1pct_rate=0.93,
        within_5pct_rate=0.97,
        output_json='{"x": 1}',
        output_diff="diff text",
    )


def test_write_evaluation_inserts(metrics_db):
    write_evaluation(metrics_db, _eval())
    row = metrics_db.execute("SELECT * FROM evaluations WHERE evaluation_id='e-1'").fetchone()
    assert row is not None
    assert row["company_id"] == "C001"
    assert row["matched"] == 100
    assert row["coverage"] == 0.91
    assert row["scope"] == '["IncomeStatement","BalanceSheet"]'


def test_write_evaluation_duplicate_id_raises(metrics_db):
    write_evaluation(metrics_db, _eval())
    with pytest.raises(sqlite3.IntegrityError):
        write_evaluation(metrics_db, _eval())


def test_write_evaluation_scores_by_statement(metrics_db):
    write_evaluation(metrics_db, _eval())
    write_evaluation_scores_by_statement(
        metrics_db,
        [
            StatementScoreRecord(
                evaluation_id="e-1",
                statement="IncomeStatement",
                coverage=0.9,
                precision=0.92,
                recall=0.91,
                f1=0.915,
                exact_match_rate=0.85,
                within_1pct_rate=0.93,
                within_5pct_rate=0.97,
            ),
            StatementScoreRecord(
                evaluation_id="e-1",
                statement="BalanceSheet",
                coverage=0.88,
                precision=0.9,
                recall=0.89,
                f1=0.895,
                exact_match_rate=0.83,
                within_1pct_rate=0.92,
                within_5pct_rate=0.96,
            ),
        ],
    )
    rows = metrics_db.execute(
        "SELECT statement, coverage FROM evaluation_scores_by_statement "
        "WHERE evaluation_id='e-1' ORDER BY statement"
    ).fetchall()
    assert [r["statement"] for r in rows] == ["BalanceSheet", "IncomeStatement"]
    assert rows[0]["coverage"] == 0.88


def test_write_evaluation_scores_empty_list_is_noop(metrics_db):
    write_evaluation(metrics_db, _eval())
    write_evaluation_scores_by_statement(metrics_db, [])
    n = metrics_db.execute("SELECT COUNT(*) AS n FROM evaluation_scores_by_statement").fetchone()[
        "n"
    ]
    assert n == 0


def test_score_row_requires_parent_evaluation(metrics_db):
    """FK to evaluations must be enforced when writing via the helper."""
    with pytest.raises(sqlite3.IntegrityError):
        write_evaluation_scores_by_statement(
            metrics_db,
            [
                StatementScoreRecord(
                    evaluation_id="missing",
                    statement="IncomeStatement",
                    coverage=1.0,
                    precision=1.0,
                    recall=1.0,
                    f1=1.0,
                    exact_match_rate=1.0,
                    within_1pct_rate=1.0,
                    within_5pct_rate=1.0,
                ),
            ],
        )
