-- T02 - Gaps in entry numbering
-- Why: the ERP numbers entries sequentially within each journal. A missing
-- number can mean an entry was deleted, the extract is incomplete, or a change
-- was made outside the normal workflow. Each gap needs an explanation before
-- the auditor can rely on the ledger being complete.
-- Technique: LAG() compares each number with the previous one in its journal.

WITH numbers AS (
    SELECT DISTINCT
        journal_code,
        SUBSTR(entry_number, 1, INSTR(entry_number, '-'))                      AS prefix,
        CAST(SUBSTR(entry_number, INSTR(entry_number, '-') + 1) AS INTEGER)   AS entry_seq
    FROM journal_lines
),
with_previous AS (
    SELECT
        journal_code,
        prefix,
        entry_seq,
        LAG(entry_seq) OVER (PARTITION BY journal_code ORDER BY entry_seq) AS previous_seq
    FROM numbers
)
SELECT
    journal_code,
    prefix || printf('%05d', previous_seq + 1)  AS first_missing_number,
    prefix || printf('%05d', entry_seq - 1)     AS last_missing_number,
    entry_seq - previous_seq - 1                AS missing_count
FROM with_previous
WHERE entry_seq - previous_seq > 1
ORDER BY journal_code, first_missing_number;
