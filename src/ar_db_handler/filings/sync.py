"""
``sync_companies()`` — pull the latest company snapshot from GCS into the
local ``companies`` table.

The module loads ``.env`` (via ``python-dotenv``) on import so callers don't
have to remember to call ``load_dotenv()`` themselves. The credentials
resolution chain is:

1. The ``credentials_path`` kwarg to ``sync_companies()``      (highest)
2. ``OMAHA_GCS_CREDENTIALS`` environment variable
3. Whatever default ``GCPWeeklyFiles`` falls back to            (lowest)

``GCPWeeklyFiles`` itself is imported lazily inside ``sync_companies()`` so
the rest of ``ar-db-handler`` can be imported, tested, and used in
non-GCS contexts (notebooks, CI without credentials, mocked tests) without
the ``google-cloud-storage`` extra being installed.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import TYPE_CHECKING

from .._models import (
    ERROR_SNAPSHOT_SCHEMA_DRIFT,
    ERROR_SYNC_NO_PERIOD,
    SYSTEM_SCRAPER_ID,
    CompanyRecord,
    ErrorRecord,
    SyncResult,
)
from .errors import record_error
from .upserts import upsert_company

if TYPE_CHECKING:  # pragma: no cover — typing only, no runtime import cost
    import pandas as pd

# Load .env once at import time. We don't fail if python-dotenv is missing —
# the caller may have already populated the environment.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

logger = logging.getLogger("ar_db_handler.sync")


# Columns we accept from the snapshot DataFrame. Anything missing falls back
# to a sensible default (NULL or the dataclass default). Keeping this list
# explicit means a schema drift upstream surfaces here rather than as a
# mysterious failure inside the upsert.
_REQUIRED_COLUMNS: tuple[str, ...] = (
    "company_id",
    "fs_ticker",
    "country_code",
    "country",
    "file_name",
    "coverage_status",
)
_OPTIONAL_COLUMNS: tuple[str, ...] = (
    "country_id",
    "start_year_force",
)


def _resolve_credentials_path(explicit: str | None) -> str | None:
    """
    Resolution chain: explicit kwarg → env var → None (let GCPWeeklyFiles
    fall back to its own default).
    """
    if explicit:
        return explicit
    return os.environ.get("OMAHA_GCS_CREDENTIALS")


def _row_to_record(row: dict) -> CompanyRecord:
    """
    Build a ``CompanyRecord`` from a DataFrame row (as a dict).

    Missing required columns raise ``KeyError`` — we do not silently insert
    a row with placeholder data. Missing optional columns use defaults.
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in row]
    if missing:
        raise KeyError(
            f"Snapshot row missing required column(s): {missing}. "
            f"Row keys present: {sorted(row.keys())}"
        )

    return CompanyRecord(
        company_id=int(row["company_id"]),
        fs_ticker=str(row["fs_ticker"]),
        country_code=str(row["country_code"]),
        country=str(row["country"]),
        country_id=(None if row.get("country_id") is None else str(row.get("country_id"))),
        file_name=str(row["file_name"]),
        coverage_status=str(row["coverage_status"]),
        start_year_force=int(row.get("start_year_force") or 2008),
        # is_in_company_info & last_synced_at are forced by upsert_company().
    )


def _iter_rows(df: pd.DataFrame):
    """Yield each DataFrame row as a plain dict (dropping NaNs to None)."""
    import math

    for record in df.to_dict(orient="records"):
        cleaned = {}
        for k, v in record.items():
            # pandas turns missing values into float('nan') — translate back
            # to None so downstream code can use a clean ``if v is None`` check.
            if isinstance(v, float) and math.isnan(v):
                cleaned[k] = None
            else:
                cleaned[k] = v
        yield cleaned


def _deactivate_existing(conn: sqlite3.Connection, country_code: str | None) -> int:
    """
    Set ``is_in_company_info = 0`` for every existing row in scope.

    Run BEFORE the upsert loop so that any row not subsequently re-upserted
    (i.e. dropped from the snapshot) is left flagged as inactive. The
    parameterised ``country_code`` filter degrades to a no-op when the
    parameter is NULL — SQLite evaluates ``(:cc IS NULL)`` per-row.

    Returns:
        Number of rows touched by the UPDATE — i.e. the upper bound on
        "delisted" companies before the upsert loop reactivates the ones
        still in the snapshot.
    """
    cur = conn.execute(
        """
        UPDATE companies
        SET is_in_company_info = 0
        WHERE (country_code = :cc OR :cc IS NULL)
        """,
        {"cc": country_code},
    )
    conn.commit()
    return cur.rowcount or 0


