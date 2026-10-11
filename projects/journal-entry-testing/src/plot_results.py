"""Draw the journal entry testing results (optional; needs matplotlib).

Reads the CSV files written by run_analysis.py and saves:
  images/hits_per_test.png  entries flagged by each SQL test, planted cases vs other hits
  images/benford.png        first-digit distribution against Benford's law

Usage:
    python src/plot_results.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"
IMAGES_DIR = PROJECT_DIR / "images"
BLUE, ORANGE = "#2F6BD0", "#E8650A"


def main():
    summary = json.loads((RESULTS_DIR / "summary.json").read_text(encoding="utf-8"))
    IMAGES_DIR.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#cfc7bf", "axes.axisbelow": True})

    tests = summary["tests"][::-1]
    labels = [f"{t['id']} · {t['title']}" for t in tests]
    planted = [t["planted_hits"] for t in tests]
    other = [t["other_hits"] for t in tests]
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=150)
    ax.barh(labels, planted, color=BLUE, height=0.55, label="Planted cases")
    ax.barh(labels, other, left=planted, color=ORANGE, height=0.55, label="Other hits to review")
    for y, (p, o) in enumerate(zip(planted, other)):
        ax.text(p + o + 0.1, y, str(p + o), va="center", fontsize=9)
    ax.set_xlabel("Entries flagged")
    ax.set_title("What each SQL test found", loc="left", fontweight="bold")
    ax.grid(axis="x", color="#e7e1db")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "hits_per_test.png")
    plt.close(fig)

    with (RESULTS_DIR / "benford_first_digit.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    digits = [int(r["digit"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=150)
    ax.bar(digits, [float(r["observed_share"]) * 100 for r in rows], color=BLUE, width=0.5, label="Observed")
    ax.plot(digits, [float(r["expected_share"]) * 100 for r in rows], color=ORANGE, marker="o", linewidth=2,
            label="Expected (Benford)")
    ax.set_xticks(digits)
    ax.set_xlabel("First digit of the amount")
    ax.set_ylabel("Share of amounts (%)")
    ax.set_title(f"Benford's law · MAD {summary['benford']['mad']} ({summary['benford']['conformity'].lower()})",
                 loc="left", fontweight="bold")
    ax.grid(axis="y", color="#e7e1db")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "benford.png")
    plt.close(fig)
    print("Saved images/hits_per_test.png and images/benford.png")


if __name__ == "__main__":
    main()
