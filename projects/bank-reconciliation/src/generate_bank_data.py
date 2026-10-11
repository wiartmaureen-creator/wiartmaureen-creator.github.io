"""Build the two inputs of the December 2025 bank reconciliation.

1. data/ledger_bank_2025-12.csv
   The bank account (512000) lines of the Lumen Supplies general ledger for
   December 2025, taken from the journal entry testing project. This is the
   "books" side, as an accountant would export it from the ERP.

2. data/bank_statement_2025-12.csv
   The bank's own export for the same month, in a typical French bank format
   (semicolon separator, comma decimals, dd/mm/yyyy dates, cryptic labels).
   It is derived from the ledger, then made realistic: clearing delays,
   labels without a reference, and the usual reconciling items (bank charges
   and a direct debit nobody booked, an unidentified customer transfer,
   payments not yet debited, cheques not yet credited, one keying error).

The reconciling items are written to validation/expected_items.csv so that
the Excel workbook's results can be checked against a known answer.

Usage:
    python src/generate_bank_data.py
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path

SEED = 1231
PERIOD_START = dt.date(2025, 12, 1)
PERIOD_END = dt.date(2025, 12, 31)
OPENING_BALANCE = 186_420.35  # agreed balance at 30/11/2025 (previous reconciliation)
LABEL_WITHOUT_REFERENCE_SHARE = 0.08

PROJECT_DIR = Path(__file__).resolve().parent.parent
SOURCE_LEDGER = PROJECT_DIR.parent / "journal-entry-testing" / "data" / "general_ledger.csv"
DATA_DIR = PROJECT_DIR / "data"
VALIDATION_DIR = PROJECT_DIR / "validation"

HOLIDAYS = {dt.date(2025, 12, 25), dt.date(2026, 1, 1)}

# Items that only exist on the bank side: (date, label, signed amount, expected action)
BANK_ONLY_ITEMS = [
    (dt.date(2025, 12, 10), "PRLV SEPA ASSURANCE MULTIRISQUE PRO /CONTRAT 2026-ANNUEL", -1_284.00,
     "Direct debit not booked"),
    (dt.date(2025, 12, 18), "VIR SEPA RECU /DE C047 /MOTIF ACOMPTE COMMANDE JANVIER", 3_600.00,
     "Unidentified receipt"),
    (dt.date(2025, 12, 31), "COMMISSIONS CARTES BANCAIRES DECEMBRE", -126.40, "Bank charges not booked"),
    (dt.date(2025, 12, 31), "FRAIS TENUE DE COMPTE DECEMBRE", -38.50, "Bank charges not booked"),
    (dt.date(2025, 12, 16), "COMMISSION D INTERVENTION", -8.00, "Bank charges not booked"),
    (dt.date(2025, 12, 22), "COMMISSION D INTERVENTION", -8.00, "Bank charges not booked"),
]


def is_business_day(day: dt.date) -> bool:
    return day.weekday() < 5 and day not in HOLIDAYS


def add_business_days(day: dt.date, count: int) -> dt.date:
    while count > 0:
        day += dt.timedelta(days=1)
        if is_business_day(day):
            count -= 1
    return day


def french_amount(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def transpose_digits(amount: float, rng: random.Random) -> float:
    """Swap two adjacent, different digits of the integer part (a typical keying error)."""
    digits = list(f"{amount:.2f}")
    integer_positions = [i for i in range(len(digits) - 4)
                         if digits[i] != digits[i + 1] and not (i == 0 and digits[1] == "0")]
    i = rng.choice(integer_positions)
    digits[i], digits[i + 1] = digits[i + 1], digits[i]
    return float("".join(digits))


def load_ledger_lines():
    with SOURCE_LEDGER.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle)
                if row["account_number"] == "512000"
                and PERIOD_START.isoformat() <= row["entry_date"] <= PERIOD_END.isoformat()]
    for row in rows:
        row["amount"] = round(float(row["debit"]) - float(row["credit"]), 2)
        row["date"] = dt.date.fromisoformat(row["entry_date"])
    rows.sort(key=lambda r: (r["date"], r["entry_number"]))
    return rows


def bank_label(row, with_reference: bool) -> str:
    description = row["description"]
    reference = row["piece_ref"]
    if description.startswith("Customer receipt"):
        customer = description.split()[2]
        label = f"VIR SEPA RECU /DE {customer}"
    elif description.startswith("Supplier payment"):
        supplier = description.split()[2]
        label = f"VIR SEPA EMIS /A {supplier}"
    elif description.startswith("Rent payment"):
        label = "VIR SEPA EMIS /A S090 LOYER"
    elif description.startswith("Salary transfer"):
        label = "VIR SEPA EMIS /A SALAIRES DECEMBRE"
    elif description.startswith("Social charges"):
        label = "PRLV SEPA URSSAF NORD PAS DE CALAIS"
    elif description.startswith("Loan instalment"):
        label = "ECHEANCE PRET PROFESSIONNEL"
    else:
        label = description.upper()
    return f"{label} /REF {reference}" if with_reference else label


def main():
    rng = random.Random(SEED)
    ledger = load_ledger_lines()

    # Choose the reconciling items that come from timing and errors.
    last_day_receipts = [r for r in ledger if r["date"] == PERIOD_END and r["amount"] > 0]
    in_transit = set(r["entry_number"] for r in rng.sample(last_day_receipts, 2))
    supplier_payments = [r for r in ledger if r["description"].startswith("Supplier payment")
                         and -5_000 < r["amount"] < -1_000 and r["date"].day < 20]
    keying_error = rng.choice(supplier_payments)["entry_number"]

    bank_rows = []
    expected = []
    for row in ledger:
        if row["entry_number"] in in_transit:
            expected.append([row["entry_number"], "", "Deposit in transit", f"{row['amount']:.2f}"])
            continue
        if row["amount"] > 0:
            bank_date = row["date"]  # receipts are booked from the bank feed
        elif row["description"].startswith(("Salary", "Social", "Loan")):
            bank_date = row["date"]
        elif row["date"] >= dt.date(2025, 12, 26):
            bank_date = add_business_days(row["date"], rng.choice([1, 2, 3]))  # cleared in January
        else:
            bank_date = add_business_days(row["date"], rng.choice([0, 1, 1, 2]))
        if bank_date > PERIOD_END:
            expected.append([row["entry_number"], "", "Outstanding payment", f"{row['amount']:.2f}"])
            continue
        amount = row["amount"]
        if row["entry_number"] == keying_error:
            amount = -transpose_digits(-row["amount"], rng)
            expected.append([row["entry_number"], "", "Amount difference", f"{amount - row['amount']:.2f}"])
        with_reference = rng.random() > LABEL_WITHOUT_REFERENCE_SHARE
        bank_rows.append((bank_date, bank_label(row, with_reference), amount))

    for date, label, amount, kind in BANK_ONLY_ITEMS:
        bank_rows.append((date, label, amount))
        expected.append(["", label, kind, f"{amount:.2f}"])

    bank_rows.sort(key=lambda r: (r[0], r[1]))
    closing_balance = round(OPENING_BALANCE + sum(r[2] for r in bank_rows), 2)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    with (DATA_DIR / "bank_statement_2025-12.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Date opération", "Date valeur", "Libellé", "Débit", "Crédit"])
        for date, label, amount in bank_rows:
            value_date = add_business_days(date, 1) if amount > 0 else date
            writer.writerow([date.strftime("%d/%m/%Y"), value_date.strftime("%d/%m/%Y"), label,
                             french_amount(-amount) if amount < 0 else "",
                             french_amount(amount) if amount > 0 else ""])

    with (DATA_DIR / "ledger_bank_2025-12.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry_number", "entry_date", "piece_ref", "description", "debit", "credit"])
        for row in ledger:
            writer.writerow([row["entry_number"], row["entry_date"], row["piece_ref"],
                             row["description"], row["debit"], row["credit"]])

    with (VALIDATION_DIR / "expected_items.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry_number", "bank_label", "item_type", "amount"])
        writer.writerows(expected)

    with (VALIDATION_DIR / "statement_header.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["opening_balance", "closing_balance"])
        writer.writerow([f"{OPENING_BALANCE:.2f}", f"{closing_balance:.2f}"])

    print(f"Ledger lines: {len(ledger)} | bank lines: {len(bank_rows)}")
    print(f"Opening balance {OPENING_BALANCE:,.2f} -> statement closing balance {closing_balance:,.2f}")
    print(f"Reconciling items planted: {len(expected)}")
    for item in expected:
        print("  ", item)


if __name__ == "__main__":
    main()
