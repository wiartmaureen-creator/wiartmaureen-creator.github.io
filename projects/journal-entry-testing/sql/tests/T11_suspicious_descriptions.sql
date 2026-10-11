-- T11 - Suspicious wording in entry descriptions
-- Why: vague or unusual descriptions ("misc regularisation", "per CFO
-- request", "do not reverse") are a known red flag in journal entry testing.
-- Keywords live in the review_keywords table so the list can grow without
-- touching the query. Expect some legitimate hits: this is a pointer, not a verdict.

SELECT
    e.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_by,
    e.description,
    GROUP_CONCAT(k.keyword, ', ') AS matched_keywords,
    e.total_debit                 AS amount
FROM v_entries AS e
JOIN review_keywords AS k
  ON LOWER(e.description) LIKE '%' || k.keyword || '%'
GROUP BY e.entry_number, e.journal_code, e.entry_date, e.created_by, e.description, e.total_debit
ORDER BY e.entry_date;
