-- metrics.db schema
-- Populated by the evaluator.

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id       TEXT PRIMARY KEY,   -- UUID
    filing_id           TEXT,               -- cross-DB reference to filings.db, not enforced
    company_id          TEXT,
    fiscal_year         INTEGER,
    evaluated_at        DATETIME,
    pdf_source          TEXT,
    xbrl_source         TEXT,
    scope               TEXT,               -- JSON array of statement names
    xbrl_facts_scope    INTEGER,
    pdf_facts_scope     INTEGER,
    matched             INTEGER,
    missed              INTEGER,
    spurious            INTEGER,
    tier1_matches       INTEGER,
    tier2_matches       INTEGER,
    coverage            REAL,
    precision           REAL,
    recall              REAL,
    f1                  REAL,
    exact_match_rate    REAL,
    within_1pct_rate    REAL,
    within_5pct_rate    REAL,
    output_json         TEXT,
    output_diff         TEXT
);

CREATE TABLE IF NOT EXISTS evaluation_scores_by_statement (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id       TEXT NOT NULL REFERENCES evaluations(evaluation_id),
    statement           TEXT NOT NULL,  -- IncomeStatement | BalanceSheet | CashFlow | Note_PPE
    coverage            REAL,
    precision           REAL,
    recall              REAL,
    f1                  REAL,
    exact_match_rate    REAL,
    within_1pct_rate    REAL,
    within_5pct_rate    REAL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_filing_id
    ON evaluations(filing_id);

CREATE INDEX IF NOT EXISTS idx_evaluations_company_year
    ON evaluations(company_id, fiscal_year);

CREATE INDEX IF NOT EXISTS idx_scores_evaluation_id
    ON evaluation_scores_by_statement(evaluation_id);
