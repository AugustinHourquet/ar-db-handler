# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] — 2026-05-26

### Fixed

- `make clean` and `make clean-venv` failed on Windows with
  `CreateProcess … Le fichier spécifié est introuvable` because the
  recipes called Unix shell built-ins (`rm`, `find`, `touch`) that
  don't exist in `cmd.exe`. All file-system operations are now
  delegated to `scripts/make_helpers.py`, which uses `pathlib` /
  `shutil` and works identically on every OS. The non-FS targets
  (`format`, `lint`, `test`, `setup-check`) were already cross-platform
  via direct `.venv/Scripts/python` or `.venv/bin/python` invocation.

### Changed

- `make install` no longer guards venv creation with `test -d …` — the
  `python -m venv` module is itself idempotent, and `test` is not a
  cmd.exe built-in. Removing the guard is what lets a clean Windows
  install actually reach the `pip install` step.
- `make format` / `make lint` now also cover `scripts/`.

## [0.3.0] — 2026-05-26

### Changed (BREAKING)

- `FileRecord` no longer has a `fiscal_year_status` field. The
  `fiscal_year_status` column is removed from `files`. Callers that
  passed `fiscal_year_status="DERIVED"` or `"MISSING"` must drop that
  argument.
- A SUCCESS row MUST now carry a non-null `fiscal_year`. The reasoning:
  every regulator the pipeline targets (EDGAR `reportDate`, EDINET
  `periodEnd`, ...) exposes the period-end on filing metadata, so a
  successful scrape with no derivable year indicates a scraper bug, not
  a data limitation. This is enforced two ways:
  1. **Python**: `upsert_file()` raises the new `MissingFiscalYearError`
     before any INSERT.
  2. **SQL**: `CHECK (status != 'SUCCESS' OR fiscal_year IS NOT NULL)`
     catches direct INSERTs that bypass `upsert_file`.
     PENDING and FAILED rows may still have `fiscal_year = NULL`.

### Added

- New `scraper_errors` table — a dedicated audit area for rejected
  upserts and system-level failures. Schema includes `error_id`,
  `scraper_id`, `error_type`, `error_message`, `company_id`,
  `source_filing_id`, `file_type`, `payload` (JSON), `recorded_at`.
- New helpers `record_error(conn, ErrorRecord)` and
  `get_scraper_errors(conn, scraper_id=..., error_type=..., limit=...)`.
- New `ErrorRecord` dataclass.
- New exception base class `ArDbHandlerError` (parent of
  `AlreadyScrapedError` and `MissingFiscalYearError`).
- New `MissingFiscalYearError` exception.
- Error-type string constants for stable SQL-side filtering:
  `ERROR_UNKNOWN_FILE_TYPE`, `ERROR_MISSING_FISCAL_YEAR`,
  `ERROR_ALREADY_SCRAPED`, `ERROR_FK_VIOLATION`,
  `ERROR_CHECK_VIOLATION`, `ERROR_SNAPSHOT_SCHEMA_DRIFT`,
  `ERROR_SYNC_NO_PERIOD`.
- `SYSTEM_SCRAPER_ID` sentinel (`"SYSTEM"`) for errors that don't
  belong to a scraper run (sync failures, ad-hoc scripts).
- Auto-recording wiring in every helper that rejects a row:
  - `upsert_file()` records `UNKNOWN_FILE_TYPE`, `MISSING_FISCAL_YEAR`,
    `ALREADY_SCRAPED`, `FK_VIOLATION`, `CHECK_VIOLATION` before raising.
  - `sync_companies()` records `SYNC_NO_PERIOD` and
    `SNAPSHOT_SCHEMA_DRIFT` before raising (with `SYSTEM` scraper_id).

### Notes

- The recording path is best-effort: a failure in `record_error()`
  itself is logged at WARNING and silently swallowed. This keeps it
  safe to call from inside an `except` block — a second exception
  there would mask the one the caller is trying to report.
- Test count: 77 → 100 (+23, all green).

## [0.1.0] — 2026-05-22

### Added

- Initial release.
- `filings.db` schema: `companies`, `scraper_runs`, `files` tables with
  WAL mode and foreign-key constraints enforced via pragma.
- `metrics.db` schema: `metrics` table stub (columns TBD).
- `init_filings_db(path)` and `init_metrics_db(path)` connection helpers.
- ID generation in `ids.py`:
  - `make_run_id()` — UUID4 string for ephemeral scraper runs.
  - `make_file_id(company_id, source_filing_id, file_type)` — deterministic
    16-char SHA-256 prefix derived from the natural uniqueness key.
- `EXTENSION_MAP` — `PDF → .pdf`, `XBRL → .zip`.
- Filings write helpers:
  - `upsert_file(conn, record, force=False)` — resolves `file_id`,
    normalises `form_type` (`None`/`""` → `'UNKNOWN'`), resolves
    `extension`, sets `fiscal_year_status`, raises `AlreadyScrapedError`
    when a SUCCESS row exists and `force=False`.
  - `upsert_run(conn, record)` — `INSERT OR IGNORE`.
  - `update_run_finished(...)` — updates `finished_at`, `elapsed_time`,
    `status` and the four count columns at run end.
  - `upsert_company(conn, record)` — `INSERT OR REPLACE`, always sets
    `last_synced_at` to `datetime.utcnow().isoformat()` and
    `is_in_company_info = 1`.
- `sync_companies(conn, country_code=None, credentials_path=None, filename=...)`:
  pulls the latest snapshot from `GCPWeeklyFiles`, deactivates rows
  (`is_in_company_info = 0`) within the scope before upserting, then
  upserts every row from the snapshot. Returns a `SyncResult`.
- Filings read helpers (`queries/filings.py`):
  - `get_file(conn, file_id)`
  - `get_scraped_files(conn, country_code=None, company_id=None)` —
    skip-set as `set[tuple[int, str, str]]`.
  - `get_scraped_pairs(conn, company_id=None, fiscal_year=None)` —
    every SUCCESS PDF/XBRL pair, no priority filtering applied.
  - `list_companies(conn, country_code=None, active_only=True)`.
- Metrics write helper stub (`metrics/writer.py`): `write_metric()`.
- Public API re-exports in `ar_db_handler.__init__`.
- Test suite: `test_ids.py`, `test_filings_schema.py`,
  `test_filings_upserts.py`, `test_sync.py`, `test_queries.py`,
  `test_metrics_schema.py`, `test_metrics_writer.py`.
- Makefile with venv bootstrap, idempotent install via stamp file, and
  `format` / `lint` / `test` / `setup-check` / `pre-commit-install`
  targets that all call the venv's Python directly.
- `.env.example` documenting `OMAHA_GCS_CREDENTIALS`.
- README covering usage, the two databases, the fiscal-year derivation
  chain, amendment handling, and the expected caller patterns.
