"""Generate a synthetic general ledger for a fictitious French distributor.

The ledger covers fiscal year 2025 and uses French chart-of-accounts (PCG)
numbering with English labels. Normal business activity is simulated first
(sales, purchases, bank, payroll, month-end and year-end entries), then a
small, documented set of anomalies is planted on top of it.

The planted anomalies are written to validation/planted_anomalies.csv. That
file is the "answer key" run_analysis.py uses to check that every SQL test
finds what it is designed to find.

Everything is random but seeded: each run produces exactly the same files.

Usage:
    python src/generate_ledger.py
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from dataclasses import dataclass, field
from pathlib import Path

SEED = 2025
FY_START = dt.date(2025, 1, 1)
FY_END = dt.date(2025, 12, 31)
VAT_RATE = 0.20

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
VALIDATION_DIR = PROJECT_DIR / "validation"

ACCOUNTS = [
    # (account_number, account_label, account_type)
    ("164000", "Bank loans", "Liability"),
    ("281540", "Accumulated depreciation - equipment", "Asset"),
    ("370000", "Inventory of goods", "Asset"),
    ("401000", "Trade payables", "Liability"),
    ("408100", "Accrued supplier invoices", "Liability"),
    ("411000", "Trade receivables", "Asset"),
    ("418100", "Unbilled receivables", "Asset"),
    ("421000", "Salaries payable", "Liability"),
    ("428600", "Accrued payroll costs", "Liability"),
    ("431000", "Social security payable", "Liability"),
    ("445660", "Deductible VAT", "Asset"),
    ("445710", "Collected VAT", "Liability"),
    ("445870", "VAT on unbilled receivables", "Liability"),
    ("467000", "Other receivables", "Asset"),
    ("471000", "Suspense account", "Asset"),
    ("491000", "Allowance for doubtful receivables", "Asset"),
    ("512000", "Bank", "Asset"),
    ("603700", "Change in inventory of goods", "Expense"),
    ("606300", "Small equipment and supplies", "Expense"),
    ("607000", "Purchases of goods", "Expense"),
    ("613200", "Rent", "Expense"),
    ("615000", "Maintenance and repairs", "Expense"),
    ("622600", "Professional fees", "Expense"),
    ("625100", "Travel expenses", "Expense"),
    ("626000", "Postage and telecom", "Expense"),
    ("641000", "Salaries", "Expense"),
    ("645000", "Employer social charges", "Expense"),
    ("658000", "Other operating expenses", "Expense"),
    ("661100", "Loan interest", "Expense"),
    ("681100", "Depreciation expense", "Expense"),
    ("681740", "Allowance expense - doubtful receivables", "Expense"),
    ("707000", "Sales of goods", "Revenue"),
    ("709000", "Sales discounts and rebates", "Revenue"),
    ("781740", "Release of allowance - doubtful receivables", "Revenue"),
]

JOURNALS = [
    # (journal_code, journal_label, is_manual)
    ("SAL", "Sales (invoicing system interface)", 0),
    ("PUR", "Purchases", 0),
    ("BNK", "Bank", 0),
    ("PAY", "Payroll", 0),
    ("MISC", "General journal (manual entries)", 1),
]

USERS = [
    # (user_id, full_name, job_title, is_system, posting_allowed)
    ("ERP_BATCH", "Invoicing interface", "System account", 1, 1),
    ("jmartin", "Julie Martin", "Accounts payable accountant", 0, 1),
    ("sdubois", "Samuel Dubois", "Accounts receivable accountant", 0, 1),
    ("lpetit", "Lea Petit", "Payroll officer", 0, 1),
    ("cmoreau", "Claire Moreau", "Chief accountant", 0, 1),
    ("ftessier", "Franck Tessier", "Chief financial officer", 0, 1),
    ("hbernard", "Hugo Bernard", "Sales manager", 0, 0),
]

PUBLIC_HOLIDAYS = [
    ("2025-01-01", "New Year's Day"),
    ("2025-04-21", "Easter Monday"),
    ("2025-05-01", "Labour Day"),
    ("2025-05-08", "Victory in Europe Day"),
    ("2025-05-29", "Ascension Day"),
    ("2025-06-09", "Whit Monday"),
    ("2025-07-14", "Bastille Day"),
    ("2025-08-15", "Assumption Day"),
    ("2025-11-01", "All Saints' Day"),
    ("2025-11-11", "Armistice Day"),
    ("2025-12-25", "Christmas Day"),
    ("2026-01-01", "New Year's Day"),
]
HOLIDAYS = {dt.date.fromisoformat(day) for day, _ in PUBLIC_HOLIDAYS}

# Seasonality of sales volumes (summer slowdown, year-end peak).
MONTH_FACTOR = {1: 0.85, 2: 0.9, 3: 1.0, 4: 1.0, 5: 0.95, 6: 1.05,
                7: 0.9, 8: 0.6, 9: 1.05, 10: 1.1, 11: 1.2, 12: 1.35}

# Purchase mix: (expense account, weight, lognormal mu, lognormal sigma, supplier pool)
PURCHASE_MIX = [
    ("607000", 0.62, 7.0, 1.25, range(1, 19)),
    ("606300", 0.09, 5.6, 0.9, range(19, 24)),
    ("615000", 0.08, 6.2, 1.0, range(24, 28)),
    ("622600", 0.07, 6.9, 0.9, range(28, 32)),
    ("625100", 0.07, 5.2, 1.0, range(32, 36)),
    ("626000", 0.07, 5.5, 0.7, range(36, 38)),
]

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


@dataclass
class Entry:
    journal: str
    entry_date: dt.date
    created_at: dt.datetime
    created_by: str
    piece_ref: str
    description: str
    lines: list  # (account_number, aux_account, debit, credit)
    order: int = 0
    number: str = ""
    to_delete: bool = False


@dataclass
class PlantedCase:
    case_id: str
    scenario: str
    expected_tests: str
    entry: Entry
    story: str


@dataclass
class Ledger:
    entries: list = field(default_factory=list)
    planted: list = field(default_factory=list)

    def add(self, journal, entry_date, created_at, created_by, piece_ref, description, lines):
        entry = Entry(journal, entry_date, created_at, created_by, piece_ref,
                      description, lines, order=len(self.entries))
        self.entries.append(entry)
        return entry

    def plant(self, case_id, scenario, expected_tests, story, *entry_args):
        entry = self.add(*entry_args)
        self.planted.append(PlantedCase(case_id, scenario, expected_tests, entry, story))
        return entry


# --- small helpers -----------------------------------------------------------

def money(value: float) -> float:
    return round(value + 1e-9, 2)


def debit(account, amount, aux=None):
    return (account, aux, money(amount), 0.0)


def credit(account, amount, aux=None):
    return (account, aux, 0.0, money(amount))


def is_business_day(day: dt.date) -> bool:
    return day.weekday() < 5 and day not in HOLIDAYS


def next_business_day(day: dt.date) -> dt.date:
    while not is_business_day(day):
        day += dt.timedelta(days=1)
    return day


def add_business_days(day: dt.date, count: int) -> dt.date:
    for _ in range(count):
        day = next_business_day(day + dt.timedelta(days=1))
    return day


def last_business_day(year: int, month: int) -> dt.date:
    day = month_end(year, month)
    while not is_business_day(day):
        day -= dt.timedelta(days=1)
    return day


def month_end(year: int, month: int) -> dt.date:
    first_of_next = dt.date(year + month // 12, month % 12 + 1, 1)
    return first_of_next - dt.timedelta(days=1)


def office_time(rng: random.Random, day: dt.date) -> dt.datetime:
    """A realistic keying time during office hours (roughly 08:15-18:45)."""
    hours = min(max(rng.gauss(13.0, 2.2), 8.25), 18.75)
    return dt.datetime.combine(day, dt.time()) + dt.timedelta(seconds=int(hours * 3600))


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


def business_days_of_year():
    day = FY_START
    while day <= FY_END:
        if is_business_day(day):
            yield day
        day += dt.timedelta(days=1)


# --- normal business activity ---------------------------------------------------

def generate_sales(ledger: Ledger, rng: random.Random):
    customers = [f"C{n:03d}" for n in range(1, 61)]
    weights = [rng.paretovariate(1.2) for _ in customers]  # a few large customers
    invoice_no = 0
    sales = []
    for day in business_days_of_year():
        count = max(0, round(rng.gauss(6.5, 2.0) * MONTH_FACTOR[day.month]))
        batch_start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(2, 10))
        for index in range(count):
            invoice_no += 1
            customer = rng.choices(customers, weights)[0]
            net = money(min(max(rng.lognormvariate(6.6, 1.35), 35), 48_000))
            vat = money(net * VAT_RATE)
            gross = money(net + vat)
            piece = f"INV-25{invoice_no:05d}"
            created = batch_start + dt.timedelta(seconds=index * 9 + rng.randint(0, 5))
            entry = ledger.add("SAL", day, created, "ERP_BATCH", piece,
                               f"Invoice {piece} - customer {customer}",
                               [debit("411000", gross, customer),
                                credit("707000", net), credit("445710", vat)])
            sales.append((entry, customer, gross))
    return sales


def generate_receipts(ledger: Ledger, rng: random.Random, sales):
    for entry, customer, gross in sales:
        if entry.to_delete or rng.random() < 0.03:  # deleted invoice or never paid
            continue
        pay_day = next_business_day(entry.entry_date + dt.timedelta(days=rng.randint(20, 60)))
        if pay_day > FY_END:
            continue  # still open at year end
        ledger.add("BNK", pay_day, office_time(rng, pay_day), "sdubois",
                   f"RCP-{entry.piece_ref[4:]}",
                   f"Customer receipt {customer} - {entry.piece_ref}",
                   [debit("512000", gross), credit("411000", gross, customer)])


def generate_purchases(ledger: Ledger, rng: random.Random):
    used_refs = set()
    purchases = []
    mix_weights = [item[1] for item in PURCHASE_MIX]
    for day in business_days_of_year():
        for _ in range(rng.choice([1, 2, 2, 3, 3, 3, 4, 5])):
            account, _, mu, sigma, pool = rng.choices(PURCHASE_MIX, mix_weights)[0]
            supplier = f"S{rng.choice(list(pool)):03d}"
            net = money(min(max(rng.lognormvariate(mu, sigma), 15), 60_000))
            vat = money(net * VAT_RATE)
            gross = money(net + vat)
            ref = f"{supplier}-{rng.randint(10_000, 99_999)}"
            while ref in used_refs:
                ref = f"{supplier}-{rng.randint(10_000, 99_999)}"
            used_refs.add(ref)
            posted_on = next_business_day(day + dt.timedelta(days=rng.choice([0, 0, 1, 1, 2, 3])))
            entry = ledger.add("PUR", day, office_time(rng, posted_on), "jmartin", ref,
                               f"Supplier invoice {ref}",
                               [debit(account, net), debit("445660", vat),
                                credit("401000", gross, supplier)])
            purchases.append((entry, supplier, gross))
    return purchases


def generate_supplier_payments(ledger: Ledger, rng: random.Random, purchases):
    for entry, supplier, gross in purchases:
        pay_day = next_business_day(entry.entry_date + dt.timedelta(days=rng.randint(28, 50)))
        if pay_day > FY_END:
            continue
        ledger.add("BNK", pay_day, office_time(rng, pay_day), "jmartin",
                   f"PMT-{entry.piece_ref}",
                   f"Supplier payment {supplier} - {entry.piece_ref}",
                   [debit("401000", gross, supplier), credit("512000", gross)])


def generate_monthly_entries(ledger: Ledger, rng: random.Random):
    loan_balance = 400_000.00
    for month in range(1, 13):
        name = f"{MONTH_NAMES[month - 1]} 2025"

        # Rent invoice and payment.
        rent_day = next_business_day(dt.date(2025, month, 1))
        ledger.add("PUR", rent_day, office_time(rng, rent_day), "jmartin",
                   f"RENT-2025-{month:02d}", f"Office and warehouse rent {name}",
                   [debit("613200", 4_500), debit("445660", 900),
                    credit("401000", 5_400, "S090")])
        pay_day = add_business_days(rent_day, 3)
        ledger.add("BNK", pay_day, office_time(rng, pay_day), "jmartin",
                   f"PMT-RENT-2025-{month:02d}", f"Rent payment {name}",
                   [debit("401000", 5_400, "S090"), credit("512000", 5_400)])

        # Payroll, employer charges, salary transfer and social charges payment.
        payroll_day = last_business_day(2025, month)
        gross_pay = money(rng.uniform(41_000, 44_500))
        employee_share = money(gross_pay * 0.22)
        net_pay = money(gross_pay - employee_share)
        employer_share = money(gross_pay * 0.42)
        ledger.add("PAY", payroll_day, office_time(rng, payroll_day), "lpetit",
                   f"PAYROLL-2025-{month:02d}", f"Payroll {name}",
                   [debit("641000", gross_pay), credit("421000", net_pay),
                    credit("431000", employee_share)])
        ledger.add("PAY", payroll_day, office_time(rng, payroll_day), "lpetit",
                   f"PAYROLL-2025-{month:02d}", f"Employer social charges {name}",
                   [debit("645000", employer_share), credit("431000", employer_share)])
        ledger.add("BNK", payroll_day, office_time(rng, payroll_day), "sdubois",
                   f"SAL-TRF-2025-{month:02d}", f"Salary transfer {name}",
                   [debit("421000", net_pay), credit("512000", net_pay)])
        social_day = next_business_day(dt.date(2025 + month // 12, month % 12 + 1, 15))
        if social_day <= FY_END:
            charges = money(employee_share + employer_share)
            ledger.add("BNK", social_day, office_time(rng, social_day), "sdubois",
                       f"URSSAF-2025-{month:02d}", f"Social charges payment {name}",
                       [debit("431000", charges), credit("512000", charges)])

        # Loan instalment.
        loan_day = next_business_day(dt.date(2025, month, 5))
        interest = money(loan_balance * 0.042 / 12)
        principal = 8_333.33
        loan_balance = money(loan_balance - principal)
        ledger.add("BNK", loan_day, office_time(rng, loan_day), "sdubois",
                   f"LOAN-2025-{month:02d}", f"Loan instalment {name}",
                   [debit("164000", principal), debit("661100", interest),
                    credit("512000", principal + interest)])

        # Monthly depreciation, keyed a couple of days after month end.
        closing_day = add_business_days(month_end(2025, month), 2)
        ledger.add("MISC", month_end(2025, month), office_time(rng, closing_day), "cmoreau",
                   f"DEP-2025-{month:02d}", f"Depreciation {name}",
                   [debit("681100", 1_412.50), credit("281540", 1_412.50)])


def generate_reclassifications(ledger: Ledger, rng: random.Random):
    expense_accounts = ["606300", "615000", "622600", "625100", "626000", "658000"]
    days = sorted(rng.sample(list(business_days_of_year()), 24))
    for index, day in enumerate(days):
        source, target = rng.sample(expense_accounts, 2)
        amount = money(rng.lognormvariate(6.0, 0.8))
        if index in (7, 18):
            description = "Correction of posting error - wrong expense account"
        else:
            description = f"Reclassification from {source} to {target}"
        ledger.add("MISC", day, office_time(rng, day), "cmoreau",
                   f"RCL-2025-{index + 1:02d}", description,
                   [debit(target, amount), credit(source, amount)])


def generate_year_end_entries(ledger: Ledger, rng: random.Random):
    """Legitimate closing entries, dated 31/12 and keyed before the books close."""
    closing_days = [day for day in (dt.date(2026, 1, d) for d in range(5, 17))
                    if is_business_day(day)]
    accrual_accounts = ["607000", "615000", "622600", "626000", "625100", "606300"]
    for index, account in enumerate(accrual_accounts):
        day = closing_days[index]
        amount = money(rng.lognormvariate(7.3, 0.7))
        ledger.add("MISC", FY_END, office_time(rng, day), "cmoreau",
                   f"YE-ACC-{index + 1:02d}", "Accrued supplier invoice - December 2025",
                   [debit(account, amount), credit("408100", amount)])

    ledger.add("MISC", FY_END, at("2026-01-15 21:34:18"), "cmoreau", "YE-INV-01",
               "Change in inventory - year-end stock count",
               [debit("370000", 18_432.75), credit("603700", 18_432.75)])
    ledger.add("MISC", FY_END, office_time(rng, closing_days[6]), "cmoreau", "YE-BDA-01",
               "Allowance for doubtful receivables - customer C017",
               [debit("681740", 6_215.80), credit("491000", 6_215.80)])
    ledger.add("MISC", FY_END, office_time(rng, closing_days[7]), "cmoreau", "YE-FAE-01",
               "Goods shipped not yet invoiced - sales cut-off",
               [debit("418100", 8_642.18), credit("707000", 7_201.82),
                credit("445870", 1_440.36)])
    ledger.add("MISC", FY_END, office_time(rng, closing_days[8]), "cmoreau", "YE-BON-01",
               "Accrued annual bonuses 2025",
               [debit("641000", 30_000), credit("428600", 30_000)])


# --- planted anomalies -----------------------------------------------------------

def plant_manual_anomalies(ledger: Ledger):
    """Hand-written cases, each one targeting one or more SQL tests."""
    cases = [
        ("A01", "Fictitious year-end revenue", "T05;T06;T08;T09;T11",
         "The CFO books a 50,000 sale on the last day of the year, a week after the books were closed, late in the evening.",
         ("MISC", FY_END, at("2026-01-28 21:47:12"), "ftessier", "ADJ-2025-117",
          "Year-end sales adjustment per CFO request",
          [debit("411000", 60_000, "C014"), credit("707000", 50_000), credit("445710", 10_000)])),
        ("A02", "Revenue accrual keyed on a Saturday", "T04;T06;T09",
         "Unsupported revenue accrual keyed by the CFO on a Saturday, two working days before year end.",
         ("MISC", dt.date(2025, 12, 27), at("2025-12-27 10:12:40"), "ftessier", "ACR-2025-Q4",
          "Revenue accrual - Q4 deliveries",
          [debit("418100", 24_000), credit("707000", 20_000), credit("445870", 4_000)])),
        ("A03", "Manual sale outside the invoicing system", "T09",
         "A sale keyed by hand in the general journal instead of coming from the invoicing system.",
         ("MISC", dt.date(2025, 12, 30), at("2025-12-30 14:05:09"), "ftessier", "MAN-2025-031",
          "Sales - project milestone",
          [debit("411000", 18_540, "C031"), credit("707000", 15_450), credit("445710", 3_090)])),
        ("A04", "Allowance released after closing", "T08",
         "An allowance for doubtful receivables is released into profit two weeks after the books were closed.",
         ("MISC", FY_END, at("2026-02-02 09:31:55"), "ftessier", "ADJ-2025-121",
          "Release of allowance - doubtful receivables",
          [debit("491000", 12_800), credit("781740", 12_800)])),
        ("A05", "Accrual cancelled after closing", "T08;T11",
         "A supplier accrual is cancelled after closing, which boosts profit, with a 'do not reverse' note.",
         ("MISC", FY_END, at("2026-01-27 16:20:03"), "ftessier", "ADJ-2025-119",
          "Cancel accrual - do not reverse",
          [debit("408100", 7_365.40), credit("607000", 7_365.40)])),
        ("A06", "Payment keyed on a public holiday", "T04;T11",
         "A vaguely described bank payment keyed on 1 May (Labour Day).",
         ("MISC", dt.date(2025, 5, 1), at("2025-05-01 11:40:27"), "cmoreau", "MISC-0501",
          "Misc regularisation",
          [debit("658000", 3_420), credit("512000", 3_420)])),
        ("A07", "Transfer to suspense on a Saturday", "T04",
         "Cash moved to the suspense account on a Saturday in mid-August.",
         ("MISC", dt.date(2025, 8, 16), at("2025-08-16 15:02:44"), "cmoreau", "SUS-0816",
          "Transfer to suspense account",
          [debit("471000", 8_750), credit("512000", 8_750)])),
        ("A08", "CFO self-reimbursement on a holiday", "T04",
         "The CFO keys the reimbursement of his own expenses on 11 November.",
         ("MISC", dt.date(2025, 11, 11), at("2025-11-11 18:12:09"), "ftessier", "EXP-FT-1111",
          "Expense reimbursement - F. Tessier",
          [debit("625100", 2_180.35), credit("512000", 2_180.35)])),
        ("A09", "Supplier invoice keyed near midnight", "T05",
         "A consulting invoice keyed at 23:18 on a Friday.",
         ("PUR", dt.date(2025, 3, 14), at("2025-03-14 23:18:37"), "jmartin", "S029-77120",
          "Supplier invoice S029-77120",
          [debit("622600", 6_480), debit("445660", 1_296), credit("401000", 7_776, "S029")])),
        ("A10", "Inventory write-down keyed at dawn", "T05;T11",
         "A 14,912.66 inventory write-down keyed at 05:42 with a generic description.",
         ("MISC", dt.date(2025, 9, 30), at("2025-10-01 05:42:10"), "cmoreau", "INV-ADJ-0930",
          "Inventory adjustment",
          [debit("603700", 14_912.66), credit("370000", 14_912.66)])),
        ("A11", "Round transfer to suspense", "T06",
         "Exactly 25,000 moved from the bank to the suspense account.",
         ("MISC", dt.date(2025, 6, 30), at("2025-06-30 16:44:02"), "cmoreau", "TRF-0630",
          "Transfer",
          [debit("471000", 25_000), credit("512000", 25_000)])),
        ("A12", "Round advance to a director", "T06",
         "Exactly 40,000 paid out as an advance on a director's current account.",
         ("MISC", dt.date(2025, 10, 15), at("2025-10-15 11:03:51"), "ftessier", "ADV-1015",
          "Advance - director current account",
          [debit("467000", 40_000), credit("512000", 40_000)])),
        ("A13", "Unbalanced entry (transposition)", "T01",
         "Debit 1,875.20 but credit 1,857.20: two digits swapped. The difference (18.00) divides by 9, the classic sign of a transposition.",
         ("MISC", dt.date(2025, 4, 30), at("2025-05-05 10:20:30"), "cmoreau", "ACC-2025-04",
          "Accrued fees - April 2025",
          [debit("622600", 1_875.20), credit("408100", 1_857.20)])),
        ("A14", "Unbalanced entry", "T01",
         "An accrual where debit and credit differ by 60.00.",
         ("MISC", dt.date(2025, 7, 31), at("2025-08-04 09:48:12"), "cmoreau", "ACC-2025-07",
          "Accrued maintenance - July 2025",
          [debit("615000", 4_260), credit("408100", 4_200)])),
        ("A15", "Credit note keyed by a user without posting rights", "T10",
         "The sales manager, who has no posting rights, grants a credit note to a customer.",
         ("MISC", dt.date(2025, 12, 19), at("2025-12-19 17:25:41"), "hbernard", "CN-2025-041",
          "Commercial gesture - customer C022",
          [debit("709000", 2_000), debit("445710", 400), credit("411000", 2_400, "C022")])),
        ("A16", "Credit note keyed by a user without posting rights", "T10",
         "Second credit note from the sales manager, three days later.",
         ("MISC", dt.date(2025, 12, 22), at("2025-12-22 16:02:19"), "hbernard", "CN-2025-042",
          "Commercial gesture - customer C005",
          [debit("709000", 1_650), debit("445710", 330), credit("411000", 1_980, "C005")])),
        ("A17", "Credit note keyed by a user without posting rights", "T10",
         "Third credit note from the sales manager, just before Christmas.",
         ("MISC", dt.date(2025, 12, 23), at("2025-12-23 12:47:55"), "hbernard", "CN-2025-043",
          "Commercial gesture - customer C022",
          [debit("709000", 2_625), debit("445710", 525), credit("411000", 3_150, "C022")])),
    ]
    for case_id, scenario, tests, story, entry_args in cases:
        ledger.plant(case_id, scenario, tests, story, *entry_args)


def plant_duplicates(ledger: Ledger, rng: random.Random, purchases):
    """Re-post five supplier invoices a few days after the original."""
    candidates = [item for item in purchases
                  if 2 <= item[0].entry_date.month <= 11 and item[2] > 300]
    for index, (original, supplier, gross) in enumerate(rng.sample(candidates, 5), start=1):
        repost_day = add_business_days(original.created_at.date(), rng.randint(2, 8))
        ledger.plant(f"D{index:02d}", "Duplicate supplier invoice", "T03",
                     f"Invoice {original.piece_ref} from supplier {supplier} posted a second time "
                     f"({gross:,.2f}), which could lead to paying it twice.",
                     "PUR", original.entry_date, office_time(rng, repost_day), "jmartin",
                     original.piece_ref, original.description, list(original.lines))


def plant_split_payments(ledger: Ledger, rng: random.Random):
    """One 39,576 invoice paid in four instalments just under the approval threshold."""
    invoice_day = dt.date(2025, 11, 3)
    ledger.add("PUR", invoice_day, office_time(rng, invoice_day), "jmartin", "S038-40211",
               "Supplier invoice S038-40211",
               [debit("607000", 32_980), debit("445660", 6_596), credit("401000", 39_576, "S038")])
    for index, day in enumerate([dt.date(2025, 11, d) for d in (24, 25, 26, 27)], start=1):
        ledger.plant(f"P{index:02d}", "Payment split below the approval threshold", "T07",
                     "A 39,576 invoice paid in four transfers of 9,894 on consecutive days: each one "
                     "stays under the 10,000 limit that requires the CFO's approval.",
                     "BNK", day, office_time(rng, day), "jmartin", f"PMT-S038-40211-{index}",
                     "Supplier payment S038 - S038-40211",
                     [debit("401000", 9_894, "S038"), credit("512000", 9_894)])


def plant_sequence_gaps(ledger: Ledger, rng: random.Random, sales):
    """Mark four sales invoices for deletion: their numbers will be missing."""
    candidates = [item[0] for item in sales if 3 <= item[0].entry_date.month <= 11]
    chosen = sorted(rng.sample(candidates, 4), key=lambda entry: entry.order)
    for index, entry in enumerate(chosen, start=1):
        entry.to_delete = True
        ledger.planted.append(PlantedCase(
            f"G{index:02d}", "Gap in sales entry numbering", "T02", entry,
            f"Sales invoice {entry.piece_ref} was deleted after posting: its entry number is missing."))


# --- numbering and export ------------------------------------------------------

def assign_entry_numbers(ledger: Ledger):
    """Number entries per journal in the order they were keyed (FY 2025 sequence)."""
    for journal_code, _, _ in JOURNALS:
        journal_entries = [e for e in ledger.entries if e.journal == journal_code]
        journal_entries.sort(key=lambda e: (e.created_at, e.order))
        for seq, entry in enumerate(journal_entries, start=1):
            entry.number = f"{journal_code}25-{seq:05d}"


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def export(ledger: Ledger):
    kept = [e for e in ledger.entries if not e.to_delete]
    kept.sort(key=lambda e: (e.entry_date, e.journal, e.number))
    ledger_rows = []
    for entry in kept:
        for line_no, (account, aux, dr, cr) in enumerate(entry.lines, start=1):
            ledger_rows.append([
                entry.number, entry.journal, line_no, entry.entry_date.isoformat(),
                account, aux or "", entry.piece_ref, entry.description,
                f"{dr:.2f}", f"{cr:.2f}", entry.created_by,
                entry.created_at.isoformat(sep=" "),
            ])
    write_csv(DATA_DIR / "general_ledger.csv",
              ["entry_number", "journal_code", "line_no", "entry_date", "account_number",
               "aux_account", "piece_ref", "description", "debit", "credit",
               "created_by", "created_at"], ledger_rows)
    write_csv(DATA_DIR / "chart_of_accounts.csv",
              ["account_number", "account_label", "account_type"], ACCOUNTS)
    write_csv(DATA_DIR / "journals.csv", ["journal_code", "journal_label", "is_manual"], JOURNALS)
    write_csv(DATA_DIR / "users.csv",
              ["user_id", "full_name", "job_title", "is_system", "posting_allowed"], USERS)
    write_csv(DATA_DIR / "public_holidays.csv", ["holiday_date", "holiday_name"], PUBLIC_HOLIDAYS)
    # Manual cases first, then duplicates, split payments and numbering gaps.
    case_order = sorted(ledger.planted, key=lambda case: ("ADPG".index(case.case_id[0]), case.case_id))
    write_csv(VALIDATION_DIR / "planted_anomalies.csv",
              ["case_id", "entry_number", "scenario", "expected_tests", "story"],
              [[case.case_id, case.entry.number, case.scenario, case.expected_tests, case.story]
               for case in case_order])
    return len(kept), len(ledger_rows)


def main():
    rng = random.Random(SEED)
    ledger = Ledger()

    sales = generate_sales(ledger, rng)
    plant_sequence_gaps(ledger, rng, sales)  # before receipts: deleted invoices are never paid
    generate_receipts(ledger, rng, sales)
    purchases = generate_purchases(ledger, rng)
    generate_supplier_payments(ledger, rng, purchases)
    generate_monthly_entries(ledger, rng)
    generate_reclassifications(ledger, rng)
    generate_year_end_entries(ledger, rng)

    plant_manual_anomalies(ledger)
    plant_duplicates(ledger, rng, purchases)
    plant_split_payments(ledger, rng)

    assign_entry_numbers(ledger)
    entry_count, line_count = export(ledger)
    print(f"General ledger written: {entry_count:,} entries, {line_count:,} lines")
    print(f"Planted anomalies: {len(ledger.planted)} cases -> validation/planted_anomalies.csv")


if __name__ == "__main__":
    main()
