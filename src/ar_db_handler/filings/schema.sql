-- ===========================================================================
-- filings.db — schema
--
-- Populated by country-specific scrapers (US/EDGAR, JP/EDINET, ...) and read
-- by the evaluator. ar-db-handler is country-agnostic — no scraping or
-- evaluation logic lives here, only the storage layer.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS companies (
    company_id          INTEGER PRIMARY KEY,
    fs_ticker           TEXT NOT NULL,
    country_code        TEXT NOT NULL,                  -- US | JP | ...
    country             TEXT NOT NULL,                  -- United States | Japan | ...
    country_id          TEXT,
    file_name           TEXT NOT NULL,
    coverage_status     TEXT NOT NULL,                  -- LAFA | LANA | PARR | ...
    start_year_force    INTEGER DEFAULT 2008,
    is_in_company_info  INTEGER NOT NULL DEFAULT 1,     -- 1 = active in master pipeline, 0 = delisted/dropped
    last_synced_at      TEXT                            -- ISO datetime of last successful sync
);

CREATE TABLE IF NOT EXISTS scraper_runs (
    scraper_id      TEXT PRIMARY KEY,                   -- UUID via make_run_id()
    country_code    TEXT NOT NULL,
    workers_count   INTEGER DEFAULT 3,
    source_file     TEXT,                               -- local path to python script file
    log_path        TEXT,                               -- local or GCS path, decided at runtime
    version         TEXT,
    started_at      TEXT,                               -- ISO datetime
    finished_at     TEXT,                               -- ISO datetime
    elapsed_time    REAL,                               -- seconds as float
    status          TEXT NOT NULL,                      -- RUNNING | SUCCESS | FAILED
    scraped_files   INTEGER DEFAULT 0,
    xbrl_count      INTEGER DEFAULT 0,
    pdf_count       INTEGER DEFAULT 0,
    fail_count      INTEGER DEFAULT 0,
    metadata        TEXT                                -- JSON blob for any extra context
);

CREATE TABLE IF NOT EXISTS files (
    file_id            TEXT PRIMARY KEY,                -- deterministic hash via make_file_id()
    company_id         INTEGER NOT NULL REFERENCES companies(company_id),
    scraper_id         TEXT NOT NULL REFERENCES scraper_runs(scraper_id),
    status             TEXT NOT NULL,                   -- SUCCESS | FAILED | PENDING
    country_code       TEXT NOT NULL,                   -- US | JP | ...
    file_type          TEXT NOT NULL,                   -- PDF | XBRL
    extension          TEXT NOT NULL,                   -- .pdf for PDF, .zip for XBRL
    form_type          TEXT NOT NULL DEFAULT 'UNKNOWN', -- 10-K | 10-KA | 10-KSB | UNKNOWN (metadata only)
    source_filing_id   TEXT NOT NULL,                   -- regulator-assigned filing ID (EDGAR accession no, EDINET docID, ...)
    fiscal_year        INTEGER,                         -- derived from reporting_date; NOT NULL when status='SUCCESS' (CHECK below)
    reporting_date     TEXT,                            -- ISO date — the period-end the filing covers; sole source for fiscal_year
    filing_date        TEXT,                            -- ISO date — submission date, NEVER used to derive fiscal_year
    gcs_path           TEXT,                            -- NULL if status = FAILED
    url                TEXT,
    scraped_at         TEXT,                            -- ISO datetime
    error_message      TEXT,                            -- NULL if status = SUCCESS

    -- One authoritative row per (company, source filing ID, file type).
    -- source_filing_id is the regulator-assigned unique identifier for the
    -- filing (accession number for EDGAR, docID for EDINET, etc.) —
    -- fully country-agnostic and requires zero derivation. form_type is
    -- metadata only and does not participate in the unique constraint.
    UNIQUE (company_id, source_filing_id, file_type),

    -- A SUCCESS row MUST carry a resolved fiscal_year. The reporting_date
    -- is always available from the source API (EDGAR reportDate, EDINET
    -- periodEnd, ...), so a SUCCESS row without fiscal_year indicates a
    -- scraper bug rather than a data limitation. PENDING and FAILED rows
    -- may have NULL fiscal_year — they represent in-flight or unrecoverable
    -- work and don't need a resolved year.
    CHECK (status != 'SUCCESS' OR fiscal_year IS NOT NULL)
);

-- Indexes for the hot query paths (skip-set lookups, pair joins, country scoping).
CREATE INDEX IF NOT EXISTS idx_files_status_country
    ON files (status, country_code);

CREATE INDEX IF NOT EXISTS idx_files_company_fy_type
    ON files (company_id, fiscal_year, file_type);

CREATE INDEX IF NOT EXISTS idx_companies_country
    ON companies (country_code);

-- ===========================================================================
-- scraper_errors — dedicated area for things the helpers had to reject
-- ===========================================================================
--
-- Three categories of error land here:
--
-- 1. INVARIANT violations from upsert_file (the helper rejects the row and
--    raises an exception — but ALSO records it here before raising, so the
--    error is durable even if the caller swallows the exception):
--      * UNKNOWN_FILE_TYPE       — file_type not in EXTENSION_MAP
--      * MISSING_FISCAL_YEAR     — status='SUCCESS' but fiscal_year IS NULL
--      * ALREADY_SCRAPED         — natural-key row exists with status='SUCCESS'
--                                  and force=False
--      * FK_VIOLATION            — company_id or scraper_id doesn't exist
--      * CHECK_VIOLATION         — any other CHECK constraint rejection
--
-- 2. INVARIANT violations from sync_companies — recorded with a sentinel
--    scraper_id of 'SYSTEM' since sync isn't part of any scraper run:
--      * SNAPSHOT_SCHEMA_DRIFT   — required column missing from snapshot
--      * SYNC_NO_PERIOD          — GCPWeeklyFiles.get_latest_period() returned None
--
-- 3. ARBITRARY scraper-side errors recorded via record_error() — anything
--    the scraper wants to log that didn't go through one of the helpers
--    above (download timeouts, HTML parse failures, GCS upload errors).
--    The caller chooses an error_type string for these.
--
-- Foreign key on scraper_id is intentionally NOT declared: we want to
-- accept the 'SYSTEM' sentinel for sync errors, and we don't want a bad
-- scraper_id on a record_error() call to itself raise an IntegrityError
-- — the recording path must always succeed.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS scraper_errors (
    error_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper_id          TEXT NOT NULL,                  -- run UUID or 'SYSTEM'
    error_type          TEXT NOT NULL,                  -- enum-like string, see comment above
    error_message       TEXT NOT NULL,                  -- human-readable summary
    -- Best-effort context: the natural-key fields if we got that far.
    -- All NULL-able because record_error() is also called for system-level
    -- failures that have no file context.
    company_id          INTEGER,
    source_filing_id    TEXT,
    file_type           TEXT,
    -- Raw JSON payload of the offending record (or any context the caller
    -- wants to attach). Stored as TEXT — caller serialises with json.dumps.
    payload             TEXT,
    recorded_at         TEXT NOT NULL                   -- ISO datetime
);

CREATE INDEX IF NOT EXISTS idx_scraper_errors_run
    ON scraper_errors (scraper_id, recorded_at);

CREATE INDEX IF NOT EXISTS idx_scraper_errors_type
    ON scraper_errors (error_type);
