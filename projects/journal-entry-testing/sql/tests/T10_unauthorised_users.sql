-- T10 - Entries keyed by users without posting rights
-- Why: segregation of duties. Only authorised accounting staff should post
-- entries. The LEFT JOIN also catches user IDs that do not exist in the
-- users list at all (shared, deleted or generic accounts).

SELECT
    e.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_at,
    e.created_by,
    COALESCE(u.job_title, 'Unknown user')             AS job_title,
    CASE
        WHEN u.user_id IS NULL THEN 'User not in the users list'
        ELSE 'User has no posting rights'
    END                                               AS issue,
    e.total_debit                                     AS amount,
    e.description
FROM v_entries AS e
LEFT JOIN users AS u
       ON u.user_id = e.created_by
WHERE u.user_id IS NULL
   OR u.posting_allowed = 0
ORDER BY e.created_at;
