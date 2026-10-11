-- Benford's law - first-digit analysis of line amounts
-- Why: in large sets of naturally occurring amounts, the first digit is 1
-- about 30% of the time and 9 less than 5% of the time. Invented figures
-- rarely follow that pattern. The analysis does not prove anything on its
-- own: it shows where the population departs from expectation.
-- Amounts below 10 are excluded, as Nigrini recommends.
-- Expected shares are log10(1 + 1/d), written as constants so the query
-- runs on any SQL engine.

WITH expected (digit, expected_share) AS (
    VALUES (1, 0.30103), (2, 0.17609), (3, 0.12494), (4, 0.09691), (5, 0.07918),
           (6, 0.06695), (7, 0.05799), (8, 0.05115), (9, 0.04576)
),
first_digits AS (
    SELECT CAST(SUBSTR(CAST(CAST(debit + credit AS INTEGER) AS TEXT), 1, 1) AS INTEGER) AS digit
    FROM journal_lines
    WHERE debit + credit >= 10
),
observed AS (
    SELECT digit, COUNT(*) AS observed_count
    FROM first_digits
    GROUP BY digit
),
population AS (
    SELECT COUNT(*) AS total FROM first_digits
)
SELECT
    x.digit,
    COALESCE(o.observed_count, 0)                                          AS observed_count,
    ROUND(1.0 * COALESCE(o.observed_count, 0) / p.total, 5)                AS observed_share,
    x.expected_share,
    ROUND(1.0 * COALESCE(o.observed_count, 0) / p.total - x.expected_share, 5) AS difference
FROM expected AS x
CROSS JOIN population AS p
LEFT JOIN observed AS o
       ON o.digit = x.digit
ORDER BY x.digit;
