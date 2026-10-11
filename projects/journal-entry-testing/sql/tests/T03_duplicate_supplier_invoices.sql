-- T03 - Duplicate supplier invoices
-- Why: an invoice posted twice inflates expenses and can be paid twice.
-- Key: same supplier + same invoice reference + same amount. Each later
-- occurrence is listed next to the first one so the pair can be reviewed.
-- Design choice: matching on supplier + amount alone would also catch every
-- monthly rent invoice, so the invoice reference is part of the key.

WITH purchase_invoices AS (
    SELECT
        entry_number,
        MIN(entry_date)                                                AS entry_date,
        MIN(created_at)                                                AS created_at,
        MAX(CASE WHEN account_number LIKE '401%' THEN aux_account END) AS supplier,
        MAX(piece_ref)                                                 AS piece_ref,
        ROUND(SUM(CASE WHEN account_number LIKE '401%' THEN credit ELSE 0 END), 2)
                                                                       AS invoice_amount,
        MIN(created_by)                                                AS created_by
    FROM journal_lines
    WHERE journal_code = 'PUR'
    GROUP BY entry_number
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER()  OVER same_invoice AS occurrence,
        FIRST_VALUE(entry_number) OVER same_invoice AS first_entry_number,
        FIRST_VALUE(created_at)   OVER same_invoice AS first_created_at
    FROM purchase_invoices
    WINDOW same_invoice AS (
        PARTITION BY supplier, piece_ref, invoice_amount
        ORDER BY created_at, entry_number
    )
)
SELECT
    entry_number,
    first_entry_number,
    supplier,
    piece_ref,
    invoice_amount,
    entry_date,
    created_at,
    CAST(JULIANDAY(created_at) - JULIANDAY(first_created_at) AS INTEGER) AS days_after_first,
    created_by
FROM ranked
WHERE occurrence > 1
ORDER BY invoice_amount DESC;
