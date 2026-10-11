# Journal entry testing: from 4,466 entries to five decisions

**Which entries in a company's general ledger need a closer look, and what should management do about them?**

Every financial audit includes testing journal entries for signs of fraud and error
(ISA 240, management override of controls). This project is a repeatable toolkit of
11 SQL tests that scans a full general ledger in under a second, scores every entry
by risk, and turns the findings into decisions and process improvements. It is
validated against 30 anomalies planted on purpose.

➡️ **Case study with charts:** [`index.html`](index.html) (published on the portfolio site)

## Results at a glance

| | |
|---|---|
| Ledger analysed | 11,317 lines · 4,466 entries · fiscal year 2025 |
| Tests | 11 SQL tests + risk score + Benford's law |
| Planted anomalies detected | **30 / 30** |
| Entries left to review | **33** (0.7% of all entries) |
| Benford first-digit MAD | 0.0026 (close conformity) |
| Run time | about half a second for the whole pipeline |

## From findings to decisions

| Finding | At stake | Decision for management | Process improvement |
|---|---|---|---|
| Revenue keyed by hand by the CFO at year end (3 entries) | €85,450 | Do not sign off until each sale is supported; reverse what is not | Revenue only from the invoicing system |
| Entries keyed after the books were closed (3) | +€70,165 profit | Reverse, or approve and document formally | Lock the period in the ERP on the closing date |
| One invoice paid in four transfers under the €10,000 limit | €39,576 | Retrospective CFO approval and explanation | Apply the limit to weekly totals per supplier |
| Supplier invoices posted twice (5) | €10,241 | Cancel before payment | ERP rejects an invoice reference already posted |
| Credit notes keyed by a user without posting rights (3) | €7,530 | Confirm with customers | Remove access; finance approves credit notes |

The revenue and profit lines overlap on one €50,000 entry.

## The tests

| ID | Test | Why it matters |
|---|---|---|
| T01 | Unbalanced entries | Debits must equal credits; flags possible transpositions (difference divisible by 9) |
| T02 | Gaps in entry numbering | Missing numbers can hide deleted entries or an incomplete extract |
| T03 | Duplicate supplier invoices | The same invoice posted twice can be paid twice |
| T04 | Keyed on a weekend or public holiday | Entries made when nobody else is in the office escape review |
| T05 | Keyed outside office hours | Late-night or dawn postings by people, not systems |
| T06 | Large round amounts | Estimates or invented figures rather than invoices |
| T07 | Payments just below the approval limit | Split payments that bypass the CFO's approval |
| T08 | Keyed after the books were closed | Late entries can change the reported result |
| T09 | Manual revenue entries | Revenue keyed by hand instead of coming from the invoicing system |
| T10 | Keyed by unauthorised users | Segregation of duties |
| T11 | Suspicious descriptions | "Adjustment per CFO request", "do not reverse"... |

Each test is a standalone, commented file in [`sql/tests/`](sql/tests/). All thresholds
(closing date, approval limit, office hours, round-amount rule) live in one table,
`audit_parameters`, defined in [`sql/01_audit_parameters.sql`](sql/01_audit_parameters.sql).

## The data

Real ledgers are confidential, so the data is **synthetic**: a fictitious French
distributor, *Lumen Supplies SAS*, over fiscal year 2025. A seeded Python script
([`src/generate_ledger.py`](src/generate_ledger.py)) simulates a year of activity
(invoicing interface, purchases, payments, payroll, loan, month-end and year-end
closing) using French chart of accounts numbering with English labels.

It then plants 30 known anomalies, listed in
[`validation/planted_anomalies.csv`](validation/planted_anomalies.csv). That answer
key is what lets the pipeline measure whether each test finds what it was built for.

```
data/
  general_ledger.csv     one row per journal line (11,317 rows)
  chart_of_accounts.csv  34 accounts
  journals.csv           SAL, PUR, BNK, PAY, MISC (manual)
  users.csv              7 users with job titles and posting rights
  public_holidays.csv    French public holidays
validation/
  planted_anomalies.csv  the answer key
```

## How it works

[`src/run_analysis.py`](src/run_analysis.py) runs the pipeline:

1. **Load** the CSV files into a typed SQLite schema ([`sql/00_schema.sql`](sql/00_schema.sql)).
2. **Test**: run every file in `sql/tests/` and export each result to `results/`.
3. **Score**: each test has a weight; an entry's risk score is the sum of the weights of
   the tests it triggers ([`sql/risk_scoring.sql`](sql/risk_scoring.sql)).
4. **Benford**: first-digit analysis of all amounts of 10 or more, with Nigrini's MAD
   conformity thresholds ([`sql/benford_first_digit.sql`](sql/benford_first_digit.sql)).
5. **Validate**: compare the hits with the planted answer key (`results/detection_check.csv`).

SQL techniques used: CTEs, window functions (`LAG`, `ROW_NUMBER`, `FIRST_VALUE`,
`COUNT/SUM OVER`, named windows), `LEFT JOIN ... IS NULL` anti-joins to find unknown users,
conditional aggregation, date and time functions, a view (`v_entries`).

## Run it

Only the Python standard library is needed (Python 3.10+).

```bash
python src/generate_ledger.py   # writes data/ and validation/
python src/run_analysis.py      # builds output/ledger.db and results/
```

The SQLite database in `output/ledger.db` can be opened with any SQLite client
(for example DB Browser for SQLite) to run the queries by hand.

## What I would do next

- Run the same queries on a real FEC file (the French legal ledger format) after mapping its 18 columns.
- Add a first-two-digits Benford test and a test on rarely used accounts.
- Calibrate the weights with an engagement team and track false positives cleared over time.
- Feed the review list into Power BI so the team can filter it and document conclusions.

---
*Lumen Supplies SAS and all people named in the data are fictitious.*
