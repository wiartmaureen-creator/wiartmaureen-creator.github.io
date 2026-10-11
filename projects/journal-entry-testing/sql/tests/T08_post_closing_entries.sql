-- T08 - Entries dated in the year but keyed after the books were closed
-- Why: once the books are closed and the accounts approved, nobody should
-- add 2025 entries. Late entries can change the reported profit after
-- management and the auditor have reviewed it.

WITH params AS (
    SELECT
        MAX(CASE WHEN name = 'fiscal_year_end' THEN value END) AS fy_end,
        MAX(CASE WHEN name = 'closing_date'    THEN value END) AS closing_date
    FROM audit_parameters
)
SELECT
    e.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_at,
    CAST(JULIANDAY(e.created_at) - JULIANDAY(p.closing_date) AS INTEGER) AS days_after_closing,
    e.created_by,
    COALESCE(u.job_title, 'Unknown user')                                AS job_title,
    e.total_debit                                                        AS amount,
    e.description
FROM v_entries AS e
LEFT JOIN users AS u
       ON u.user_id = e.created_by
CROSS JOIN params AS p
WHERE e.entry_date <= p.fy_end
  AND e.created_at >  p.closing_date
ORDER BY e.created_at;
