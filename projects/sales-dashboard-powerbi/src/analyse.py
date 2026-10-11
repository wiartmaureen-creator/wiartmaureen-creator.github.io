"""Compute the figures behind the dashboard and the management memo.

Reads the star schema in data/, reproduces the dashboard measures with pandas
(so the Power BI numbers can be checked independently) and writes:
  results/summary.json      headline figures and the findings for the memo
  results/dashboard_data.js monthly cube used by the interactive web version

Usage:
    python src/analyse.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
RESULTS_DIR = PROJECT_DIR / "results"

NORMAL_DISCOUNT = {"Store": 0.07, "Online": 0.09}


def load():
    sales = pd.read_csv(DATA_DIR / "fact_sales.csv", parse_dates=["date"])
    budget = pd.read_csv(DATA_DIR / "fact_budget.csv", parse_dates=["month_start"])
    stores = pd.read_csv(DATA_DIR / "dim_store.csv")
    categories = pd.read_csv(DATA_DIR / "dim_category.csv")
    sales = sales.merge(stores, on="store_id").merge(categories, on="category_id")
    budget = budget.merge(stores, on="store_id").merge(categories, on="category_id")
    sales["year"] = sales["date"].dt.year
    sales["month"] = sales["date"].dt.month
    budget["month"] = budget["month_start"].dt.month
    return sales, budget, stores, categories


def measures(frame: pd.DataFrame) -> dict:
    """The dashboard's DAX measures, in pandas."""
    net = frame["net_sales"].sum()
    margin = net - frame["cost_of_sales"].sum()
    gross = frame["gross_sales"].sum()
    return {
        "net_sales": net,
        "gross_margin": margin,
        "gross_margin_pct": margin / net if net else 0.0,
        "discount_rate": frame["discount"].sum() / gross if gross else 0.0,
        "return_rate": frame["returns"].sum() / (gross - frame["discount"].sum()) if gross else 0.0,
        "units": int(frame["units"].sum()),
    }


def by(frame_2025, frame_2024, budget, key):
    rows = []
    for value in sorted(frame_2025[key].unique()):
        current = measures(frame_2025[frame_2025[key] == value])
        last = measures(frame_2024[frame_2024[key] == value])
        plan = budget[budget[key] == value]
        budget_net = plan["budget_net_sales"].sum()
        budget_margin = plan["budget_gross_margin"].sum()
        rows.append({
            key: value,
            "net_sales": round(current["net_sales"]),
            "net_sales_ly": round(last["net_sales"]),
            "yoy": round(current["net_sales"] / last["net_sales"] - 1, 4),
            "budget": round(budget_net),
            "vs_budget": round(current["net_sales"] / budget_net - 1, 4),
            "gross_margin": round(current["gross_margin"]),
            "gross_margin_budget": round(budget_margin),
            "gm_pct": round(current["gross_margin_pct"], 4),
            "gm_pct_ly": round(last["gross_margin_pct"], 4),
            "gm_pct_change_pts": round((current["gross_margin_pct"] - last["gross_margin_pct"]) * 100, 2),
            "discount_rate": round(current["discount_rate"], 4),
            "return_rate": round(current["return_rate"], 4),
            "units_yoy": round(current["units"] / last["units"] - 1, 4),
        })
    return rows


