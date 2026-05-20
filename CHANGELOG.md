# Changelog

All notable changes to `ar-db-handler` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-20

### Added
- Initial release.
- `filings.db` schema: `scraper_runs`, `companies`, `filings`, `filing_files`.
- `metrics.db` schema: `evaluations`, `evaluation_scores_by_statement`.
- Database initialisation helpers (`init_filings_db`, `init_metrics_db`)
  with WAL mode and FK pragma enforced.
- Write helpers for filings: `upsert_run`, `upsert_worker`, `upsert_company`,
  `upsert_filing`, `upsert_filing_file` (with `AlreadyScrapedError` and
  `force=True` override).
- Write helpers for metrics: `write_evaluation`,
  `write_evaluation_scores_by_statement`.
- Read helpers: `get_filing`, `get_filing_file`, `get_scraped_pairs`,
  `list_companies`.
- Lightweight dataclass records for every table.
- Test suite covering schema, upsert rules, FK enforcement, and queries.
