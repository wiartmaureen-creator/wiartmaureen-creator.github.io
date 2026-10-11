-- T04 - Entries keyed on a weekend or a public holiday
-- Why: entries made when nobody else is in the office escape the usual
-- review. The test uses the system timestamp (when the entry was actually
-- keyed), not the accounting date: a month-end entry dated on a Saturday is
-- normal, someone keying entries on a Saturday is not.
-- Refinement: system accounts are excluded, since the nightly invoicing batch
-- runs every night (including Saturday morning) by design.

SELECT
    e.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_at,
    e.created_by,
    COALESCE(u.job_title, 'Unknown user')   AS job_title,
    CASE
        WHEN h.holiday_name IS NOT NULL THEN 'Public holiday - ' || h.holiday_name
        WHEN strftime('%w', e.created_at) = '6' THEN 'Saturday'
        ELSE 'Sunday'
    END                                     AS non_working_day,
    e.total_debit                           AS amount,
    e.description
FROM v_entries AS e
LEFT JOIN users AS u
       ON u.user_id = e.created_by
LEFT JOIN public_holidays AS h
       ON h.holiday_date = DATE(e.created_at)
WHERE COALESCE(u.is_system, 0) = 0
  AND (strftime('%w', e.created_at) IN ('0', '6') OR h.holiday_date IS NOT NULL)
ORDER BY e.created_at;
