"""Run the journal entry tests on the synthetic general ledger.

Steps
  1. Load the CSV extracts into a fresh SQLite database (output/ledger.db).
  2. Run every SQL test in sql/tests/ and export each result to results/.
  3. Score each flagged entry by the tests it triggers (sql/risk_scoring.sql).
  4. Run the Benford first-digit analysis and measure conformity (MAD).
  5. Check the hits against the planted anomalies (validation/).
  6. Write results/summary.json, plus results/summary.js for the web page.

Usage:
    python src/run_analysis.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
SQL_DIR = PROJECT_DIR / "sql"
TESTS_DIR = SQL_DIR / "tests"
RESULTS_DIR = PROJECT_DIR / "results"
OUTPUT_DIR = PROJECT_DIR / "output"
VALIDATION_FILE = PROJECT_DIR / "validation" / "planted_anomalies.csv"

# table name -> (CSV file, columns stored as numbers)
SOURCE_TABLES = {
    "accounts": ("chart_of_accounts.csv", set()),
    "journals": ("journals.csv", {"is_manual"}),
    "users": ("users.csv", {"is_system", "posting_allowed"}),
    "public_holidays": ("public_holidays.csv", set()),
    "journal_lines": ("general_ledger.csv", {"line_no", "debit", "credit"}),
}

# Nigrini's first-digit MAD thresholds.
BENFORD_CONFORMITY = [
    (0.006, "Close conformity"),
    (0.012, "Acceptable conformity"),
    (0.015, "Marginally acceptable conformity"),
    (float("inf"), "Nonconformity"),
]

TOP_RISK_ROWS = 12


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def to_value(column: str, text: str, numeric_columns: set):
    if text == "":
        return None
    if column in numeric_columns:
        return float(text) if "." in text else int(text)
    return text


def build_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript((SQL_DIR / "00_schema.sql").read_text(encoding="utf-8"))
    for table, (file_name, numeric_columns) in SOURCE_TABLES.items():
        rows = read_csv(DATA_DIR / file_name)
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            ([to_value(c, row[c], numeric_columns) for c in columns] for row in rows),
        )
    conn.executescript((SQL_DIR / "01_audit_parameters.sql").read_text(encoding="utf-8"))
    conn.commit()
    return conn


def run_query(conn: sqlite3.Connection, sql: str):
    cursor = conn.execute(sql)
    columns = [description[0] for description in cursor.description]
    return columns, cursor.fetchall()


def write_result(path: Path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def expand_gaps(columns, rows) -> list[str]:
    """Turn T02 gap ranges into the list of missing entry numbers."""
    index = {name: i for i, name in enumerate(columns)}
    missing = []
    for row in rows:
        first = row[index["first_missing_number"]]
        prefix, first_seq = first.split("-")
        for offset in range(row[index["missing_count"]]):
            missing.append(f"{prefix}-{int(first_seq) + offset:05d}")
    return missing


def run_tests(conn: sqlite3.Connection):
    """Run each test, export it and record which entries it flags."""
    results = {}
    for sql_file in sorted(TESTS_DIR.glob("T*.sql")):
        test_id = sql_file.stem.split("_")[0]
        columns, rows = run_query(conn, sql_file.read_text(encoding="utf-8"))
        write_result(RESULTS_DIR / f"{sql_file.stem}.csv", columns, rows)
        if "entry_number" in columns:
            position = columns.index("entry_number")
            flagged = sorted({row[position] for row in rows})
            conn.executemany("INSERT INTO test_hits (test_id, entry_number) VALUES (?, ?)",
                             [(test_id, number) for number in flagged])
        else:
            flagged = expand_gaps(columns, rows)
        results[test_id] = {"file": sql_file.name, "columns": columns,
                            "rows": rows, "flagged": flagged}
    conn.commit()
    return results


def benford_analysis(conn: sqlite3.Connection):
    columns, rows = run_query(conn, (SQL_DIR / "benford_first_digit.sql").read_text(encoding="utf-8"))
    write_result(RESULTS_DIR / "benford_first_digit.csv", columns, rows)
    digits = [dict(zip(columns, row)) for row in rows]
    mad = sum(abs(d["difference"]) for d in digits) / len(digits)
    conformity = next(label for limit, label in BENFORD_CONFORMITY if mad <= limit)
    return {
        "population": sum(d["observed_count"] for d in digits),
        "mad": round(mad, 4),
        "conformity": conformity,
        "digits": [{"digit": d["digit"], "observed": d["observed_share"],
                    "expected": d["expected_share"], "count": d["observed_count"]}
                   for d in digits],
    }


def check_detection(test_results):
    """Compare what each test flagged with the planted answer key."""
    planted = read_csv(VALIDATION_FILE)
    details = []
    for case in planted:
        expected = case["expected_tests"].split(";")
        triggered = sorted(test_id for test_id, result in test_results.items()
                           if case["entry_number"] in result["flagged"])
        details.append({
            "case_id": case["case_id"],
            "entry_number": case["entry_number"],
            "scenario": case["scenario"],
            "story": case["story"],
            "expected_tests": expected,
            "triggered_tests": triggered,
            "detected": all(test_id in triggered for test_id in expected),
        })
    write_result(RESULTS_DIR / "detection_check.csv",
                 ["case_id", "entry_number", "scenario", "expected_tests",
                  "triggered_tests", "detected"],
                 [[d["case_id"], d["entry_number"], d["scenario"], ";".join(d["expected_tests"]),
                   ";".join(d["triggered_tests"]), "Yes" if d["detected"] else "No"]
                  for d in details])
    return details


def dataset_profile(conn: sqlite3.Connection):
    _, rows = run_query(conn, """
        SELECT COUNT(*), COUNT(DISTINCT entry_number), ROUND(SUM(debit), 2),
               MIN(entry_date), MAX(entry_date), COUNT(DISTINCT account_number),
               COUNT(DISTINCT created_by)
        FROM journal_lines
    """)
    lines, entries, total_debit, first_date, last_date, accounts, users = rows[0]
    _, by_journal = run_query(conn, """
        SELECT journal_code, COUNT(DISTINCT entry_number) FROM journal_lines
        GROUP BY journal_code ORDER BY 2 DESC
    """)
    return {
        "lines": lines, "entries": entries, "total_debit": total_debit,
        "first_date": first_date, "last_date": last_date,
        "accounts": accounts, "users": users,
        "entries_by_journal": dict(by_journal),
    }


def main():
    conn = build_database(OUTPUT_DIR / "ledger.db")
    test_results = run_tests(conn)

    columns, risk_rows = run_query(conn, (SQL_DIR / "risk_scoring.sql").read_text(encoding="utf-8"))
    write_result(RESULTS_DIR / "risk_ranking.csv", columns, risk_rows)

    benford = benford_analysis(conn)
    detection = check_detection(test_results)
    profile = dataset_profile(conn)

    planted_entries = {d["entry_number"] for d in detection}
    _, catalog = run_query(conn, "SELECT test_id, title, weight, rationale FROM test_catalog ORDER BY test_id")
    tests = []
    for test_id, title, weight, rationale in catalog:
        flagged = test_results[test_id]["flagged"]
        planted_hits = sum(1 for number in flagged if number in planted_entries)
        tests.append({
            "id": test_id, "title": title, "weight": weight, "rationale": rationale,
            "file": test_results[test_id]["file"], "hits": len(flagged),
            "planted_hits": planted_hits, "other_hits": len(flagged) - planted_hits,
        })

    flagged_entries = len(risk_rows)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "company": "Lumen Supplies SAS (fictitious)",
        "fiscal_year": 2025,
        "dataset": profile,
        "tests": tests,
        "flagged_entries": flagged_entries,
        "flagged_share": round(flagged_entries / profile["entries"], 4),
        "detection": {
            "planted_cases": len(detection),
            "detected": sum(1 for d in detection if d["detected"]),
            "details": detection,
        },
        "benford": benford,
        "top_risk": [dict(zip(columns, row)) for row in risk_rows[:TOP_RISK_ROWS]],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2, ensure_ascii=False)
    (RESULTS_DIR / "summary.json").write_text(payload, encoding="utf-8")
    (RESULTS_DIR / "summary.js").write_text(
        "// Generated by src/run_analysis.py - do not edit by hand.\n"
        f"window.JET_SUMMARY = {payload};\n", encoding="utf-8")

    print(f"Ledger: {profile['entries']:,} entries / {profile['lines']:,} lines")
    print(f"{'Test':<5} {'Title':<38} {'Hits':>5} {'Planted':>8} {'Other':>6}")
    for test in tests:
        print(f"{test['id']:<5} {test['title']:<38} {test['hits']:>5} "
              f"{test['planted_hits']:>8} {test['other_hits']:>6}")
    print(f"Entries flagged by at least one test: {flagged_entries} "
          f"({summary['flagged_share']:.1%} of entries)")
    print(f"Planted cases detected: {summary['detection']['detected']}"
          f"/{summary['detection']['planted_cases']}")
    for d in detection:
        if not d["detected"]:
            print(f"  MISSED {d['case_id']} {d['entry_number']}: expected {d['expected_tests']},"
                  f" got {d['triggered_tests']}")
    print(f"Benford MAD: {benford['mad']} -> {benford['conformity']}")


if __name__ == "__main__":
    main()
