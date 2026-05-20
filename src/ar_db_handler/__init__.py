"""ar_db_handler — SQLite data-access layer for the annual report pipeline.

Two databases live behind this package:

* `filings.db` — populated by scrapers, read by the evaluator
* `metrics.db` — populated by the evaluator

This module is intentionally *pure data access*: it knows nothing about
EDGAR, GCS, scraping, or evaluation logic. Every other module that
needs to read or write to these databases imports from here.

Public surface
--------------
Initialisation:
    init_filings_db, init_metrics_db

filings.db writes:
    upsert_run, upsert_worker, upsert_company,
    upsert_filing, upsert_filing_file
    AlreadyScrapedError

filings.db reads:
    get_filing, get_filing_file, get_scraped_pairs, list_companies

metrics.db writes:
    write_evaluation, write_evaluation_scores_by_statement

Record dataclasses (for callers building inputs):
    RunRecord, WorkerRecord, CompanyRecord, FilingRecord,
    FilingFileRecord, EvaluationRecord, StatementScoreRecord,
    ScrapedPair
"""

from __future__ import annotations

from .exceptions import AlreadyScrapedError
from .filings.init import init_filings_db
from .filings.upserts import (
    upsert_company,
    upsert_filing,
    upsert_filing_file,
    upsert_run,
    upsert_worker,
)
from .metrics.init import init_metrics_db
from .metrics.writer import (
    write_evaluation,
    write_evaluation_scores_by_statement,
)
from .queries.filings import (
    get_filing,
    get_filing_file,
    get_scraped_pairs,
    list_companies,
)
from .records import (
    CompanyRecord,
    EvaluationRecord,
    FilingFileRecord,
    FilingRecord,
    RunRecord,
    ScrapedPair,
    StatementScoreRecord,
    WorkerRecord,
)

__all__ = [
    # exceptions
    "AlreadyScrapedError",
    # init
    "init_filings_db",
    "init_metrics_db",
    # filings writes
    "upsert_run",
    "upsert_worker",
    "upsert_company",
    "upsert_filing",
    "upsert_filing_file",
    # filings reads
    "get_filing",
    "get_filing_file",
    "get_scraped_pairs",
    "list_companies",
    # metrics writes
    "write_evaluation",
    "write_evaluation_scores_by_statement",
    # records
    "RunRecord",
    "WorkerRecord",
    "CompanyRecord",
    "FilingRecord",
    "FilingFileRecord",
    "EvaluationRecord",
    "StatementScoreRecord",
    "ScrapedPair",
]

__version__ = "0.1.0"
