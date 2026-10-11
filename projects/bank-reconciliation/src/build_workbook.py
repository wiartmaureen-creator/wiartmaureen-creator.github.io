"""Build bank_reconciliation.xlsx with Excel itself (COM automation, Windows only).

The workbook is a reusable tool, not a static report:
  * Power Query imports the bank's CSV export and the ledger extract
    (folder and file names come from the Settings sheet);
  * formulas in the two tables match every bank line to a ledger entry,
    first by reference, then by amount and date;
  * the Reconciliation sheet produces the bank reconciliation statement
    and integrity checks; the Actions sheet lists what is left to explain,
    with a proposed action for each item.

After building, the script refreshes the queries a second time (to prove
the formulas survive a refresh), reads the results back, checks them
against an independent pandas calculation and against the answer key,
exports images for the case study and writes results/summary.json.

Usage:
    python src/build_workbook.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pythoncom
import win32com.client as win32

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
RESULTS_DIR = PROJECT_DIR / "results"
IMAGES_DIR = PROJECT_DIR / "images"
WORKBOOK_PATH = PROJECT_DIR / "bank_reconciliation.xlsx"
VALIDATION_DIR = PROJECT_DIR / "validation"

BANK_FILE = "bank_statement_2025-12.csv"
LEDGER_FILE = "ledger_bank_2025-12.csv"
DATE_TOLERANCE_DAYS = 5

# Excel constants
XL_SRC_EXTERNAL = 0
XL_YES = 1
XL_CMD_SQL = 2
XL_OPEN_XML_WORKBOOK = 51
XL_BAR_CLUSTERED = 57
XL_CELL_VALUE = 1
XL_EQUAL = 3
XL_EXPRESSION = 2

INK = (11, 11, 11)
BLUE = (42, 120, 214)
INPUT_BLUE = (0, 0, 255)
SOFT_BLUE = (230, 239, 251)
GREY = (82, 81, 78)
LIGHT_GREY = (240, 239, 236)
GREEN = (0, 99, 0)
SOFT_GREEN = (226, 244, 226)
RED = (208, 59, 59)
SOFT_RED = (251, 230, 230)
SOFT_AMBER = (254, 243, 214)


def rgb(color):
    r, g, b = color
    return r + g * 256 + b * 65536


def set_format(range_, number_format):
    """Set a number format in English codes whatever the language of Excel.

    Through COM, Excel reads NumberFormat in the user's locale (on a French
    Excel "yyyy" is rejected). Passing LCID 1033 forces the English codes."""
    dispid = range_._oleobj_.GetIDsOfNames("NumberFormat")
    range_._oleobj_.Invoke(dispid, 1033, pythoncom.DISPATCH_PROPERTYPUT, 0, number_format)


# --- Power Query (M) ---------------------------------------------------------------

M_SETTING = 'Excel.CurrentWorkbook(){{[Name="{name}"]}}[Content]{{0}}[Column1]'

BANK_QUERY = f"""let
    // Folder and file name come from the Settings sheet, so next month only needs a new file.
    Folder = {M_SETTING.format(name="DataFolder")},
    FileName = {M_SETTING.format(name="BankFile")},
    Source = Csv.Document(File.Contents(Folder & FileName), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    // Rename by position: bank exports change their header wording more often than their layout.
    Renamed = Table.RenameColumns(Promoted, List.Zip({{Table.ColumnNames(Promoted), {{"Date", "ValueDate", "Label", "Debit", "Credit"}}}})),
    BlanksToNull = Table.ReplaceValue(Renamed, "", null, Replacer.ReplaceValue, {{"Debit", "Credit"}}),
    // French bank format: dd/mm/yyyy dates and comma decimals.
    Typed = Table.TransformColumnTypes(BlanksToNull, {{{{"Date", type date}}, {{"ValueDate", type date}}, {{"Debit", type number}}, {{"Credit", type number}}}}, "fr-FR"),
    Cleaned = Table.TransformColumns(Typed, {{{{"Label", each Text.Trim(Text.Clean(_)), type text}}}}),
    WithAmount = Table.AddColumn(Cleaned, "Amount", each (if [Credit] = null then 0 else [Credit]) - (if [Debit] = null then 0 else [Debit]), type number),
    // The ERP reference, when the bank kept it, follows "/REF " in the label.
    WithReference = Table.AddColumn(WithAmount, "Reference", each if Text.Contains([Label], "/REF ") then Text.Trim(Text.AfterDelimiter([Label], "/REF ")) else "", type text),
    Indexed = Table.AddIndexColumn(WithReference, "Row", 1, 1, Int64.Type),
    WithId = Table.AddColumn(Indexed, "BankId", each "B" & Text.PadStart(Text.From([Row]), 3, "0"), type text),
    Result = Table.SelectColumns(WithId, {{"BankId", "Date", "Label", "Reference", "Amount"}})
in
    Result"""

LEDGER_QUERY = f"""let
    Folder = {M_SETTING.format(name="DataFolder")},
    FileName = {M_SETTING.format(name="LedgerFile")},
    PeriodStart = Date.From({M_SETTING.format(name="PeriodStart")}),
    PeriodEnd = Date.From({M_SETTING.format(name="PeriodEnd")}),
    Source = Csv.Document(File.Contents(Folder & FileName), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{{{"entry_date", type date}}, {{"debit", type number}}, {{"credit", type number}}}}, "en-US"),
    InPeriod = Table.SelectRows(Typed, each [entry_date] >= PeriodStart and [entry_date] <= PeriodEnd),
    // Bank account convention: a debit increases the balance, a credit decreases it.
    WithAmount = Table.AddColumn(InPeriod, "Amount", each [debit] - [credit], type number),
    Renamed = Table.RenameColumns(WithAmount, {{{{"entry_number", "Entry"}}, {{"entry_date", "Date"}}, {{"piece_ref", "Reference"}}, {{"description", "Description"}}}}),
    Selected = Table.SelectColumns(Renamed, {{"Entry", "Date", "Reference", "Description", "Amount"}}),
    Sorted = Table.Sort(Selected, {{{{"Date", Order.Ascending}}, {{"Entry", Order.Ascending}}}})
