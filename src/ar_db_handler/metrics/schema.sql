-- ===========================================================================
-- metrics.db — schema (STUB)
--
-- Populated by the evaluator. The full column set is not yet defined;
-- the table below is the minimum stub agreed in the build prompt.
--
-- file_id is a cross-DB reference to filings.db.files.file_id and is
-- intentionally NOT enforced as a FK — SQLite cannot enforce FKs across
-- databases and we do not want a hard coupling between the two .db files.
-- Callers reconcile by file_id at query time.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS metrics (
    evaluation_id   TEXT PRIMARY KEY,    -- UUID
    file_id         TEXT                 -- cross-DB reference to filings.db; not enforced as FK
    -- remaining columns to be defined
);
