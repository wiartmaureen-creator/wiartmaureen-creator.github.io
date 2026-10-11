-- =============================================================================
-- Auditor-side reference data: parameters, test catalogue, review keywords.
-- Change a threshold here and every test picks it up on the next run.
-- =============================================================================

INSERT INTO audit_parameters (name, value, note) VALUES
    ('fiscal_year_start',    '2025-01-01',          'First day of the audited fiscal year'),
    ('fiscal_year_end',      '2025-12-31',          'Last day of the audited fiscal year'),
    ('closing_date',         '2026-01-20 18:00:00', 'Books closed: no 2025 entry should be keyed after this'),
    ('approval_threshold',   '10000',               'Payments at or above this amount need CFO approval'),
    ('near_threshold_floor', '0.95',                'A payment from 95% of the threshold counts as just below it'),
    ('office_hours_start',   '07:00:00',            'Entries keyed before this time are out of hours'),
    ('office_hours_end',     '21:00:00',            'Entries keyed from this time on are out of hours'),
    ('round_amount_unit',    '1000',                'An amount that is a multiple of this unit is round'),
    ('round_amount_min',     '10000',               'Round amounts are only flagged from this amount');

INSERT INTO test_catalog (test_id, title, weight, rationale) VALUES
    ('T01', 'Unbalanced entries',                  5, 'Debits must equal credits. An unbalanced entry means the ledger cannot be relied on.'),
    ('T02', 'Gaps in entry numbering',             0, 'Missing numbers can hide deleted entries or an incomplete extract (no entry to score).'),
    ('T03', 'Duplicate supplier invoices',         3, 'The same invoice posted twice can be paid twice.'),
    ('T04', 'Keyed on a weekend or public holiday', 2, 'Unusual working days are a classic sign of entries made outside normal controls.'),
    ('T05', 'Keyed outside office hours',          2, 'Late-night or dawn postings by people (not systems) deserve an explanation.'),
    ('T06', 'Large round amounts',                 1, 'Round amounts often come from estimates or invented figures rather than invoices.'),
    ('T07', 'Payments just below approval limit',  2, 'Payments split to stay under the approval threshold bypass a key control.'),
    ('T08', 'Keyed after the books were closed',   4, 'Entries dated in the year but keyed after closing can change the reported result.'),
    ('T09', 'Manual revenue entries',              4, 'Revenue should come from the invoicing system; manual revenue is a fraud risk (ISA 240).'),
    ('T10', 'Keyed by unauthorised users',         5, 'Only authorised accounting staff should post entries (segregation of duties).'),
    ('T11', 'Suspicious descriptions',             1, 'Vague or unusual wording ("adjustment", "do not reverse") is a known red flag.');

INSERT INTO review_keywords (keyword) VALUES
    ('adjust'),
    ('correction'),
    ('do not reverse'),
    ('override'),
    ('per ceo'),
    ('per cfo'),
    ('regularis'),
    ('regulariz');
