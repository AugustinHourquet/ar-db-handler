"""Lightweight dataclass records for each database table.

Not an ORM. These exist purely as structured payloads passed to the
write helpers — callers build them explicitly, the writers read the
fields and bind them to parameterised SQL.

Field types mirror the column types of the underlying SQL schema. Dates
and datetimes are passed as ISO-formatted strings (this is what SQLite
expects for its `DATE` / `DATETIME` storage classes) so the caller stays
in control of timezone semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# filings.db
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    """Parent row in `scraper_runs` (worker_id IS NULL).

    `config` is a JSON-serialised string (the caller decides what goes
    in it); `worker_count` is the number of worker rows that will be
    attached to this run.
    """

    run_id: str
    country: str | None
    started_at: str | None
    finished_at: str | None
    status: str  # RUNNING | SUCCESS | FAILED
    config: str | None
    worker_count: int | None
    parent_run_id: str | None = None


@dataclass
class WorkerRecord:
    """Worker row in `scraper_runs` (country IS NULL, config IS NULL)."""

    run_id: str
    worker_id: int
    started_at: str | None
    finished_at: str | None
    status: str  # RUNNING | SUCCESS | FAILED
    files_scraped: int = 0
    parent_run_id: str | None = None


@dataclass
class CompanyRecord:
    company_id: str
    name: str | None
    ticker: str | None
    exchange: str | None
    country: str | None
    updated_at: str | None


@dataclass
class FilingRecord:
    filing_id: str
    company_id: str
    fiscal_year: int
    filing_date: str | None
    reporting_date: str | None
    reporting_period: str | None


@dataclass
class FilingFileRecord:
    file_id: str
    filing_id: str
    run_id: str
    worker_id: int | None
    file_type: str  # PDF | XBRL | ...
    form_type: str | None  # 10-K | 10-K405 | 10-KSB | ...
    gcs_path: str | None
    url: str | None
    scrape_status: str  # PENDING | SCRAPED | FAILED
    scraped_at: str | None


# ---------------------------------------------------------------------------
# metrics.db
# ---------------------------------------------------------------------------


@dataclass
class EvaluationRecord:
    """Mirrors the `evaluations` table column-for-column.

    `scope`, `output_json`, and `output_diff` are pre-serialised strings
    — the caller is responsible for `json.dumps` on these.
    """

    evaluation_id: str
    filing_id: str | None
    company_id: str | None
    fiscal_year: int | None
    evaluated_at: str | None
    pdf_source: str | None
    xbrl_source: str | None
    scope: str | None  # JSON array of statement names (already serialised)
    xbrl_facts_scope: int | None
    pdf_facts_scope: int | None
    matched: int | None
    missed: int | None
    spurious: int | None
    tier1_matches: int | None
    tier2_matches: int | None
    coverage: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    exact_match_rate: float | None
    within_1pct_rate: float | None
    within_5pct_rate: float | None
    output_json: str | None
    output_diff: str | None


@dataclass
class StatementScoreRecord:
    """A row in `evaluation_scores_by_statement`.

    `id` is omitted — it is an autoincrement primary key assigned by
    SQLite.
    """

    evaluation_id: str
    statement: str  # IncomeStatement | BalanceSheet | CashFlow | Note_PPE
    coverage: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    exact_match_rate: float | None
    within_1pct_rate: float | None
    within_5pct_rate: float | None


# ---------------------------------------------------------------------------
# Query result types
# ---------------------------------------------------------------------------


@dataclass
class ScrapedPair:
    """A filing for which both PDF and XBRL have status SCRAPED.

    This is the primary unit of work consumed by the evaluator.
    """

    filing_id: str
    company_id: str
    fiscal_year: int
    pdf_gcs_path: str
    xbrl_gcs_path: str
