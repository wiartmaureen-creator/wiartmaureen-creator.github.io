# Automated bank reconciliation in Excel

**Every month, finance teams tick bank lines against the ledger by hand. How much of that can a workbook do, and what is left for a human to decide?**

A reusable Excel tool (Power Query + formulas, no macros) that reconciles a month of
bank transactions with the ledger, produces the bank reconciliation statement with
integrity checks, and lists only the items that need an explanation, each with a
proposed action.

➡️ **Case study:** [`index.html`](index.html) · **Workbook:** [`bank_reconciliation.xlsx`](bank_reconciliation.xlsx)

## Results (December 2025, fictitious company)

| | |
|---|---|
| Bank lines imported | 229 (ledger: 232 lines) |
| Matched automatically | **96.9%**: 207 by reference, 15 by amount and date |
| Items left to explain | **16** instead of 229 lines to tick |
| Unexplained difference | **€0.00**, all 3 integrity checks passed |
| Planted reconciling items found | 16 / 16 |
| Independent check | a pandas recalculation gives the same matches as Excel |

## From items to decisions

| Item | Amount | Decision | Process improvement |
|---|---|---|---|
| Supplier S027 debited €2,908.79, ledger shows €2,098.79 | €810 | Check the invoice; if it is €2,098.79, ask the supplier for a refund | Generate payment files from the ERP instead of keying amounts |
| Insurance direct debit not booked (2026 contract) | €1,284 | Book it as a prepaid expense, not a 2025 cost | Keep a list of direct-debit mandates and book them automatically |
| Customer C047 transfer "advance for January order" | €3,600 | Book as a customer advance, not as revenue | Ask customers to quote the order number |
| Bank charges | €180.90 | Book them | Monthly standard entry |
| 7 outstanding payments / 2 deposits in transit | €4,564 / €1,274 | Timing only: check them on the January statement | Followed up automatically next month |

## How it works

```
data/bank_statement_2025-12.csv   French bank export (; separator, comma decimals, dd/mm/yyyy)
data/ledger_bank_2025-12.csv      ledger lines of bank account 512000
        │  Power Query: typing, cleaning, reference extraction ("/REF ...")
        ▼
tblBank  ──► rule 1: same reference (INDEX/MATCH)
         ──► rule 2: same amount within ±5 days, among ledger lines not matched by reference
tblLedger ◄─ which entries found a bank line?
        ▼
Reconciliation statement · integrity checks · Actions list · Summary
```

- **Power Query** reads the folder and file names from the Settings sheet, so next month
  only needs new files and *Data > Refresh All*.
- **Formulas only use functions available since Excel 2016** (INDEX/MATCH, COUNTIFS, SUMIFS,
  SUMPRODUCT), so the tool works without Microsoft 365. Multi-criteria matching uses the
  `MATCH(1, INDEX((cond1)*(cond2)*(cond3),0),0)` pattern.
- **Unmatched bank lines** are classified by keyword rules (Rules sheet) that propose an action;
  adding a rule is adding a row.
- **Integrity checks**: imported lines add up to the closing balance printed on the statement,
  opening balances agree, no ledger entry is matched twice.

## Files

| File | What it is |
|---|---|
| `bank_reconciliation.xlsx` | The tool (sheets: Start, Summary, Reconciliation, Actions, Bank, Ledger, Rules, Settings) |
| `src/generate_bank_data.py` | Builds the bank statement from the ledger of the [journal entry testing project](../journal-entry-testing/) and plants reconciling items |
| `src/build_workbook.py` | Builds the workbook with Excel itself (COM automation), refreshes it twice, checks the results against pandas and the answer key, exports images |
| `validation/expected_items.csv` | The answer key: 16 planted reconciling items |
| `results/summary.json` | Figures read back from the workbook |

## Run it

The workbook works on its own: open it, check the Settings sheet, *Data > Refresh All*.

To rebuild it from scratch (Windows with Excel 2016 or later, Python 3.10+):

```bash
pip install pandas pywin32
python src/generate_bank_data.py
python src/build_workbook.py
```

---
*Lumen Supplies SAS is fictitious; the bank statement is synthetic.*
