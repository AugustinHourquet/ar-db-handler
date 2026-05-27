# ar-db-handler

The SQLite database layer for the annual report pipeline. Owns two
databases and nothing else.

* **`filings.db`** — populated by country-specific scrapers (US/EDGAR,
  JP/EDINET, ...) and read by the evaluator.
* **`metrics.db`** — populated by the evaluator.

This package has **no** knowledge of EDGAR, scraping logic, evaluation
logic, or which form type should beat which other form type. It is a
pure data-access module: every other module in the pipeline that needs
to read or write to a database imports from here.

---

## Table of contents

1. [What it does (and what it doesn't)](#what-it-does-and-what-it-doesnt)
2. [The two databases](#the-two-databases)
3. [Project layout](#project-layout)
4. [Setup](#setup)
5. [ID generation](#id-generation)
6. [`form_type` normalisation](#form_type-normalisation)
7. [`extension` auto-derivation](#extension-auto-derivation)
8. [The UNIQUE constraint](#the-unique-constraint)
9. [`source_filing_id` — the country-agnostic skip anchor](#source_filing_id--the-country-agnostic-skip-anchor)
10. [Fiscal year — derivation rule](#fiscal-year--derivation-rule)
11. [GCS path resolution](#gcs-path-resolution)
12. [The SUCCESS / fiscal_year invariant](#the-success--fiscal_year-invariant)
13. [Error handling — the `scraper_errors` table](#error-handling--the-scraper_errors-table)
14. [Amendment handling (10-K and 10-KA)](#amendment-handling-10-k-and-10-ka)
15. [`sync_companies()`](#sync_companies)
16. [`get_scraped_files()` — the scraper skip-set](#get_scraped_files--the-scraper-skip-set)
17. [`AlreadyScrapedError` and the expected caller pattern](#alreadyscraperror-and-the-expected-caller-pattern)
18. [Development commands](#development-commands)

---

## What it does (and what it doesn't)

**Does:**

* Defines and applies the full schema for `filings.db` and `metrics.db`.
* Provides `init_filings_db(path)` and `init_metrics_db(path)` — they
  create tables if they don't exist, enable WAL mode, and turn on FK
  enforcement.
* Provides read and write helpers (upserts, queries) for every table.
* Provides `sync_companies()` — syncs the `companies` table from the
  master pipeline via `GCPWeeklyFiles`.
* Exposes a clean public API via `__init__.py`.

**Does not:**

* Know anything about EDGAR, EDINET, scraping logic, or evaluation logic.
* Manage connections across threads — callers manage their own.
* Enforce cross-database FKs (the `file_id` reference from `metrics.db`
  to `filings.db` is a plain text field, not an FK constraint —
  SQLite can't enforce FKs across separate `.db` files, and a hard
  coupling between the two databases is the wrong default anyway).

---

## The two databases

| Database     | Tables                                  | Writer                  | Readers                |
| ------------ | --------------------------------------- | ----------------------- | ---------------------- |
| `filings.db` | `companies`, `scraper_runs`, `files`    | scrapers, `sync_companies` | evaluator, scrapers |
| `metrics.db` | `metrics` (stub — columns TBD)          | evaluator               | downstream consumers   |

`filings.db` is the system of record for every filing the pipeline has
ever attempted to scrape. `metrics.db` records the outcome of evaluating
each PDF/XBRL pair the evaluator processes.

---

## Project layout

```
ar-db-handler/
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── Makefile
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
│
├── src/
│   └── ar_db_handler/
│       ├── __init__.py          # public re-exports
│       ├── _models.py           # dataclasses + AlreadyScrapedError
│       ├── connection.py        # shared init_db(), WAL mode, FK pragma
│       ├── ids.py               # make_file_id, make_run_id, EXTENSION_MAP
│       ├── paths.py             # make_blob_path, resolve_gcs_path, derive_fiscal_year
│       ├── filings/
│       │   ├── __init__.py
│       │   ├── schema.sql       # filings.db DDL
│       │   ├── init.py          # init_filings_db(path) → connection
│       │   ├── upserts.py       # write helpers for filings.db
│       │   ├── errors.py        # record_error / get_scraper_errors
│       │   └── sync.py          # sync_companies() — GCPWeeklyFiles integration
│       ├── metrics/
│       │   ├── __init__.py
│       │   ├── schema.sql       # metrics.db DDL (stub)
│       │   ├── init.py          # init_metrics_db(path) → connection
│       │   └── writer.py        # write_metric() — stub
│       └── queries/
│           ├── __init__.py
│           ├── filings.py       # read helpers for filings.db
│           └── metrics.py       # read helpers for metrics.db (stub)
│
├── scripts/
│   └── make_helpers.py      # cross-platform FS ops for the Makefile
│
└── tests/
    ├── conftest.py
    ├── test_filings_schema.py
    ├── test_filings_upserts.py
    ├── test_scraper_errors.py
    ├── test_sync.py
    ├── test_ids.py
    ├── test_metrics_schema.py
    ├── test_metrics_writer.py
    ├── test_paths.py
    └── test_queries.py
```

---

## Setup

Requires Python 3.10+. Everything runs inside a project-local virtualenv
at `.venv/`. The `Makefile` bootstraps it for you — no global pip
installs, no need to activate the venv first.

```bash
git clone <repo>
cd ar-db-handler
make install
```

`make install` does:

1. Creates `.venv/` if it doesn't exist (`python3 -m venv .venv`, or
   `python -m venv .venv` on Windows).
2. Upgrades `pip` and installs `wheel`.
3. Editable-installs this package with its dev dependencies
   (`pip install -e ".[dev]"`).
4. Writes a stamp file at `.venv/.installed` so subsequent
   `make install` calls are no-ops unless `pyproject.toml` or
   `.pre-commit-config.yaml` have changed.

To install the optional GCS dependencies needed by `sync_companies()`:

```bash
make install-gcs
```

To use a different venv location:

```bash
make VENV=.venv-dev install
make VENV=.venv-dev test
```

### Configuring GCS credentials and private dependencies

`sync_companies()` loads `GCPWeeklyFiles` from `gcpBridge.py`, a
private file in the `omaha_norma` project (not on PyPI). Configure
your local `.env` with three variables:

```bash
cp .env.example .env
# Then edit .env:
```

```
# Absolute path to gcpBridge.py in the omaha_norma project
OMAHA_GCP_BRIDGE_PATH=C:\path\to\omaha_norma\src\omaha_norma\core\gcpBridge.py

# Absolute path to omaha_norma's src/ directory (needed for gcpBridge's own imports)
OMAHA_NORMA_SRC_PATH=C:\path\to\omaha_norma\src

# GCS service-account credentials JSON
OMAHA_GCS_CREDENTIALS=C:\path\to\personal_keys\gcs_credentials.json
```

Neither path is committed to git — `.env` is gitignored. Callers may
also pass `credentials_path=...` explicitly to `sync_companies()` —
the kwarg wins over the env var.

---

## ID generation

All IDs flow through `ar_db_handler.ids`. **Never** generate IDs inline
in upsert helpers — call these functions.

```python
from ar_db_handler import make_file_id, make_run_id

# Scraper runs are ephemeral events with no natural key → UUID4.
scraper_id = make_run_id()                       # "a3f2c1d4-..."

# Files have a natural uniqueness key → deterministic 16-char SHA-256 prefix.
fid = make_file_id(
    company_id=123,
    source_filing_id="0000320193-24-000123",     # EDGAR accession number
    file_type="PDF",
)
```

`make_file_id` is **deterministic**: the same
`(company_id, source_filing_id, file_type)` always hashes to the same
`file_id`. This matches the UNIQUE constraint on the `files` table and
lets upserts be idempotent without a prior SELECT.

`form_type` and `fiscal_year` are **not** part of the hash, because
they don't participate in the unique constraint. A 10-K and a 10-KA for
the same filing have different `source_filing_id`s — that's how they
end up as two rows.

---

## `form_type` normalisation

Raw scraper output that is `None`, `""`, or whitespace is normalised to
`"UNKNOWN"` inside `upsert_file()`. Callers don't need to handle this.

```python
upsert_file(conn, FileRecord(..., form_type=None, ...))
# Stored as form_type='UNKNOWN'.
```

The `form_type NOT NULL DEFAULT 'UNKNOWN'` column constraint is a
belt-and-braces safeguard — `upsert_file()` should always set it
explicitly, but if a future caller path bypassed the helper, the DB
default catches it.

---

## `extension` auto-derivation

The `extension` column is **always** derived from `file_type` via
`EXTENSION_MAP` at insert time. Never set it manually.

```python
from ar_db_handler import EXTENSION_MAP
# EXTENSION_MAP == {"PDF": ".pdf", "XBRL": ".zip"}

upsert_file(conn, FileRecord(..., file_type="PDF", ...))
# Stored as extension='.pdf'.
```

Passing an unknown `file_type` raises `ValueError` before the row is
written.

---

## The UNIQUE constraint

```sql
UNIQUE (company_id, source_filing_id, file_type)
```

`fiscal_year` is **not** part of this constraint. The reasoning:

* `fiscal_year` is derived metadata — it can be `NULL` for
  unresolvable filings. A nullable column inside a UNIQUE constraint
  permits multiple `NULL` rows in SQLite, defeating the purpose.
* `source_filing_id` (the regulator-assigned ID) is already globally
  unique per regulator, requires zero derivation, and is the right
  natural identity for a filing.

`form_type` is also not part of the constraint — it's metadata, and a
10-K plus its 10-KA amendment are different filings with different
`source_filing_id`s.

---

## `source_filing_id` — the country-agnostic skip anchor

The skip-set used by scrapers is keyed on `source_filing_id`, not
`fiscal_year`. This is the regulator-assigned unique identifier:

| Country | Source     | Field             | Example                  |
| ------- | ---------- | ----------------- | ------------------------ |
| US      | EDGAR      | `accessionNumber` | `0000320193-24-000123`   |
| Japan   | EDINET     | `docID`           | `S100ABCD`               |
| Future  | TBD        | TBD               | TBD                      |

`source_filing_id` is always available from the source API, requires
zero derivation, and is globally unique per regulator. It is stored on
every `files` row and is the primary deduplication anchor.

---

## Fiscal year — derivation rule

A company may file two reports in the same calendar year — one for
FY2023 (filed late) and one for FY2024 (filed on time). If
`fiscal_year` were derived from `filing_date`, both reports would
collide on the same year. **`fiscal_year` is always derived from the
period the filing covers, never from when it was submitted.**

Specifically: `fiscal_year = year(reporting_date)` where
`reporting_date` is the regulator-supplied period-end
(EDGAR `reportDate`, EDINET `periodEnd`, ...). If that field is
unavailable from the API response, fall back to parsing the
`period-of-report` field on the filing index page. **Never guess from
`filing_date`.**

The scraper performs this resolution and sets `fiscal_year` on the
`FileRecord` it hands to `upsert_file()`. `ar-db-handler` itself does
not implement the resolution chain — it just persists the result and
enforces the invariant below.

---

## GCS path resolution

`ar-db-handler` owns the canonical GCS blob-path scheme for every
file the pipeline writes:

```
rawdata/{country_code}/{company_id}/{fiscal_year}/{file_type}_{form_type}_{reporting_date}{extension}
```

Examples:

* `rawdata/US/14778/2023/PDF_10-K_2023-12-31.pdf`
* `rawdata/US/14778/2023/XBRL_10-K_2023-12-31.zip`
* `rawdata/JP/200042/2023/PDF_ASR_2024-03-31.pdf`

Why here? Because `ar-db-handler` already owns the canonical metadata
(`company_id`, `file_type`, `form_type`, `fiscal_year`, `extension`)
and has access to `country_code` via the `companies` table. Every
consumer of the GCS layer already depends on `ar-db-handler`, so they
get the path builder for free, and the path scheme and the DB schema
evolve together.

The path builder lives in `ar_db_handler.paths`. It does **not**
import from `gcs-handler` — the path is just a string. `GCSClient` is
bound to a bucket at construction time, so the bucket name is not
part of this blob path.

### Auto-resolution in `upsert_file()`

When you call `upsert_file()` with `gcs_path=None` on a SUCCESS row,
`ar-db-handler` resolves it for you:

1. If `record.country_code` is missing, it's looked up from the
   `companies` table by `company_id`. A missing company records
   `ERROR_FK_VIOLATION` and raises `IntegrityError` before any insert.
2. If `record.gcs_path` is missing, `resolve_gcs_path(record)` is
   called and the result is written to the row. A missing
   `reporting_date` records `ERROR_MISSING_REPORTING_DATE` and raises
   `ValueError`.

Caller-supplied values always win — pass an explicit `country_code`
or `gcs_path` to override (e.g. backfilling pre-existing files into
a legacy bucket layout).

PENDING and FAILED rows are exempt from path resolution. They may
legitimately lack `fiscal_year` or `reporting_date`, and the schema
already allows their `gcs_path` to be NULL.

### Typical caller flow

```python
from ar_db_handler import FileRecord, upsert_file

record = FileRecord(
    company_id=14778,
    scraper_id=scraper_id,
    status="SUCCESS",
    file_type="PDF",
    source_filing_id="0000320193-24-acme-2023",
    form_type="10-K",
    fiscal_year=2023,
    reporting_date="2023-12-31",
    # country_code and gcs_path are auto-filled by upsert_file()
)
upsert_file(conn, record)
# The row written to files now has:
#   country_code = "US"
#   gcs_path     = "rawdata/US/14778/2023/PDF_10-K_2023-12-31.pdf"
```

### Standalone path builder

If you need the path string without going through `upsert_file()`
(e.g. you're about to call `GCSClient.upload(local_path, blob_path)`
before the upsert), use `make_blob_path()` or `resolve_gcs_path()`
directly:

```python
from ar_db_handler import make_blob_path, resolve_gcs_path

# From raw components
path = make_blob_path(
    country_code="US",
    company_id=14778,
    fiscal_year=2023,
    file_type="PDF",
    form_type="10-K",
    reporting_date="2023-12-31",
    extension=".pdf",
)
# → "rawdata/US/14778/2023/PDF_10-K_2023-12-31.pdf"

# Or from a partially-built FileRecord (extension is resolved internally)
path = resolve_gcs_path(record)
```

Both raise `ValueError` for malformed components and
`MissingFiscalYearError` when `fiscal_year is None` — same exception
types `upsert_file()` raises.

### Fiscal-year derivation helper

For scrapers building `FileRecord`s, `derive_fiscal_year` applies the
H2/H1 rule:

* period-end in months 07–12 → `fiscal_year = year(reporting_date)`
* period-end in months 01–06 → `fiscal_year = year(reporting_date) - 1`

```python
from ar_db_handler import derive_fiscal_year

derive_fiscal_year("2023-12-31")   # → 2023
derive_fiscal_year("2023-06-30")   # → 2022
derive_fiscal_year("2024-03-31")   # → 2023
```

`make_blob_path()` does **not** call this — it trusts the value on
the record. One source of truth for the rule, lives in
`ar_db_handler.paths`.

---

## The SUCCESS / fiscal_year invariant

A row with `status = 'SUCCESS'` MUST carry a non-null `fiscal_year`.
This is enforced two ways:

1. **Python**: `upsert_file()` raises `MissingFiscalYearError` before
   any INSERT.
2. **SQL**: `CHECK (status != 'SUCCESS' OR fiscal_year IS NOT NULL)`
   on the `files` table — catches direct INSERTs that bypass
   `upsert_file()`.

```python
upsert_file(conn, FileRecord(..., status="SUCCESS", fiscal_year=None, ...))
# → MissingFiscalYearError: status='SUCCESS' requires fiscal_year != None.
```

PENDING and FAILED rows may have `fiscal_year = NULL`:

- **PENDING** rows represent intent recorded before the metadata fetch
  completed. The year may not be known yet.
- **FAILED** rows represent unrecoverable failures — there's nothing
  to evaluate, so we don't need the year.

Why the invariant rather than the old `fiscal_year_status = 'MISSING'`
escape hatch? Because every regulator we target exposes the
period-end on filing metadata. A successful scrape with no derivable
year is a scraper bug, not a data limitation. Forcing it to fail loudly
at the upsert layer means the scraper has to handle it — the
alternative (silently quarantining MISSING rows for manual repair) lets
bugs accumulate.

---

## Error handling — the `scraper_errors` table

Every rejected upsert is **also recorded** to a dedicated audit table
before the exception is raised. This means:

- The caller can `except` to handle the failure inline if it wants.
- The error is durable even if the caller swallows the exception.
- The recording uses the same connection, so there's no partial state
  where the rejection happened in the DB but the audit row didn't.

Five categories from `upsert_file()`:

| Trigger                                | `error_type` constant            | Python exception            |
| -------------------------------------- | -------------------------------- | --------------------------- |
| unknown `file_type`                    | `ERROR_UNKNOWN_FILE_TYPE`        | `ValueError`                |
| `status='SUCCESS'` & `fiscal_year=None`| `ERROR_MISSING_FISCAL_YEAR`      | `MissingFiscalYearError`    |
| SUCCESS row exists, `force=False`      | `ERROR_ALREADY_SCRAPED`          | `AlreadyScrapedError`       |
| bogus `company_id` or `scraper_id`     | `ERROR_FK_VIOLATION`             | `sqlite3.IntegrityError`    |
| other CHECK constraint failure         | `ERROR_CHECK_VIOLATION`          | `sqlite3.IntegrityError`    |

Two categories from `sync_companies()` (recorded with
`scraper_id = SYSTEM_SCRAPER_ID`):

| Trigger                                                 | `error_type` constant         | Python exception |
| ------------------------------------------------------- | ----------------------------- | ---------------- |
| `GCPWeeklyFiles.get_latest_period()` returned None      | `ERROR_SYNC_NO_PERIOD`        | `RuntimeError`   |
| Snapshot row missing required column                    | `ERROR_SNAPSHOT_SCHEMA_DRIFT` | `KeyError`       |

### Recording your own errors

The scraper can call `record_error()` directly for any
download/parse failure that didn't go through one of the helpers:

```python
from ar_db_handler import record_error, ErrorRecord

try:
    download_pdf(url, dest)
except requests.Timeout as exc:
    record_error(
        conn,
        ErrorRecord(
            scraper_id=scraper_id,
            error_type="DOWNLOAD_TIMEOUT",       # caller-defined string is fine
            error_message=str(exc),
            company_id=company_id,
            source_filing_id=accession,
            file_type="PDF",
            payload=json.dumps({"url": url, "attempts": 3}),
        ),
    )
    # Then continue / retry / give up as you prefer.
```

### Reading errors back

```python
from ar_db_handler import (
    get_scraper_errors,
    SYSTEM_SCRAPER_ID,
    ERROR_ALREADY_SCRAPED,
)

# Every error from a specific run, newest first
errs = get_scraper_errors(conn, scraper_id=my_run_id)

# Just one category, capped
already = get_scraper_errors(conn, error_type=ERROR_ALREADY_SCRAPED, limit=100)

# System-level errors (sync failures, ad-hoc scripts)
sys_errs = get_scraper_errors(conn, scraper_id=SYSTEM_SCRAPER_ID)
```

The payload column holds caller-serialised JSON — usually the
offending `FileRecord` (for upsert failures) or whatever context the
caller passed to `record_error()`.

### Best-effort recording

`record_error()` is best-effort: a failure during recording itself
(e.g. the `scraper_errors` table got dropped) is logged at WARNING
level and silently swallowed. This is deliberate — the helpers call it
from inside `except` blocks, and a second exception there would mask
the original one the caller is trying to report.

---

## Amendment handling (10-K and 10-KA)

A 10-K and its 10-KA amendment are two filings with different
`source_filing_id`s, so they coexist as **two separate rows**:

```python
upsert_file(conn, FileRecord(source_filing_id="acc-10k",  form_type="10-K",  ...))
upsert_file(conn, FileRecord(source_filing_id="acc-10ka", form_type="10-KA", ...))
```

`get_scraped_pairs()` returns **every combination** — for the example
above (two PDFs × two XBRLs), four pairs:

```python
pairs = get_scraped_pairs(conn, company_id=100, fiscal_year=2024)
# 4 pairs: (10-K PDF, 10-K XBRL), (10-K PDF, 10-KA XBRL),
#          (10-KA PDF, 10-K XBRL), (10-KA PDF, 10-KA XBRL)
```

**Priority selection is the caller's responsibility.** `ar-db-handler`
is country-agnostic and has no opinion on whether a 10-KA should beat
a 10-K. The country-specific scraper or the evaluator applies its own
logic to pick the preferred pair.

---

## `sync_companies()`

Pulls the latest company snapshot from GCS and upserts the
`companies` table.

```python
from ar_db_handler import init_filings_db, sync_companies

conn = init_filings_db("data/filings.db")

# Sync every country
result = sync_companies(conn)

# Or scope to one country
result = sync_companies(conn, country_code="US")

print(result)
# SyncResult(period='2026-05-21-W57', upserted=2770, delisted=0, country_code='US')
```

To initialise the table for the first time, use the provided script:

```bash
python scripts/init_companies_table.py
```

### GCP column mapping

The GCP snapshot (`companyInfo.parquet`) uses different column names
from the DB schema. `sync_companies()` renames them on load:

| GCP column        | DB column          |
|-------------------|--------------------|
| `CompanyID`       | `company_id`       |
| `FactSet Ticker`  | `fs_ticker`        |
| `fileName`        | `file_name`        |
| `Coverage_Status` | `coverage_status`  |
| `Country_Name`    | `country`          |
| `StartYearForce`  | `start_year_force` |
| `country_id`      | `country_id`       |

`country_code` (e.g. `"US"`) is not present in the GCP file — it is
derived from `Country_Name` via an internal `_COUNTRY_NAME_TO_CODE`
mapping after the rename step. `country_id` is an internal company
identifier stored as-is for cross-referencing with other GCP data.
Rows with a null `StartYearForce` default to `2006`.

### Country filtering

The `country_code` argument is resolved to its full country name
(e.g. `"US"` → `"UNITED STATES"`) and matched against the `Country_Name`
column in the raw GCP file before any renaming. Add new countries to
`_COUNTRY_NAME_TO_CODE` in `sync.py` if they are not yet covered.

### How deactivation works (step 5 of the procedure)

Before upserting, `sync_companies()` runs:

```sql
UPDATE companies
SET is_in_company_info = 0
WHERE (country_code = :country_code OR :country_code IS NULL)
```

This flips every in-scope row to inactive. The subsequent upsert loop
re-activates the rows that ARE in the snapshot (each `upsert_company`
forces `is_in_company_info = 1`). Anything left at `0` after the loop
has been delisted/dropped from the master pipeline.

**Why pre-flip and re-set rather than diff-then-update?** Diff-and-update
needs two queries plus a Python set difference; the pre-flip approach
is one UPDATE plus the upsert loop you'd run anyway. Both end at the
same state; pre-flip is simpler.

### Credentials resolution

`sync_companies()` resolves the GCS credentials path in this order:

1. The `credentials_path=` kwarg, if passed.
2. The `OMAHA_GCS_CREDENTIALS` env var (loaded from `.env` if present).
3. Whatever default `GCPWeeklyFiles` falls back to.

---

## `get_scraped_files()` — the scraper skip-set

Called once per run (or per worker) to build an O(1) skip-set.

```python
from ar_db_handler import get_scraped_files

already = get_scraped_files(conn, country_code="US")
# {(company_id, source_filing_id, file_type), ...}

for filing in edgar_filings:
    if (filing.company_id, filing.accession_number, "PDF") in already:
        continue  # already done — skip
    # ... download ...
```

`fiscal_year` is intentionally NOT part of the tuple. Using a derived
field as the skip anchor would cause false misses on filings where
derivation failed (`fiscal_year IS NULL`). `source_filing_id` is
always present, always unique, and never derived.

---

## `AlreadyScrapedError` and the expected caller pattern

The scraper's primary defence against re-scraping is `get_scraped_files()`.
`AlreadyScrapedError` is the secondary guard — `upsert_file()` raises
it when a row with `status = 'SUCCESS'` already exists and the caller
didn't pass `force=True`.

The expected caller pattern:

```python
from ar_db_handler import AlreadyScrapedError, upsert_file

already = get_scraped_files(conn, country_code="US")

for filing in edgar_filings:
    key = (filing.company_id, filing.accession_number, "PDF")
    if key in already:
        continue  # primary skip — fast path

    # Download, build a FileRecord ...
    try:
        upsert_file(conn, record)  # force=False by default
    except AlreadyScrapedError:
        # Race condition: another worker scraped this between the
        # skip-set build and this point. Log and move on.
        logger.info("Race-condition double-scrape avoided for %s", key)
```

`PENDING` and `FAILED` rows are overwritten without `force=True` —
they represent in-flight or recoverable work, not committed state.
Only `SUCCESS` is sticky.

---

## Development commands

```bash
make install              # create .venv, pip install -e ".[dev]"
make install-gcs          # also install the optional [gcs] extra
make format               # black + ruff --fix
make lint                 # ruff check + black --check
make test                 # pytest
make setup-check          # import the package and print its version
make pre-commit-install   # install the git pre-commit hooks
make clean                # remove build artefacts (keeps the venv)
make clean-venv           # remove the venv directory itself
```

Every target depends on `install` via the stamp file, so the venv is
created on first use and skipped thereafter. Every target invokes the
venv's Python directly — no manual activation needed.

### A note on Windows

The Makefile works under Windows `make` (Chocolatey / scoop / GnuWin32)
**without** needing Git Bash or WSL. File-system operations
(`clean`, `clean-venv`, the install stamp) are delegated to
`scripts/make_helpers.py` because Windows `cmd.exe` has no `rm`,
`find`, or `touch`. The non-FS recipes invoke the venv's Python
directly, which works identically on both platforms.

If you previously hit `CreateProcess … Le fichier spécifié est introuvable`
on `make clean`, this layout is what fixes it.