in
    Sorted"""

# --- Formulas ----------------------------------------------------------------------

LEDGER_COLUMNS = [
    ("MatchedByRef", "=COUNTIF(tblBank[Reference],[@Reference])>0"),
]
# Only functions available since Excel 2016 (INDEX/MATCH, COUNTIFS, SUMIFS...): the tool
# must run on the older Excel versions many finance teams still use, not only Microsoft 365.
# INDEX(<array>,0) lets MATCH test several conditions without Ctrl+Shift+Enter.
LEDGER_COLUMNS_AFTER_BANK = [
    ("BankId", '=IFERROR(INDEX(tblBank[BankId],MATCH([@Entry],tblBank[MatchedEntry],0)),"")'),
    ("Status", '=IF([@BankId]<>"","Matched",IF([@Amount]>0,"Deposit in transit","Outstanding payment"))'),
    ("Action", '=IF([@Status]="Matched","",IF([@Status]="Deposit in transit",'
               '"Check it is credited on the January statement","Check it is debited on the January statement"))'),
    ("ItemNo", '=IF([@Status]="Matched","",COUNTIF(tblBank[Status],"<>Matched")'
               '+COUNTIF(INDEX([Status],1):[@Status],"<>Matched"))'),
]
BANK_COLUMNS = [
    ("RefEntry", '=IF([@Reference]="","",IFERROR(INDEX(tblLedger[Entry],MATCH([@Reference],tblLedger[Reference],0)),""))'),
    ("AmountEntry", '=IF([@RefEntry]<>"","",IFERROR(INDEX(tblLedger[Entry],MATCH(1,INDEX((tblLedger[Amount]=[@Amount])'
                    '*(tblLedger[MatchedByRef]=FALSE)*(ABS(tblLedger[Date]-[@Date])<=DateTolerance),0),0)),""))'),
    ("MatchedEntry", '=IF([@RefEntry]<>"",[@RefEntry],[@AmountEntry])'),
    ("MatchRule", '=IF([@RefEntry]<>"","Reference",IF([@AmountEntry]<>"","Amount and date","None"))'),
    ("BookAmount", '=IF([@MatchedEntry]="","",INDEX(tblLedger[Amount],MATCH([@MatchedEntry],tblLedger[Entry],0)))'),
    ("Difference", '=IF([@MatchedEntry]="",0,ROUND([@Amount]-[@BookAmount],2))'),
    ("Status", '=IF([@MatchedEntry]="","Not in books",IF([@Difference]<>0,"Amount difference","Matched"))'),
    ("Category", '=IF([@Status]="Matched","",IF([@Status]="Amount difference","Amount difference",'
                 'IFERROR(INDEX(tblRules[Category],MATCH(TRUE,INDEX(ISNUMBER(SEARCH(tblRules[Keyword],[@Label])),0),0)),"Other")))'),
    ("Action", '=IF([@Status]="Matched","",IF([@Status]="Amount difference",'
               '"Check the invoice: the bank and the ledger show different amounts",'
               'IFERROR(INDEX(tblRules[Action],MATCH(TRUE,INDEX(ISNUMBER(SEARCH(tblRules[Keyword],[@Label])),0),0)),'
               '"Investigate with the bank")))'),
    ("ItemNo", '=IF([@Status]="Matched","",COUNTIF(INDEX([Status],1):[@Status],"<>Matched"))'),
]

RULES = [
    ("Keyword", "Category", "Action", "Account"),
    ("FRAIS", "Bank charges", "Book the bank charges", "627000"),
    ("COMMISSION", "Bank charges", "Book the bank charges", "627000"),
    ("AGIOS", "Bank interest", "Book the bank interest", "661600"),
    ("PRLV", "Direct debit not booked", "Find the supplier invoice and book the direct debit", "401000"),
    ("VIR SEPA RECU", "Unidentified receipt", "Identify the customer and allocate the receipt (suspense 471000 meanwhile)", "471000"),
    ("VIR SEPA EMIS", "Unidentified payment", "Find the invoice behind this transfer", "471000"),
]

ACTION_ROWS = 40  # capacity of the Actions sheet; the item count is checked against it

# Actions sheet: item n is looked up in the Bank table first, then in the Ledger table.
ACTION_COLUMNS = [
    ("Source", '"Bank "&INDEX(tblBank[BankId],MATCH($A{r},tblBank[ItemNo],0))',
     '"Books "&INDEX(tblLedger[Entry],MATCH($A{r},tblLedger[ItemNo],0))'),
    ("Date", 'INDEX(tblBank[Date],MATCH($A{r},tblBank[ItemNo],0))',
     'INDEX(tblLedger[Date],MATCH($A{r},tblLedger[ItemNo],0))'),
    ("Description", 'INDEX(tblBank[Label],MATCH($A{r},tblBank[ItemNo],0))',
     'INDEX(tblLedger[Description],MATCH($A{r},tblLedger[ItemNo],0))'),
    ("Amount (EUR)", 'INDEX(tblBank[Amount],MATCH($A{r},tblBank[ItemNo],0))',
     'INDEX(tblLedger[Amount],MATCH($A{r},tblLedger[ItemNo],0))'),
    ("Category", 'INDEX(tblBank[Category],MATCH($A{r},tblBank[ItemNo],0))',
     'INDEX(tblLedger[Status],MATCH($A{r},tblLedger[ItemNo],0))'),
    ("Proposed action", 'INDEX(tblBank[Action],MATCH($A{r},tblBank[ItemNo],0))',
     'INDEX(tblLedger[Action],MATCH($A{r},tblLedger[ItemNo],0))'),
]


# --- Helpers -----------------------------------------------------------------------

def style_title(cell, size=16):
    cell.Font.Size = size
    cell.Font.Bold = True
    cell.Font.Color = rgb(INK)


def label_value(ws, row, label, formula, number_format="#,##0.00;-#,##0.00;0.00", bold=False, note=None, col="B"):
    ws.Range(f"{col}{row}").Value = label
    value_col = chr(ord(col) + 1)
    ws.Range(f"{value_col}{row}").Formula = formula
    set_format(ws.Range(f"{value_col}{row}"), number_format)
    if bold:
        ws.Range(f"{col}{row}:{value_col}{row}").Font.Bold = True
    if note:
        note_col = chr(ord(col) + 2)
        ws.Range(f"{note_col}{row}").Formula = note if note.startswith("=") else note
        ws.Range(f"{note_col}{row}").Font.Color = rgb(GREY)


def hide_gridlines(wb, ws):
    try:
        ws.Activate()
        wb.Windows(1).DisplayGridlines = False
    except Exception:  # cosmetic only
        pass


def load_query(ws, query_name, table_name):
    source = ("OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;"
              f"Location={query_name};Extended Properties=\"\"")
    table = ws.ListObjects.Add(XL_SRC_EXTERNAL, source, True, XL_YES, ws.Range("$A$1"))
    table.Name = table_name
    query_table = table.QueryTable
    query_table.CommandType = XL_CMD_SQL
    query_table.CommandText = f"SELECT * FROM [{query_name}]"
    query_table.BackgroundQuery = False
    query_table.RefreshOnFileOpen = False
    query_table.PreserveColumnInfo = True
    query_table.AdjustColumnWidth = True
    query_table.Refresh(False)
    table.TableStyle = "TableStyleMedium2"
    return table


def add_formula_column(table, name, formula, number_format=None):
    column = table.ListColumns.Add()
    column.Name = name
    column.DataBodyRange.Formula = formula
    if number_format:
        set_format(column.DataBodyRange, number_format)
    return column


def colour_status(range_, value, font, fill):
    condition = range_.FormatConditions.Add(XL_CELL_VALUE, XL_EQUAL, f'="{value}"')
    condition.Font.Color = rgb(font)
    condition.Interior.Color = rgb(fill)


def export_range(excel, ws, address, path):
    """Copy a range as a picture into a temporary chart and save it as PNG."""
    ws.Activate()
    rng = ws.Range(address)
    for attempt in range(5):
        try:
            rng.CopyPicture(1, 2)  # xlScreen, xlBitmap
            holder = ws.ChartObjects().Add(rng.Left, rng.Top, rng.Width, rng.Height)
            holder.Chart.ChartArea.Format.Line.Visible = False
            holder.Activate()
            time.sleep(0.4)
            holder.Chart.Paste()
            time.sleep(0.4)
            holder.Chart.Export(str(path))
            holder.Delete()
            return True
        except Exception:
            time.sleep(1)
    print(f"  image export failed: {path.name}")
    return False


# --- Build ------------------------------------------------------------------------

def build(excel):
    wb = excel.Workbooks.Add()
    wb.Styles("Normal").Font.Name = "Arial"
    wb.Styles("Normal").Font.Size = 10

    names = ["Start", "Summary", "Reconciliation", "Actions", "Bank", "Ledger", "Rules", "Settings"]
    while wb.Worksheets.Count < len(names):
        wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
    sheets = {}
    for index, name in enumerate(names, start=1):
        wb.Worksheets(index).Name = name
        sheets[name] = wb.Worksheets(index)

    # Settings: every input in one place, blue = editable.
    st = sheets["Settings"]
    style_title(st.Range("B2"))
    st.Range("B2").Value = "Settings"
    st.Range("B3").Value = "Blue cells are inputs. Change them for another month, then Data > Refresh All."
    st.Range("B3").Font.Color = rgb(GREY)
    settings = [
        (5, "Data folder (automatic: the data folder next to this file)",
         '=LEFT(CELL("filename",A1),FIND("[",CELL("filename",A1))-1)&"data\\"', "DataFolder", None, "@", False),
        (6, "Bank statement file", BANK_FILE, "BankFile", None, "@", True),
        (7, "Ledger extract file (account 512000)", LEDGER_FILE, "LedgerFile", None, "@", True),
        (9, "Period start", "=DATE(2025,12,1)", "PeriodStart", None, "dd/mm/yyyy", True),
        (10, "Period end", "=DATE(2025,12,31)", "PeriodEnd", None, "dd/mm/yyyy", True),
        (12, "Opening balance per bank statement", None, "OpeningBank", "From the November statement", "#,##0.00", True),
        (13, "Opening balance per books", None, "OpeningBooks", "From the November reconciliation", "#,##0.00", True),
        (14, "Closing balance printed on the bank statement", None, "StatementClosing",
         "Typed from the statement: used to check the CSV import is complete", "#,##0.00", True),
        (16, "Date tolerance for amount matching (days)", DATE_TOLERANCE_DAYS, "DateTolerance",
         "A bank line without reference is matched to a ledger line with the same amount within this many days", "0", True),
    ]
    with (VALIDATION_DIR / "statement_header.csv").open(encoding="utf-8") as handle:
        header = next(csv.DictReader(handle))
    balances = {"OpeningBank": float(header["opening_balance"]),
                "OpeningBooks": float(header["opening_balance"]),
                "StatementClosing": float(header["closing_balance"])}
    for row, label, value, name, note, number_format, is_input in settings:
        st.Range(f"B{row}").Value = label
        cell = st.Range(f"C{row}")
        if value is None:
            value = balances[name]
        if isinstance(value, str) and value.startswith("="):
            cell.Formula = value
        else:
            cell.Value = value
        set_format(cell, number_format)
        if number_format == "@" and not str(value).startswith("="):
            cell.Value = value
        cell.Font.Color = rgb(INPUT_BLUE if is_input else INK)
        if is_input:
            cell.Interior.Color = rgb(SOFT_BLUE)
        cell.HorizontalAlignment = -4131  # left
        wb.Names.Add(name, f"=Settings!$C${row}")
        if note:
            st.Range(f"D{row}").Value = note
            st.Range(f"D{row}").Font.Color = rgb(GREY)
    st.Columns("B").ColumnWidth = 52
    st.Columns("C").ColumnWidth = 34
    st.Columns("D").ColumnWidth = 70
    hide_gridlines(wb, st)

    # Rules: keyword -> category, action, account.
    rl = sheets["Rules"]
    style_title(rl.Range("B2"))
    rl.Range("B2").Value = "Classification rules for unmatched bank lines"
    rl.Range("B3").Value = "The first keyword found in the bank label wins. Add a row to teach the workbook a new case."
    rl.Range("B3").Font.Color = rgb(GREY)
    for r, values in enumerate(RULES, start=5):
        for c, value in enumerate(values, start=2):
            rl.Cells(r, c).NumberFormat = "@"
            rl.Cells(r, c).Value = value
    rules_table = rl.ListObjects.Add(1, rl.Range(f"B5:E{4 + len(RULES)}"), None, XL_YES)
    rules_table.Name = "tblRules"
    rules_table.TableStyle = "TableStyleMedium2"
    for col, width in zip("BCDE", (18, 26, 70, 12)):
        rl.Columns(col).ColumnWidth = width
    hide_gridlines(wb, rl)

    wb.SaveAs(str(WORKBOOK_PATH), XL_OPEN_XML_WORKBOOK)
    excel.CalculateFull()  # CELL("filename") needs a saved file

    # Power Query: import both files.
    wb.Queries.FastCombine = True  # settings and files are combined in one query
    wb.Queries.Add("BankStatement", BANK_QUERY, "Bank CSV export, cleaned and typed")
    wb.Queries.Add("LedgerBank", LEDGER_QUERY, "Ledger lines of the bank account for the period")
    ledger = load_query(sheets["Ledger"], "LedgerBank", "tblLedger")
    bank = load_query(sheets["Bank"], "BankStatement", "tblBank")

    for name, formula in LEDGER_COLUMNS:
        add_formula_column(ledger, name, formula)
    for name, formula in BANK_COLUMNS:
        number_format = "#,##0.00;-#,##0.00;0.00" if name in ("BookAmount", "Difference") else None
        add_formula_column(bank, name, formula, number_format)
    for name, formula in LEDGER_COLUMNS_AFTER_BANK:
        add_formula_column(ledger, name, formula)

    for table, date_col, amount_col in ((bank, "Date", "Amount"), (ledger, "Date", "Amount")):
        set_format(table.ListColumns(date_col).DataBodyRange, "dd/mm/yyyy")
        set_format(table.ListColumns(amount_col).DataBodyRange, "#,##0.00;-#,##0.00;0.00")
        status = table.ListColumns("Status").DataBodyRange
        colour_status(status, "Matched", GREEN, SOFT_GREEN)
        for value in ("Not in books", "Amount difference"):
            colour_status(status, value, RED, SOFT_RED)
        for value in ("Deposit in transit", "Outstanding payment"):
            colour_status(status, value, INK, SOFT_AMBER)
    sheets["Bank"].Columns("C").ColumnWidth = 58
    sheets["Ledger"].Columns("D").ColumnWidth = 44
    for ws in (sheets["Bank"], sheets["Ledger"]):
        ws.Columns("A:Q").AutoFit()
        ws.Columns("C").ColumnWidth = min(ws.Columns("C").ColumnWidth, 58)
    sheets["Bank"].Columns("N").ColumnWidth = 62
    sheets["Bank"].Columns("C").ColumnWidth = 50
    sheets["Ledger"].Columns("I").ColumnWidth = 48

    build_reconciliation(wb, sheets["Reconciliation"])
    build_actions(wb, sheets["Actions"])
    build_summary(wb, sheets["Summary"])
    build_start(wb, sheets["Start"])

    sheets["Start"].Activate()
    excel.CalculateFull()
    wb.Save()
    return wb


def build_reconciliation(wb, ws):
    style_title(ws.Range("B2"), 18)
    ws.Range("B2").Value = "Bank reconciliation statement"
    ws.Range("B3").Formula = '="Lumen Supplies SAS  ·  Bank account 512000  ·  Period ended "&TEXT(DAY(PeriodEnd),"00")&"/"&TEXT(MONTH(PeriodEnd),"00")&"/"&YEAR(PeriodEnd)'
    ws.Range("B3").Font.Color = rgb(GREY)
    ws.Range("C5").Value = "Amount (EUR)"
    ws.Range("D5").Value = "Items"
    ws.Range("B5:D5").Font.Bold = True
    ws.Range("B5:D5").Interior.Color = rgb(LIGHT_GREY)

    ws.Range("B6").Value = "A. Balance per bank"
    ws.Range("B6").Font.Bold = True
    label_value(ws, 7, "Closing balance per bank statement", "=StatementClosing")
    label_value(ws, 8, "Add: deposits in transit (in the books, not yet on the statement)",
                '=SUMIFS(tblLedger[Amount],tblLedger[Status],"Deposit in transit")',
                note='=COUNTIFS(tblLedger[Status],"Deposit in transit")')
    label_value(ws, 9, "Less: outstanding payments (in the books, not yet debited)",
                '=SUMIFS(tblLedger[Amount],tblLedger[Status],"Outstanding payment")',
                note='=COUNTIFS(tblLedger[Status],"Outstanding payment")')
    label_value(ws, 10, "Adjusted bank balance", "=SUM(C7:C9)", bold=True)

    ws.Range("B12").Value = "B. Balance per books"
    ws.Range("B12").Font.Bold = True
    label_value(ws, 13, "Closing balance per books", "=OpeningBooks+SUM(tblLedger[Amount])")
    label_value(ws, 14, "Add/less: bank items not yet booked",
                '=SUMIFS(tblBank[Amount],tblBank[Status],"Not in books")',
                note='=COUNTIFS(tblBank[Status],"Not in books")')
    label_value(ws, 15, "Add/less: amounts keyed differently in the books",
                '=SUMIFS(tblBank[Difference],tblBank[Status],"Amount difference")',
                note='=COUNTIFS(tblBank[Status],"Amount difference")')
    label_value(ws, 16, "Adjusted book balance", "=SUM(C13:C15)", bold=True)

    label_value(ws, 18, "Unexplained difference (A - B)", "=ROUND(C10-C16,2)", bold=True)
    ws.Range("D18").Formula = '=IF(C18=0,"✓ Reconciled","✗ Not reconciled")'
    ws.Range("D18").Font.Bold = True
    colour_status(ws.Range("D18"), "✓ Reconciled", GREEN, SOFT_GREEN)
    colour_status(ws.Range("D18"), "✗ Not reconciled", RED, SOFT_RED)
    for row in (10, 16, 18):
        ws.Range(f"B{row}:D{row}").Borders(8).Weight = 2  # top border

    ws.Range("B20").Value = "Integrity checks"
    ws.Range("B20").Font.Bold = True
    ws.Range("B20:D20").Interior.Color = rgb(LIGHT_GREY)
    checks = [
        (21, "Imported statement lines add up to the printed closing balance",
         "=ROUND(OpeningBank+SUM(tblBank[Amount])-StatementClosing,2)", "Import complete"),
        (22, "Opening balances agree (bank vs books)", "=ROUND(OpeningBank-OpeningBooks,2)", "Opening agreed"),
        (23, "No ledger entry is matched to two bank lines",
         '=SUMPRODUCT((tblBank[MatchedEntry]<>"")*(COUNTIF(tblBank[MatchedEntry],tblBank[MatchedEntry])>1))', "No double match"),
    ]
    for row, label, formula, ok_text in checks:
        label_value(ws, row, label, formula)
        ws.Range(f"D{row}").Formula = f'=IF(C{row}=0,"✓ {ok_text}","✗ Check")'
        colour_status(ws.Range(f"D{row}"), f"✓ {ok_text}", GREEN, SOFT_GREEN)
        colour_status(ws.Range(f"D{row}"), "✗ Check", RED, SOFT_RED)
    ws.Columns("A").ColumnWidth = 2
    ws.Columns("B").ColumnWidth = 62
    ws.Columns("C").ColumnWidth = 16
    ws.Columns("D").ColumnWidth = 22
    ws.Range("D6:D23").HorizontalAlignment = -4108  # centre
    hide_gridlines(wb, ws)


def build_actions(wb, ws):
    style_title(ws.Range("A1"), 16)
    ws.Range("A1").Value = "Items to explain and proposed actions"
    ws.Range("A2").Value = ("Filled automatically from the Bank and Ledger tables: bank-side items first, "
                            "then items that are only in the books.")
    ws.Range("A2").Font.Color = rgb(GREY)
    ws.Range("I2").Value = "Items"
    ws.Range("J2").Formula = '=COUNTIF(tblBank[Status],"<>Matched")+COUNTIF(tblLedger[Status],"<>Matched")'
    ws.Range("I3").Value = "Capacity"
    ws.Range("J3").Value = ACTION_ROWS
    ws.Range("K2").Formula = '=IF(J2<=J3,"","✗ Extend the list")'
    ws.Range("I2:K3").Font.Color = rgb(GREY)
    headers = ["#"] + [name for name, _, _ in ACTION_COLUMNS]
    for c, header in enumerate(headers, start=1):
        ws.Cells(4, c).Value = header
    ws.Range("A4:G4").Font.Bold = True
    ws.Range("A4:G4").Font.Color = rgb((255, 255, 255))
    ws.Range("A4:G4").Interior.Color = rgb(BLUE)
    for r in range(5, 5 + ACTION_ROWS):
        ws.Range(f"A{r}").Formula = f'=IF(ROW()-4<=$J$2,ROW()-4,"")'
        for c, (_, bank_part, books_part) in enumerate(ACTION_COLUMNS, start=2):
            bank_formula = bank_part.format(r=r)
            books_formula = books_part.format(r=r)
            ws.Cells(r, c).Formula = f'=IF($A{r}="","",IFERROR({bank_formula},{books_formula}))'
    last = 4 + ACTION_ROWS
    set_format(ws.Range(f"C5:C{last}"), "dd/mm/yyyy")
    set_format(ws.Range(f"E5:E{last}"), "#,##0.00;-#,##0.00;0.00")
    ws.Range(f"A5:A{last}").HorizontalAlignment = -4108
    for col, width in zip("ABCDEFG", (5, 19, 12, 58, 14, 24, 66)):
        ws.Columns(col).ColumnWidth = width
    hide_gridlines(wb, ws)


def build_summary(wb, ws):
    style_title(ws.Range("B2"), 18)
    ws.Range("B2").Value = "December 2025 bank reconciliation"
    ws.Range("B3").Value = "Lumen Supplies SAS (fictitious)  ·  refresh with Data > Refresh All"
    ws.Range("B3").Font.Color = rgb(GREY)

    kpis = [
        ("B", "Bank lines", "=ROWS(tblBank[BankId])", "0"),
        ("D", "Matched automatically", '=COUNTIFS(tblBank[Status],"Matched")/ROWS(tblBank[BankId])', "0.0%"),
        ("F", "Items to explain", '=COUNTIFS(tblBank[Status],"<>Matched")+COUNTIFS(tblLedger[Status],"<>Matched")', "0"),
        ("H", "Result", "=Reconciliation!D18", "@"),
    ]
    for col, label, formula, number_format in kpis:
        ws.Range(f"{col}5").Value = label
        ws.Range(f"{col}5").Font.Color = rgb(GREY)
        cell = ws.Range(f"{col}6")
        cell.Formula = formula
        set_format(cell, number_format)
        cell.Font.Size = 20
        cell.Font.Bold = True
        cell.HorizontalAlignment = -4131
    colour_status(ws.Range("H6"), "✓ Reconciled", GREEN, SOFT_GREEN)

    ws.Range("B9").Value = "Bank lines by matching result"
    ws.Range("B9").Font.Bold = True
    rows = [
        ("Matched by reference", '=COUNTIFS(tblBank[MatchRule],"Reference",tblBank[Status],"Matched")'),
        ("Matched by amount and date", '=COUNTIFS(tblBank[MatchRule],"Amount and date",tblBank[Status],"Matched")'),
        ("Matched, amount differs", '=COUNTIFS(tblBank[Status],"Amount difference")'),
        ("Not in the books", '=COUNTIFS(tblBank[Status],"Not in books")'),
    ]
    ws.Range("B10").Value = "Result"
    ws.Range("C10").Value = "Lines"
    ws.Range("B10:C10").Font.Bold = True
    ws.Range("B10:C10").Interior.Color = rgb(LIGHT_GREY)
    for offset, (label, formula) in enumerate(rows, start=11):
        ws.Range(f"B{offset}").Value = label
        ws.Range(f"C{offset}").Formula = formula

    ws.Range("B17").Value = "Reconciling items by category"
    ws.Range("B17").Font.Bold = True
    ws.Range("B18").Value = "Category"
    ws.Range("C18").Value = "Items"
    ws.Range("D18").Value = "Amount (EUR)"
    ws.Range("B18:D18").Font.Bold = True
    ws.Range("B18:D18").Interior.Color = rgb(LIGHT_GREY)
    categories = ["Deposit in transit", "Outstanding payment", "Bank charges", "Direct debit not booked",
                  "Unidentified receipt", "Amount difference"]
    for offset, category in enumerate(categories, start=19):
        ws.Range(f"B{offset}").Value = category
        # Timing items live in the Ledger table, the others in the Bank table.
        ws.Range(f"C{offset}").Formula = (f'=COUNTIFS(tblLedger[Status],B{offset})'
                                          f'+COUNTIFS(tblBank[Category],B{offset})')
        ws.Range(f"D{offset}").Formula = (f'=IF(B{offset}="Amount difference",'
                                          f'SUMIFS(tblBank[Difference],tblBank[Status],"Amount difference"),'
                                          f'SUMIFS(tblLedger[Amount],tblLedger[Status],B{offset})'
                                          f'+SUMIFS(tblBank[Amount],tblBank[Category],B{offset}))')
        set_format(ws.Range(f"D{offset}"), "#,##0.00;-#,##0.00;0.00")

    chart_shape = ws.Shapes.AddChart2(-1, XL_BAR_CLUSTERED, ws.Range("F9").Left, ws.Range("F9").Top, 430, 230)
    chart = chart_shape.Chart
    chart.SetSourceData(ws.Range("B10:C14"))
    chart.HasTitle = True
    chart.ChartTitle.Text = "Bank lines by matching result"
    chart.HasLegend = False
    chart.SeriesCollection(1).Format.Fill.ForeColor.RGB = rgb(BLUE)
    chart.SeriesCollection(1).HasDataLabels = True
    chart.Axes(1).ReversePlotOrder = True

    ws.Columns("A").ColumnWidth = 2
    ws.Columns("B").ColumnWidth = 30
    for col in "CDEFGH":
        ws.Columns(col).ColumnWidth = 16
    hide_gridlines(wb, ws)


def build_start(wb, ws):
    style_title(ws.Range("B2"), 20)
    ws.Range("B2").Value = "Bank reconciliation tool"
    ws.Range("B3").Value = "Lumen Supplies SAS (fictitious company)  ·  December 2025  ·  portfolio project by Maureen Wiart"
    ws.Range("B3").Font.Color = rgb(GREY)
    lines = [
        ("Why", "Reconciling the bank statement with the ledger every month is slow when done by hand, "
                "and errors slip through. This workbook does the matching and lists only what needs a human."),
        ("How to use it", "1. Save next month's bank CSV export and ledger extract in the data folder."),
        ("", "2. Update the file names, period and balances on the Settings sheet (blue cells)."),
        ("", "3. Data > Refresh All. Then read Summary, Reconciliation and Actions."),
        ("How it works", "Power Query imports and cleans both files (French date and number formats, label cleaning, "
                         "reference extraction)."),
        ("", "Each bank line is matched to a ledger entry by reference (XLOOKUP); lines without a reference "
             "are matched on amount within a date tolerance."),
        ("", "Unmatched lines are classified with the keyword rules on the Rules sheet, which propose an action."),
        ("Sheets", "Summary · Reconciliation · Actions · Bank · Ledger · Rules · Settings"),
        ("Colour code", "Blue text on blue fill = input you can change. Green = matched / check passed. "
                        "Amber = timing difference. Red = needs action."),
    ]
    for offset, (title, text) in enumerate(lines, start=5):
        ws.Range(f"B{offset}").Value = title
        ws.Range(f"B{offset}").Font.Bold = True
        ws.Range(f"C{offset}").Value = text
    ws.Columns("A").ColumnWidth = 2
    ws.Columns("B").ColumnWidth = 16
    ws.Columns("C").ColumnWidth = 120
    hide_gridlines(wb, ws)


# --- Verification ----------------------------------------------------------------

def read_table(ws, table_name):
    table = ws.ListObjects(table_name)
    headers = [c.Name for c in table.ListColumns]
    values = table.DataBodyRange.Value
    return pd.DataFrame(list(values), columns=headers)


def independent_check(bank_xl, ledger_xl):
    """Recompute the matching in pandas from the raw CSV files."""
    bank = pd.read_csv(DATA_DIR / BANK_FILE, sep=";", dtype=str, keep_default_na=False)
    bank.columns = ["Date", "ValueDate", "Label", "Debit", "Credit"]
    to_num = lambda s: pd.to_numeric(s.str.replace(",", "."), errors="coerce").fillna(0.0)
    bank["Amount"] = (to_num(bank["Credit"]) - to_num(bank["Debit"])).round(2)
    bank["Date"] = pd.to_datetime(bank["Date"], format="%d/%m/%Y")
    bank["Reference"] = bank["Label"].str.split("/REF ").str[1].fillna("").str.strip()

    ledger = pd.read_csv(DATA_DIR / LEDGER_FILE)
    ledger["Amount"] = (ledger["debit"] - ledger["credit"]).round(2)
    ledger["Date"] = pd.to_datetime(ledger["entry_date"])
    ledger = ledger.sort_values(["Date", "entry_number"]).reset_index(drop=True)
    ledger["MatchedByRef"] = ledger["piece_ref"].isin(set(bank["Reference"]))

    matched = []
    for _, line in bank.iterrows():
        entry = ""
        if line["Reference"]:
            hit = ledger.loc[ledger["piece_ref"] == line["Reference"], "entry_number"]
            entry = hit.iloc[0] if len(hit) else ""
        if not entry:
            pool = ledger[(ledger["Amount"] == line["Amount"]) & (~ledger["MatchedByRef"])
                          & ((ledger["Date"] - line["Date"]).abs().dt.days <= DATE_TOLERANCE_DAYS)]
            entry = pool["entry_number"].iloc[0] if len(pool) else ""
        matched.append(entry)
    bank["MatchedEntry"] = matched
    agree = (bank["MatchedEntry"].tolist() == bank_xl["MatchedEntry"].tolist())
    unmatched_ledger = set(ledger["entry_number"]) - set(bank["MatchedEntry"])
    agree_ledger = unmatched_ledger == set(ledger_xl.loc[ledger_xl["Status"] != "Matched", "Entry"])
    return agree and agree_ledger


def verify(excel, wb):
    bank_xl = read_table(wb.Worksheets("Bank"), "tblBank")
    ledger_xl = read_table(wb.Worksheets("Ledger"), "tblLedger")
    rec = wb.Worksheets("Reconciliation")
    def value(address):
        raw = rec.Range(address).Value
        return round(raw, 2) if isinstance(raw, float) else raw

    statement = {
        "bank_closing": value("C7"), "deposits_in_transit": value("C8"), "deposits_in_transit_count": value("D8"),
        "outstanding_payments": value("C9"), "outstanding_payments_count": value("D9"),
        "adjusted_bank": value("C10"), "book_closing": value("C13"),
        "bank_items_not_booked": value("C14"), "bank_items_not_booked_count": value("D14"),
        "amount_differences": value("C15"), "amount_differences_count": value("D15"),
        "adjusted_book": value("C16"), "difference": value("C18"), "result": value("D18"),
        "checks": [rec.Range(f"D{r}").Value for r in (21, 22, 23)],
    }

    actions_ws = wb.Worksheets("Actions")
    actions = []
    row = 5
    while actions_ws.Cells(row, 1).Value:
        source, date, description, amount, category, action = [actions_ws.Cells(row, c).Value for c in range(2, 8)]
        actions.append({"source": source, "date": date.strftime("%Y-%m-%d") if date else "",
                        "description": description, "amount": round(amount, 2),
                        "category": category, "action": action})
        row += 1

    expected = list(csv.DictReader((VALIDATION_DIR / "expected_items.csv").open(encoding="utf-8")))
    found = 0
    for item in expected:
        if item["entry_number"]:
            hit = any(a["source"] == f"Books {item['entry_number']}" and a["category"] == item["item_type"]
                      for a in actions)
            if item["item_type"] == "Amount difference":
                hit = bool(((bank_xl["MatchedEntry"] == item["entry_number"])
                            & (bank_xl["Status"] == "Amount difference")).any())
        else:
            hit = any(a["description"] == item["bank_label"] and abs(a["amount"] - float(item["amount"])) < 0.005
                      for a in actions)
        found += hit

    by_rule = bank_xl.groupby("MatchRule").size().to_dict()
    statuses = bank_xl.groupby("Status").size().to_dict()
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "company": "Lumen Supplies SAS (fictitious)",
        "period": "December 2025",
        "bank_lines": len(bank_xl),
        "ledger_lines": len(ledger_xl),
        "matched_by_reference": int(((bank_xl["MatchRule"] == "Reference") & (bank_xl["Status"] == "Matched")).sum()),
        "matched_by_amount": int(((bank_xl["MatchRule"] == "Amount and date") & (bank_xl["Status"] == "Matched")).sum()),
        "amount_differences": int(statuses.get("Amount difference", 0)),
        "not_in_books": int(statuses.get("Not in books", 0)),
        "matched_share": round(statuses.get("Matched", 0) / len(bank_xl), 4),
        "items_to_explain": len(actions),
        "statement": statement,
        "actions": actions,
        "rules_used": by_rule,
        "expected_items": len(expected),
        "expected_items_found": found,
        "independent_check_agrees": bool(independent_check(bank_xl, ledger_xl)),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2, ensure_ascii=False, default=str)
    (RESULTS_DIR / "summary.json").write_text(payload, encoding="utf-8")
    (RESULTS_DIR / "summary.js").write_text(
        "// Generated by src/build_workbook.py - do not edit by hand.\n"
        f"window.RECON_SUMMARY = {payload};\n", encoding="utf-8")
    return summary


def optimise_images():
    """Reduce the screenshots to 256 colours: same look, a third of the size."""
    from PIL import Image
    for path in IMAGES_DIR.glob("*.png"):
        image = Image.open(path).convert("RGB")
        image.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pythoncom.CoInitialize()
    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        if WORKBOOK_PATH.exists():
            WORKBOOK_PATH.unlink()
        wb = build(excel)

        # Prove the tool is reusable: refresh the queries again and recalculate.
        wb.RefreshAll()
        excel.CalculateUntilAsyncQueriesDone()
        excel.CalculateFull()
        summary = verify(excel, wb)

        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        excel.Visible = True  # picture export needs a drawn window
        excel.WindowState = -4140  # minimised
        export_range(excel, wb.Worksheets("Reconciliation"), "B2:D23", IMAGES_DIR / "reconciliation.png")
        last_action_row = 4 + summary["items_to_explain"]
        export_range(excel, wb.Worksheets("Actions"), f"A1:G{last_action_row}", IMAGES_DIR / "actions.png")
        export_range(excel, wb.Worksheets("Bank"), "A1:L16", IMAGES_DIR / "bank_table.png")
        export_range(excel, wb.Worksheets("Summary"), "B2:L25", IMAGES_DIR / "summary.png")
        wb.Worksheets("Start").Activate()
        wb.Save()
        wb.Close(False)
        optimise_images()

        print(f"Workbook saved: {WORKBOOK_PATH.name}")
        print(f"Bank lines {summary['bank_lines']} | by reference {summary['matched_by_reference']} | "
              f"by amount {summary['matched_by_amount']} | differences {summary['amount_differences']} | "
              f"not in books {summary['not_in_books']}")
        s = summary["statement"]
        print(f"Adjusted bank {s['adjusted_bank']:,.2f} | adjusted books {s['adjusted_book']:,.2f} | "
              f"difference {s['difference']} -> {s['result']}")
        print(f"Checks: {s['checks']}")
        print(f"Items to explain: {summary['items_to_explain']} | expected items found "
              f"{summary['expected_items_found']}/{summary['expected_items']} | "
              f"pandas cross-check agrees: {summary['independent_check_agrees']}")
    finally:
        excel.DisplayAlerts = False
        excel.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
