"""Write helpers for metrics.db.

`write_evaluation` inserts a row into the `evaluations` table.
`write_evaluation_scores_by_statement` inserts one row per statement
into `evaluation_scores_by_statement`.

Both functions use `INSERT` (not `INSERT OR REPLACE`) — if the
evaluation_id already exists, the underlying UNIQUE / PRIMARY KEY
constraint will raise. Callers that want idempotent re-runs should
either delete the prior rows or use a fresh `evaluation_id` per run.
This keeps the metric table append-only by default, which is the safer
choice for evaluation results.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence

from ..records import EvaluationRecord, StatementScoreRecord

logger = logging.getLogger(__name__)


def write_evaluation(conn: sqlite3.Connection, record: EvaluationRecord) -> None:
    """Insert a row into the `evaluations` table.

    Raises
    ------
    sqlite3.IntegrityError
        If a row with the same `evaluation_id` already exists.
    """
    conn.execute(
        """
        INSERT INTO evaluations (
            evaluation_id, filing_id, company_id, fiscal_year, evaluated_at,
            pdf_source, xbrl_source, scope,
            xbrl_facts_scope, pdf_facts_scope,
            matched, missed, spurious,
            tier1_matches, tier2_matches,
            coverage, precision, recall, f1,
            exact_match_rate, within_1pct_rate, within_5pct_rate,
            output_json, output_diff
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?
        )
        """,
        (
            record.evaluation_id,
            record.filing_id,
            record.company_id,
            record.fiscal_year,
            record.evaluated_at,
            record.pdf_source,
            record.xbrl_source,
            record.scope,
            record.xbrl_facts_scope,
            record.pdf_facts_scope,
            record.matched,
            record.missed,
            record.spurious,
            record.tier1_matches,
            record.tier2_matches,
            record.coverage,
            record.precision,
            record.recall,
            record.f1,
            record.exact_match_rate,
            record.within_1pct_rate,
            record.within_5pct_rate,
            record.output_json,
            record.output_diff,
        ),
    )
    conn.commit()


def write_evaluation_scores_by_statement(
    conn: sqlite3.Connection,
    records: Sequence[StatementScoreRecord],
) -> None:
    """Insert one row per statement-level score.

    The whole batch is committed atomically — either all rows are
    written or none. If the parent evaluation row doesn't exist, the FK
    constraint will raise `sqlite3.IntegrityError`.
    """
    if not records:
        return

    rows = [
        (
            r.evaluation_id,
            r.statement,
            r.coverage,
            r.precision,
            r.recall,
            r.f1,
            r.exact_match_rate,
            r.within_1pct_rate,
            r.within_5pct_rate,
        )
        for r in records
    ]

    conn.executemany(
        """
        INSERT INTO evaluation_scores_by_statement (
            evaluation_id, statement,
            coverage, precision, recall, f1,
            exact_match_rate, within_1pct_rate, within_5pct_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
