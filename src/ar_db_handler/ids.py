"""
ID generation.

All IDs flow through this module. Never inline ID construction in upsert
helpers — call ``make_file_id()`` / ``make_run_id()`` so the behaviour stays
in one place.
"""

from __future__ import annotations

import hashlib
import uuid

# Map file_type → file extension on disk / in GCS.
# Resolved at insert time by upsert_file() — callers MUST NOT set extension
# manually. Passing an unknown file_type raises ValueError.
EXTENSION_MAP: dict[str, str] = {
    "PDF": ".pdf",
    "XBRL": ".zip",
}


def make_run_id() -> str:
    """
    Generate a unique scraper run ID.

    Uses uuid4 — scraper runs are ephemeral events with no natural business
    key, so a random UUID is the right primitive.

    Returns:
        A UUID4 string, e.g. ``"a3f2c1d4-..."``.
    """
    return str(uuid.uuid4())


def make_file_id(
    company_id: int,
    source_filing_id: str,
    file_type: str,
) -> str:
    """
    Generate a deterministic file ID from the natural uniqueness key.

    The same ``(company_id, source_filing_id, file_type)`` always produces
    the same ``file_id``, making it consistent with the UNIQUE constraint on
    ``files`` and allowing idempotent upserts without a prior SELECT.

    ``source_filing_id`` is the regulator-assigned filing identifier
    (EDGAR accession number, EDINET docID, ...) — never derived or
    inferred. ``form_type`` and ``fiscal_year`` are NOT part of the hash
    since they do not participate in the unique constraint.

    Args:
        company_id:       Integer company identifier.
        source_filing_id: Regulator-assigned filing ID.
        file_type:        ``"PDF"`` or ``"XBRL"``.

    Returns:
        16-character hex string derived from SHA-256.
    """
    key = f"{company_id}_{source_filing_id}_{file_type}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def resolve_extension(file_type: str) -> str:
    """
    Look up the on-disk extension for a ``file_type``.

    Raises:
        ValueError: when ``file_type`` is not a key of ``EXTENSION_MAP``.
    """
    try:
        return EXTENSION_MAP[file_type]
    except KeyError as exc:
        valid = ", ".join(sorted(EXTENSION_MAP))
        raise ValueError(f"Unknown file_type {file_type!r}. Expected one of: {valid}.") from exc
