-- T09 - Revenue keyed manually instead of coming from the invoicing system
-- Why: ISA 240 presumes a risk of fraud in revenue recognition. Revenue
-- normally flows from the invoicing system; a credit to a revenue account
-- (class 70) keyed by hand in a manual journal needs a supporting document.
-- The days_before_year_end column shows whether the entries cluster at year end.

WITH params AS (
    SELECT MAX(CASE WHEN name = 'fiscal_year_end' THEN value END) AS fy_end
    FROM audit_parameters
)
SELECT
    jl.entry_number,
    jl.journal_code,
    jl.entry_date,
    CAST(JULIANDAY(p.fy_end) - JULIANDAY(jl.entry_date) AS INTEGER) AS days_before_year_end,
    MIN(jl.created_at)                                              AS created_at,
    MIN(jl.created_by)                                              AS created_by,
    COALESCE(MIN(u.job_title), 'Unknown user')                      AS job_title,
    ROUND(SUM(jl.credit), 2)                                        AS revenue_credited,
    MAX(jl.description)                                             AS description
FROM journal_lines AS jl
JOIN journals AS j
  ON j.journal_code = jl.journal_code
LEFT JOIN users AS u
       ON u.user_id = jl.created_by
CROSS JOIN params AS p
WHERE j.is_manual = 1
  AND jl.account_number LIKE '70%'
  AND jl.credit > 0
GROUP BY jl.entry_number, jl.journal_code, jl.entry_date, p.fy_end
ORDER BY revenue_credited DESC;