def sync_companies(
    conn: sqlite3.Connection,
    country_code: str | None = None,
    credentials_path: str | None = None,
    filename: str = "company_info.parquet",
) -> SyncResult:
    """
    Pull the latest company reference file from GCS and upsert into ``companies``.

    Steps (matching the build prompt):

    1. Instantiate ``GCPWeeklyFiles(credentials_path)``.
    2. Call ``get_latest_period()`` to find the most recent snapshot.
    3. Call ``read_file_from_period(period, filename)`` → DataFrame.
    4. If ``country_code`` is provided, filter to rows where
       ``country_code == country_code`` before upserting.
    5. Set ``is_in_company_info = 0`` for all existing rows in scope BEFORE
       upserting — this marks delisted/dropped companies automatically.
    6. Upsert each row via ``upsert_company()`` (forces ``is_in_company_info = 1``).
    7. Return ``SyncResult``.

    Args:
        conn:             Open connection to ``filings.db``.
        country_code:     If set, only sync rows for this country. If ``None``,
                          syncs every country present in the snapshot.
        credentials_path: Optional explicit GCS credentials path. If not
                          provided, falls back to ``OMAHA_GCS_CREDENTIALS``
                          and then to GCPWeeklyFiles' own default.
        filename:         Parquet filename within the period folder.

    Returns:
        ``SyncResult(period, upserted, delisted, country_code)``.

    Raises:
        RuntimeError: when no periods exist on GCS.
        ImportError:  when ``GCPWeeklyFiles`` cannot be imported. Install
                      the ``[gcs]`` extra (or supply your own bridge) before
                      calling this function.
        KeyError:     when a row in the snapshot is missing a required
                      column. Surfaces here so schema drift is loud.
    """
    # Lazy import — keeps the optional dependency truly optional for the
    # rest of the package.
    try:
        from gcpBridge import GCPWeeklyFiles
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "sync_companies() requires GCPWeeklyFiles (gcpBridge module). "
            "Install the [gcs] extra and ensure gcpBridge is importable."
        ) from exc

    resolved_creds = _resolve_credentials_path(credentials_path)
    bridge = GCPWeeklyFiles(credentials_path=resolved_creds)

    period = bridge.get_latest_period()
    if period is None:
        message = (
            "GCPWeeklyFiles.get_latest_period() returned None — no snapshots "
            "available in the weekly_fundamentals_files bucket."
        )
        record_error(
            conn,
            ErrorRecord(
                scraper_id=SYSTEM_SCRAPER_ID,
                error_type=ERROR_SYNC_NO_PERIOD,
                error_message=message,
                payload=json.dumps({"country_code": country_code, "filename": filename}),
            ),
        )
        raise RuntimeError(message)

    df = bridge.read_file_from_period(period, filename)
    if df is None or df.empty:
        logger.warning(
            "Snapshot %s/%s is empty — nothing to upsert. " "(deactivation step still ran)",
            period,
            filename,
        )

    # Step 4: country_code filter scopes everything that follows.
    if country_code is not None and df is not None and not df.empty:
        if "country_code" not in df.columns:
            message = (
                "Snapshot DataFrame is missing the 'country_code' column — "
                "cannot apply country_code filter."
            )
            record_error(
                conn,
                ErrorRecord(
                    scraper_id=SYSTEM_SCRAPER_ID,
                    error_type=ERROR_SNAPSHOT_SCHEMA_DRIFT,
                    error_message=message,
                    payload=json.dumps(
                        {
                            "period": period,
                            "filename": filename,
                            "columns_present": sorted(df.columns.tolist()),
                            "filter_requested": country_code,
                        }
                    ),
                ),
            )
            raise KeyError(message)
        df = df[df["country_code"].astype(str) == str(country_code)].copy()

    # Step 5: deactivate first. The rowcount is an upper bound on delistings —
    # we refine it below by counting how many rows were reactivated.
    deactivated_in_scope = _deactivate_existing(conn, country_code)

    # Step 6: upsert each row. Each successful upsert reactivates the row
    # (is_in_company_info = 1, forced by upsert_company).
    upserted = 0
    if df is not None and not df.empty:
        for row in _iter_rows(df):
            try:
                record = _row_to_record(row)
            except KeyError as exc:
                # Record before re-raising — schema drift should be loud
                # AND durable in the audit table.
                record_error(
                    conn,
                    ErrorRecord(
                        scraper_id=SYSTEM_SCRAPER_ID,
                        error_type=ERROR_SNAPSHOT_SCHEMA_DRIFT,
                        error_message=str(exc),
                        company_id=row.get("company_id"),
                        payload=json.dumps(
                            {
                                "period": period,
                                "row_keys": sorted(row.keys()),
                            }
                        ),
                    ),
                )
                raise
            upsert_company(conn, record)
            upserted += 1

    # Delisted = (rows that were active before) - (rows we re-upserted that
    # were already in the table). The cheapest correct count is to query
    # for rows still at is_in_company_info = 0 in scope.
    delisted = conn.execute(
        """
        SELECT COUNT(*) FROM companies
        WHERE is_in_company_info = 0
          AND (country_code = :cc OR :cc IS NULL)
        """,
        {"cc": country_code},
    ).fetchone()[0]

    logger.info(
        "sync_companies(country_code=%s) period=%s upserted=%d delisted=%d "
        "(deactivation pre-pass touched=%d)",
        country_code,
        period,
        upserted,
        delisted,
        deactivated_in_scope,
    )

    return SyncResult(
        period=period,
        upserted=upserted,
        delisted=int(delisted),
        country_code=country_code,
    )


# Re-export the public symbol.
__all__ = ["sync_companies"]
