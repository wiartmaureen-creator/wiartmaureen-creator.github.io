-- =============================================================================
-- Journal entry testing - database schema (SQLite)
--
-- Client-side tables mirror a typical ERP general ledger extract.
-- Auditor-side tables hold the test parameters, the test catalogue and the
-- hits produced by each test, so that no threshold is hard-coded in a query.
-- =============================================================================

DROP VIEW  IF EXISTS v_entries;
DROP TABLE IF EXISTS test_hits;
DROP TABLE IF EXISTS review_keywords;
DROP TABLE IF EXISTS test_catalog;
DROP TABLE IF EXISTS audit_parameters;
DROP TABLE IF EXISTS journal_lines;
DROP TABLE IF EXISTS public_holidays;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS journals;
DROP TABLE IF EXISTS accounts;

-- --- Client data (from the ERP extract) -------------------------------------

CREATE TABLE accounts (
    account_number TEXT PRIMARY KEY,
    account_label  TEXT NOT NULL,
    account_type   TEXT NOT NULL
        CHECK (account_type IN ('Asset', 'Liability', 'Equity', 'Revenue', 'Expense'))
);

CREATE TABLE journals (
    journal_code  TEXT PRIMARY KEY,
    journal_label TEXT NOT NULL,
    is_manual     INTEGER NOT NULL CHECK (is_manual IN (0, 1))
);

CREATE TABLE users (
    user_id         TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    job_title       TEXT NOT NULL,
    is_system       INTEGER NOT NULL CHECK (is_system IN (0, 1)),
    posting_allowed INTEGER NOT NULL CHECK (posting_allowed IN (0, 1))
);

CREATE TABLE public_holidays (
    holiday_date TEXT PRIMARY KEY,   -- ISO date, YYYY-MM-DD
    holiday_name TEXT NOT NULL
);

-- One row per journal line. created_by deliberately has no foreign key:
-- test T10 must be able to find entries keyed by unknown users.
CREATE TABLE journal_lines (
    entry_number   TEXT NOT NULL,
    journal_code   TEXT NOT NULL REFERENCES journals (journal_code),
    line_no        INTEGER NOT NULL,
    entry_date     TEXT NOT NULL,     -- accounting date, YYYY-MM-DD
    account_number TEXT NOT NULL REFERENCES accounts (account_number),
    aux_account    TEXT,              -- customer or supplier code, if any
    piece_ref      TEXT,              -- supporting document reference
    description    TEXT,
    debit          REAL NOT NULL DEFAULT 0 CHECK (debit >= 0),
    credit         REAL NOT NULL DEFAULT 0 CHECK (credit >= 0),
    created_by     TEXT NOT NULL,     -- user who keyed the entry
    created_at     TEXT NOT NULL,     -- system timestamp, YYYY-MM-DD HH:MM:SS
    PRIMARY KEY (entry_number, line_no)
);

CREATE INDEX idx_lines_account ON journal_lines (account_number);
CREATE INDEX idx_lines_user    ON journal_lines (created_by);
CREATE INDEX idx_lines_journal ON journal_lines (journal_code);

-- --- Auditor data -------------------------------------------------------------

CREATE TABLE audit_parameters (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    note  TEXT
);

CREATE TABLE test_catalog (
    test_id   TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    weight    INTEGER NOT NULL,      -- contribution to the entry risk score
    rationale TEXT NOT NULL
);

CREATE TABLE review_keywords (
    keyword TEXT PRIMARY KEY         -- lower case, matched with LIKE
);

CREATE TABLE test_hits (
    test_id      TEXT NOT NULL REFERENCES test_catalog (test_id),
    entry_number TEXT NOT NULL,
    PRIMARY KEY (test_id, entry_number)
);

-- --- One row per journal entry --------------------------------------------------

CREATE VIEW v_entries AS
SELECT
    entry_number,
    journal_code,
    MIN(entry_date)       AS entry_date,
    MIN(created_at)       AS created_at,
    MIN(created_by)       AS created_by,
    MAX(piece_ref)        AS piece_ref,
    MAX(description)      AS description,
    ROUND(SUM(debit), 2)  AS total_debit,
    ROUND(SUM(credit), 2) AS total_credit,
    COUNT(*)              AS line_count
FROM journal_lines
GROUP BY entry_number, journal_code;
