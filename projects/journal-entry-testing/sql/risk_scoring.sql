-- Risk scoring - turn test hits into a prioritised review list
-- Why: a single test produces noise; an entry that triggers several tests
-- (keyed after closing, at night, crediting revenue, with a round amount...)
-- is where the auditor should look first. Each test has a weight in
-- test_catalog; the score is the sum of the weights of the tests triggered.

SELECT
    h.entry_number,
    e.journal_code,
    e.entry_date,
    e.created_at,
    e.created_by,
    e.total_debit                                         AS amount,
    e.description,
    SUM(c.weight)                                         AS risk_score,
    COUNT(*)                                              AS tests_triggered,
    GROUP_CONCAT(h.test_id, ', ' ORDER BY h.test_id)      AS tests
FROM test_hits AS h
JOIN test_catalog AS c
  ON c.test_id = h.test_id
JOIN v_entries AS e
  ON e.entry_number = h.entry_number
GROUP BY h.entry_number, e.journal_code, e.entry_date, e.created_at,
         e.created_by, e.total_debit, e.description
ORDER BY risk_score DESC, tests_triggered DESC, amount DESC;
