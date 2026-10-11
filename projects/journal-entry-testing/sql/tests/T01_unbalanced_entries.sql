-- T01 - Unbalanced entries
-- Why: in double-entry bookkeeping every entry must balance. An unbalanced
-- entry points to an interface failure, a keying mistake or a manipulation,
-- and it means the ledger is not a reliable basis for the financial statements.
-- Bonus: when the difference divides by 9, two digits were probably swapped
-- (e.g. 1,875.20 keyed as 1,857.20).

SELECT
    entry_number,
    journal_code,
    MIN(entry_date)                     AS entry_date,
    MIN(created_by)                     AS created_by,
    ROUND(SUM(debit), 2)                AS total_debit,
    ROUND(SUM(credit), 2)               AS total_credit,
    ROUND(SUM(debit) - SUM(credit), 2)  AS difference,
    CASE
        WHEN CAST(ROUND(ABS(SUM(debit) - SUM(credit)) * 100) AS INTEGER) % 9 = 0
        THEN 'Yes'
        ELSE 'No'
    END                                 AS possible_transposition,
    MAX(description)                    AS description
FROM journal_lines
GROUP BY entry_number, journal_code
HAVING ROUND(SUM(debit) - SUM(credit), 2) <> 0
ORDER BY ABS(SUM(debit) - SUM(credit)) DESC;
