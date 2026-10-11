-- T06 - Large round amounts
-- Why: real invoices rarely end in 000. Large round amounts often come from
-- estimates, provisions or figures typed in without a supporting document.
-- Many are legitimate (a bonus accrual, a loan drawdown), so this test has a
-- low weight: it points the auditor to entries worth a quick look.
-- Amounts are compared in cents to avoid floating-point surprises.

WITH params AS (
    SELECT
        CAST(MAX(CASE WHEN name = 'round_amount_unit' THEN value END) AS INTEGER) AS unit,
        CAST(MAX(CASE WHEN name = 'round_amount_min'  THEN value END) AS REAL)    AS min_amount
    FROM audit_parameters
),
round_lines AS (
    SELECT
        jl.entry_number,
        jl.account_number,
        jl.debit + jl.credit AS amount
    FROM journal_lines AS jl
    CROSS JOIN params AS p
    WHERE jl.debit + jl.credit >= p.min_amount
      AND CAST(ROUND((jl.debit + jl.credit) * 100) AS INTEGER) % (p.unit * 100) = 0
)
SELECT
    e.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_by,
    MAX(r.amount)                        AS largest_round_amount,
    GROUP_CONCAT(DISTINCT r.account_number) AS accounts,
    e.description
FROM round_lines AS r
JOIN v_entries AS e
  ON e.entry_number = r.entry_number
GROUP BY e.entry_number, e.journal_code, e.entry_date, e.created_by, e.description
ORDER BY largest_round_amount DESC;