def main():
    sales, budget, stores, categories = load()
    s24 = sales[sales["year"] == 2024]
    s25 = sales[sales["year"] == 2025]

    total_25, total_24 = measures(s25), measures(s24)
    budget_net = budget["budget_net_sales"].sum()
    budget_margin = budget["budget_gross_margin"].sum()

    # Barbecue promotion: May-August 2025 against May-August 2024.
    bbq = lambda f: f[(f["category_id"] == "C4") & f["month"].between(5, 8)]
    bbq25, bbq24 = measures(bbq(s25)), measures(bbq(s24))
    bbq_rows = bbq(s25)
    normal_rate = bbq_rows["channel"].map(NORMAL_DISCOUNT)
    bbq_extra_discount = float((bbq_rows["discount"] - bbq_rows["gross_sales"] * normal_rate).sum())

    # Metz: April-December 2025 against the same months of 2024 and against budget.
    metz = lambda f: f[(f["store_id"] == "S06") & (f["month"] >= 4)]
    metz25, metz24 = measures(metz(s25)), measures(metz(s24))
    metz_budget = budget[(budget["store_id"] == "S06") & (budget["month"] >= 4)]["budget_net_sales"].sum()

    # Online garden furniture returns.
    online_furniture = s25[(s25["channel"] == "Online") & (s25["category_id"] == "C1")]
    store_furniture = s25[(s25["channel"] == "Store") & (s25["category_id"] == "C1")]
    online = measures(s25[s25["channel"] == "Online"])
    online_ly = measures(s24[s24["channel"] == "Online"])

    findings = {
        "bbq_promo": {
            "net_sales_change": round(bbq25["net_sales"] / bbq24["net_sales"] - 1, 4),
            "units_change": round(bbq25["units"] / bbq24["units"] - 1, 4),
            "gm_pct_2025": round(bbq25["gross_margin_pct"], 4),
            "gm_pct_2024": round(bbq24["gross_margin_pct"], 4),
            "gross_margin_change": round(bbq25["gross_margin"] - bbq24["gross_margin"]),
            "extra_discount_given": round(bbq_extra_discount),
        },
        "metz": {
            "yoy_apr_dec": round(metz25["net_sales"] / metz24["net_sales"] - 1, 4),
            "vs_budget_apr_dec": round(metz25["net_sales"] / metz_budget - 1, 4),
            "shortfall_vs_budget": round(metz25["net_sales"] - metz_budget),
        },
        "online": {
            "net_sales": round(online["net_sales"]),
            "yoy": round(online["net_sales"] / online_ly["net_sales"] - 1, 4),
            "share_of_sales": round(online["net_sales"] / total_25["net_sales"], 4),
            "furniture_return_rate": round(measures(online_furniture)["return_rate"], 4),
            "store_furniture_return_rate": round(measures(store_furniture)["return_rate"], 4),
            "furniture_returns_value": round(online_furniture["returns"].sum()),
        },
    }

    summary = {
        "company": "Calyx Home & Garden (fictitious)",
        "rows": {"fact_sales": len(sales), "fact_budget": len(budget)},
        "total": {
            "net_sales": round(total_25["net_sales"]),
            "net_sales_ly": round(total_24["net_sales"]),
            "yoy": round(total_25["net_sales"] / total_24["net_sales"] - 1, 4),
            "budget": round(budget_net),
            "vs_budget": round(total_25["net_sales"] / budget_net - 1, 4),
            "gross_margin": round(total_25["gross_margin"]),
            "gross_margin_budget": round(budget_margin),
            "gross_margin_vs_budget": round(total_25["gross_margin"] - budget_margin),
            "gm_pct": round(total_25["gross_margin_pct"], 4),
            "gm_pct_ly": round(total_24["gross_margin_pct"], 4),
            "discount_rate": round(total_25["discount_rate"], 4),
            "discount_rate_ly": round(total_24["discount_rate"], 4),
        },
        "by_category": by(s25, s24, budget, "category"),
        "by_store": by(s25, s24, budget, "store_name"),
        "by_region": by(s25, s24, budget, "region"),
        "findings": findings,
    }

    # Monthly cube for the web dashboard: [year, month, store, category, net, gross, discount, returns, cost, units]
    cube = (sales.groupby(["year", "month", "store_id", "category_id"], as_index=False)
            [["net_sales", "gross_sales", "discount", "returns", "cost_of_sales", "units"]].sum())
    budget_cube = budget.groupby(["month", "store_id", "category_id"], as_index=False)[
        ["budget_net_sales", "budget_gross_margin"]].sum()
    dashboard = {
        "stores": stores.to_dict(orient="records"),
        "categories": categories.to_dict(orient="records"),
        "fields": ["year", "month", "store_id", "category_id", "net", "gross", "discount", "returns", "cost", "units"],
        "rows": [[int(r.year), int(r.month), r.store_id, r.category_id, round(r.net_sales), round(r.gross_sales),
                  round(r.discount), round(r.returns), round(r.cost_of_sales), int(r.units)]
                 for r in cube.itertuples()],
        "budget_fields": ["month", "store_id", "category_id", "net", "margin"],
        "budget": [[int(r.month), r.store_id, r.category_id, round(r.budget_net_sales), round(r.budget_gross_margin)]
                   for r in budget_cube.itertuples()],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (RESULTS_DIR / "summary.js").write_text(
        "// Generated by src/analyse.py - do not edit by hand.\n"
        f"window.SALES_SUMMARY = {json.dumps(summary)};\n", encoding="utf-8")
    (RESULTS_DIR / "dashboard_data.js").write_text(
        "// Generated by src/analyse.py - do not edit by hand.\n"
        f"window.SALES_CUBE = {json.dumps(dashboard, separators=(',', ':'))};\n", encoding="utf-8")

    t = summary["total"]
    print(f"Net sales 2025 {t['net_sales']:,} ({t['yoy']:+.1%} vs LY, {t['vs_budget']:+.1%} vs budget)")
    print(f"Gross margin {t['gross_margin']:,} ({t['gm_pct']:.1%}, LY {t['gm_pct_ly']:.1%}); "
          f"vs budget {t['gross_margin_vs_budget']:+,}")
    print(f"Discount rate {t['discount_rate']:.1%} (LY {t['discount_rate_ly']:.1%})")
    print(json.dumps(findings, indent=1))
    print("Category:")
    for r in summary["by_category"]:
        print(f"  {r['category']:<28} {r['net_sales']:>11,} yoy {r['yoy']:+.1%} vs bud {r['vs_budget']:+.1%} "
              f"gm {r['gm_pct']:.1%} ({r['gm_pct_change_pts']:+.1f} pts) units {r['units_yoy']:+.1%}")
    print("Store:")
    for r in summary["by_store"]:
        print(f"  {r['store_name']:<12} {r['net_sales']:>11,} yoy {r['yoy']:+.1%} vs bud {r['vs_budget']:+.1%} "
              f"gm {r['gm_pct']:.1%}")


if __name__ == "__main__":
    main()
