-- T05 - Entries keyed outside office hours
-- Why: late-night or dawn postings by people are unusual and may avoid
-- supervision. Office hours come from audit_parameters (07:00-21:00 here).
-- System accounts are excluded: the invoicing interface runs at night by design.

WITH params AS (
    SELECT
        MAX(CASE WHEN name = 'office_hours_start' THEN value END) AS office_start,
        MAX(CASE WHEN name = 'office_hours_end'   THEN value END) AS office_end
    FROM audit_parameters
)
SELECT
    e.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_at,
    TIME(e.created_at)                      AS keyed_at,
    e.created_by,
    COALESCE(u.job_title, 'Unknown user')   AS job_title,
    e.total_debit                           AS amount,
    e.description
FROM v_entries AS e
LEFT JOIN users AS u
       ON u.user_id = e.created_by
CROSS JOIN params AS p
WHERE COALESCE(u.is_system, 0) = 0
  AND (TIME(e.created_at) < p.office_start OR TIME(e.created_at) >= p.office_end)
ORDER BY keyed_at;
