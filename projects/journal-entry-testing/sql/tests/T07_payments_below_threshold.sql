-- T07 - Supplier payments just below the approval threshold
-- Why: payments of 10,000 or more need the CFO's approval. Splitting one
-- payment into several smaller ones keeps each under the limit and bypasses
-- the control. The window function counts, for each supplier, how many
-- near-threshold payments it received: one is a coincidence, four is a pattern.

WITH params AS (
    SELECT
        CAST(MAX(CASE WHEN name = 'approval_threshold'   THEN value END) AS REAL) AS threshold,
        CAST(MAX(CASE WHEN name = 'near_threshold_floor' THEN value END) AS REAL) AS floor_share
    FROM audit_parameters
)
SELECT
    jl.entry_number,
    jl.entry_date,
    jl.aux_account                                            AS supplier,
    jl.debit                                                  AS payment_amount,
    ROUND(100.0 * jl.debit / p.threshold, 1)                  AS pct_of_threshold,
    COUNT(*) OVER (PARTITION BY jl.aux_account)               AS near_threshold_payments_to_supplier,
    ROUND(SUM(jl.debit) OVER (PARTITION BY jl.aux_account), 2) AS total_paid_in_these_payments,
    jl.created_by,
    jl.description
FROM journal_lines AS jl
CROSS JOIN params AS p
WHERE jl.journal_code = 'BNK'
  AND jl.account_number LIKE '401%'
  AND jl.debit >= p.threshold * p.floor_share
  AND jl.debit <  p.threshold
ORDER BY near_threshold_payments_to_supplier DESC, supplier, jl.entry_date;
