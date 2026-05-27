# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] — 2026-05-27

### Added

- `scripts/init_companies_table.py` — one-off script to initialise the
  `companies` table for a given country via `sync_companies()`.
- `_COUNTRY_NAME_TO_CODE` mapping in `sync.py` — translates GCP
  `Country_Name` values (uppercase, e.g. `"UNITED STATES"`) to ISO
  country codes (`"US"`). Used both for filtering the snapshot and for
  populating the `country_code` DB column, which the GCP file does not
  carry directly.

### Changed

- `sync_companies()` now resolves the `gcpBridge` module via a local
  file path rather than a package import. The path to `gcpBridge.py`
  (a private file in the `omaha_norma` project, not on PyPI) is read
  from `OMAHA_GCP_BRIDGE_PATH` in `.env`. A second variable
  `OMAHA_NORMA_SRC_PATH` points to the `omaha_norma/src` directory so
  that `gcpBridge`'s own imports resolve correctly. Neither path is
  committed to git — both live only in the local `.env`.
- GCP snapshot column names are now explicitly mapped to DB column names
  via `_GCP_COLUMN_RENAMES`:

  | GCP column        | DB column          |
  |-------------------|--------------------|
  | `CompanyID`       | `company_id`       |
  | `FactSet Ticker`  | `fs_ticker`        |
  | `fileName`        | `file_name`        |
  | `Coverage_Status` | `coverage_status`  |
  | `Country_Name`    | `country`          |
  | `StartYearForce`  | `start_year_force` |
  | `country_id`      | `country_id`       |

- The `country_code` DB column is now **derived** from `Country_Name`
  via `_COUNTRY_NAME_TO_CODE` after the rename step. The GCP
  `country_id` column (a numeric internal ID) is stored as-is for
  internal cross-referencing.
- The country filter in `sync_companies()` now operates on `Country_Name`
  (the GCP column, pre-rename) rather than `country_code`. The caller
  still passes a country code (e.g. `"US"`); the function resolves it to
  the corresponding country name (`"UNITED STATES"`) via
  `_COUNTRY_CODE_TO_NAME` before filtering.
- Default `filename` parameter of `sync_companies()` corrected from
  `"company_info.parquet"` to `"companyInfo.parquet"` (actual GCP filename).
- Default value for `start_year_force` changed from `2008` to `2006`
  across `sync.py`, `_models.py`, and `schema.sql`. GCP rows with a
  null `StartYearForce` fall back to `2006`.
- `.env.example` updated with `OMAHA_GCP_BRIDGE_PATH` and
  `OMAHA_NORMA_SRC_PATH` variables.

### Tests

- All fake GCP DataFrames in `test_sync.py` updated to use GCP column
  names (`CompanyID`, `FactSet Ticker`, `Country_Name`, `fileName`,
  `Coverage_Status`) via a new `_gcp_row()` helper, matching the
  real snapshot format.
- `country_id` removed from `CompanyRecord` seeds in tests (now `None`
  throughout, consistent with the new sync behaviour).
- `TestSchemaDrift.test_missing_required_column_raises` updated to
  supply a minimal GCP-format row.

## [0.4.0] — 2026-05-26

> Version jump from 0.2.1 → 0.4.0 to align with the `gcs-handler` 0.3.x
> release; no 0.3.x exists for `ar-db-handler`.

### Added

- New module `ar_db_handler.paths` with three pure functions (no DB,
  no I/O, no `gcs-handler` dependency):
  - `make_blob_path(country_code, company_id, fiscal_year, file_type,
    form_type, reporting_date, extension)` — pure path builder.
  - `resolve_gcs_path(record)` — convenience wrapper over a
    `FileRecord` (resolves `extension` from `file_type` via
    `EXTENSION_MAP`).
  - `derive_fiscal_year(reporting_date)` — H2/H1 fiscal-year rule
    helper for scrapers building `FileRecord`s.
- Canonical GCS blob-path scheme:
  `rawdata/{country_code}/{company_id}/{fiscal_year}/{file_type}_{form_type}_{reporting_date}{extension}`.
- `ERROR_MISSING_REPORTING_DATE` error-type constant.
- `tests/test_paths.py` — 51 new tests covering the path builder,
  the FileRecord wrapper, validation messages, and the H2/H1 boundary
  cases.
- 6 new tests in `tests/test_filings_upserts.py` covering the
  `upsert_file()` auto-fill behaviour.

### Changed

- `upsert_file()` now auto-fills `country_code` (from the `companies`
  table) and `gcs_path` (via `resolve_gcs_path`) on SUCCESS rows when
  the caller leaves them unset. Existing callers that already pass
  these values are unaffected — caller-supplied values always win.
  PENDING and FAILED rows are unchanged. Two new pre-flight steps in
  the helper:
  1. Pre-flight 3 (between fiscal_year invariant and SUCCESS guard):
     resolve `country_code` from `companies`. A missing company
     records `ERROR_FK_VIOLATION` and raises `IntegrityError`.
  2. Pre-flight 4: resolve `gcs_path` on SUCCESS rows. A missing
     `reporting_date` records `ERROR_MISSING_REPORTING_DATE` and
     raises `ValueError`.
- `FileRecord` field ordering: mandatory fields first, optional /
  auto-fillable fields after, each with a `= None` default. The
  fields themselves are unchanged in identity and persistence —
  `country_code` and `reporting_date` were already on the dataclass
  and the schema, just mandatory. They are now optional at
  construction time so callers can let `upsert_file` fill them in.
  All existing call sites use kwargs, so this is backward-compatible.
- Bumped version to `0.4.0` in both `pyproject.toml` and
  `ar_db_handler.__version__`.

### Notes

- Test count: 100 → 157 (+57, all green).
- No schema migration. The `files` table is unchanged.
- No new runtime dependencies. `paths.py` uses only the stdlib.
- No GCS calls in tests. Tests assert path *strings*, not GCS state.

## [0.2.1] — 2026-05-26

### Fixed
- `make clean` and `make clean-venv` failed on Windows with
  ``CreateProcess … Le fichier spécifié est introuvable`` because the
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

## [0.2.0] — 2026-05-26

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
