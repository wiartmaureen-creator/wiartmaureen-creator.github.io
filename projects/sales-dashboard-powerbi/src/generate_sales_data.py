"""Generate the sales and budget data of Calyx Home & Garden (fictitious retailer).

Star schema, ready for Power BI:
  dim_store.csv      12 stores in 5 French regions + the online shop
  dim_category.csv   6 product categories
  dim_date.csv       every day of 2024 and 2025 (French calendar labels in English)
  fact_sales.csv     one row per day x store x category (units, gross sales,
                     discounts, returns, net sales, cost of sales)
  fact_budget.csv    2025 monthly budget per store x category (net sales and margin)

Business events are built into the data so the dashboard has decisions to support:
  * summer 2025 barbecue promotion: deeper discounts, more volume, less margin;
  * a competitor opens near the Metz store in April 2025;
  * the online shop grows fast, but garden furniture bought online comes back often;
  * outdoor lighting is a growing category.

Seeded: every run produces exactly the same files.

Usage:
    python src/generate_sales_data.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import random
from pathlib import Path

SEED = 2024
START = dt.date(2024, 1, 1)
END = dt.date(2025, 12, 31)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# store_id, store_name, region, channel, opened, surface_m2, 2024 net sales target (EUR)
STORES = [
    ("S01", "Lille", "Hauts-de-France", "Store", 2011, 5200, 6_200_000),
    ("S02", "Arras", "Hauts-de-France", "Store", 2016, 3100, 3_100_000),
    ("S03", "Amiens", "Hauts-de-France", "Store", 2014, 3400, 3_400_000),
    ("S04", "Montreuil", "Ile-de-France", "Store", 2012, 4600, 5_600_000),
    ("S05", "Versailles", "Ile-de-France", "Store", 2018, 4300, 5_100_000),
    ("S06", "Metz", "Grand Est", "Store", 2015, 3500, 3_600_000),
    ("S07", "Reims", "Grand Est", "Store", 2017, 3200, 3_200_000),
    ("S08", "Rouen", "Normandie", "Store", 2013, 3900, 4_000_000),
    ("S09", "Caen", "Normandie", "Store", 2019, 3300, 3_300_000),
    ("S10", "Lyon", "Auvergne-Rhone-Alpes", "Store", 2010, 5000, 6_000_000),
    ("S11", "Grenoble", "Auvergne-Rhone-Alpes", "Store", 2020, 3600, 3_700_000),
    ("S12", "Online shop", "National", "Online", 2019, 0, 4_800_000),
]

# category_id, name, share of sales, margin on net sales, average unit price, monthly seasonality
CATEGORIES = [
    ("C1", "Garden furniture", 0.22, 0.38, 145.0, [0.3, 0.4, 0.9, 1.5, 1.9, 1.9, 1.5, 1.0, 0.6, 0.4, 0.3, 0.5]),
    ("C2", "Plants & seeds", 0.24, 0.52, 9.5, [0.4, 0.6, 1.5, 2.0, 1.9, 1.3, 0.9, 0.7, 1.0, 1.0, 0.6, 0.9]),
    ("C3", "Garden tools", 0.14, 0.40, 24.0, [0.5, 0.7, 1.3, 1.6, 1.5, 1.2, 1.0, 0.8, 0.9, 0.9, 0.6, 0.8]),
    ("C4", "Barbecues & outdoor cooking", 0.12, 0.34, 210.0, [0.2, 0.3, 0.6, 1.2, 1.9, 2.2, 2.0, 1.3, 0.5, 0.3, 0.2, 0.4]),
    ("C5", "Home decor", 0.18, 0.55, 18.0, [0.9, 0.8, 0.9, 0.9, 0.9, 0.8, 0.8, 0.8, 1.0, 1.1, 1.4, 2.0]),
    ("C6", "Outdoor lighting", 0.10, 0.45, 32.0, [0.6, 0.6, 0.8, 1.0, 1.1, 1.1, 1.0, 0.9, 1.0, 1.2, 1.4, 1.7]),
]

# Margin differences between sites (local pricing, shrinkage; online carries delivery costs).
STORE_MARGIN_OFFSET = {"S01": 0.008, "S02": -0.006, "S03": -0.003, "S04": 0.012, "S05": 0.015, "S06": -0.010,
                       "S07": -0.004, "S08": 0.002, "S09": -0.008, "S10": 0.009, "S11": -0.002, "S12": -0.025}

CLOSED_DAYS = {(1, 1), (5, 1), (12, 25)}  # stores closed; the online shop never closes
STORE_WEEKDAY = [0.75, 0.80, 0.95, 0.85, 1.00, 1.75, 0.90]
ONLINE_WEEKDAY = [1.05, 1.00, 1.00, 1.00, 0.95, 0.90, 1.10]

BASE_DISCOUNT = {"Store": 0.07, "Online": 0.09}
CLEARANCE_DISCOUNT = 0.12        # January and second half of August
BBQ_PROMO_DISCOUNT = 0.22        # summer 2025 barbecue campaign
BBQ_PROMO_UPLIFT = 1.18          # extra volume it generated
RETURN_RATE = {"Store": 0.012, "Online": 0.04}
ONLINE_FURNITURE_RETURN_RATE = 0.09

GROWTH_2025 = {"Store": 1.02, "Online": 1.38}
LIGHTING_GROWTH_2025 = 1.25
METZ_COMPETITOR_FROM = dt.date(2025, 4, 1)
METZ_COMPETITOR_EFFECT = 0.76

BUDGET_GROWTH = {"Store": 1.03, "Online": 1.25}
BUDGET_LIGHTING_GROWTH = 1.10

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def days():
    day = START
    while day <= END:
        yield day
        day += dt.timedelta(days=1)


def is_bbq_promo(day: dt.date, category_id: str) -> bool:
    return category_id == "C4" and day.year == 2025 and 5 <= day.month <= 8


def discount_rate(day: dt.date, channel: str, category_id: str) -> float:
    if is_bbq_promo(day, category_id):
        return BBQ_PROMO_DISCOUNT
    if day.month == 1 or (day.month == 8 and day.day >= 15):
        return CLEARANCE_DISCOUNT
    return BASE_DISCOUNT[channel]


def day_weights(store, category):
    """Normalise seasonality x weekday so that 2024 lands on the store's sales target."""
    _, _, _, channel, *_ = store
    seasonality = category[5]
    weekday = ONLINE_WEEKDAY if channel == "Online" else STORE_WEEKDAY
    weights = {}
    for day in days():
        if day.year != 2024:
            continue
        if channel == "Store" and (day.month, day.day) in CLOSED_DAYS:
            continue
        weights[day] = seasonality[day.month - 1] * weekday[day.weekday()]
    return sum(weights.values())


def main():
    rng = random.Random(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fact_rows = []
    monthly_2024 = {}  # (store_id, category_id, month) -> (net sales, margin)
    for store in STORES:
        store_id, name, region, channel, opened, surface, target_2024 = store
        weekday = ONLINE_WEEKDAY if channel == "Online" else STORE_WEEKDAY
        for category in CATEGORIES:
            category_id, _, share, margin, unit_price, seasonality = category
            scale = target_2024 * share / day_weights(store, category)
            for day in days():
                if channel == "Store" and (day.month, day.day) in CLOSED_DAYS:
                    continue
                net_before_discount = scale * seasonality[day.month - 1] * weekday[day.weekday()]
                if day.year == 2025:
                    net_before_discount *= GROWTH_2025[channel]
                    if category_id == "C6":
                        net_before_discount *= LIGHTING_GROWTH_2025
                    if store_id == "S06" and day >= METZ_COMPETITOR_FROM:
                        net_before_discount *= METZ_COMPETITOR_EFFECT
                    if is_bbq_promo(day, category_id):
                        net_before_discount *= BBQ_PROMO_UPLIFT
                net_before_discount *= rng.lognormvariate(0, 0.18)

                rate = discount_rate(day, channel, category_id)
                gross = net_before_discount / (1 - BASE_DISCOUNT[channel])  # list price value
                discount = gross * rate
                return_rate = (ONLINE_FURNITURE_RETURN_RATE if channel == "Online" and category_id == "C1"
                               else RETURN_RATE[channel])
                returns = (gross - discount) * return_rate
                net = gross - discount - returns
                # Cost follows the goods kept; deeper discounts eat straight into margin.
                cost = (gross - returns) * (1 - BASE_DISCOUNT[channel]) * (1 - margin - STORE_MARGIN_OFFSET[store_id])
                units = max(0, round(gross / (unit_price / (1 - BASE_DISCOUNT[channel]))))
                fact_rows.append([day.isoformat(), store_id, category_id, units,
                                  round(gross, 2), round(discount, 2), round(returns, 2),
                                  round(net, 2), round(cost, 2)])
                if day.year == 2024:
                    key = (store_id, category_id, day.month)
                    net_sum, margin_sum = monthly_2024.get(key, (0.0, 0.0))
                    monthly_2024[key] = (net_sum + net, margin_sum + net - cost)

    # 2025 budget: last year's actuals plus the growth management planned.
    budget_rows = []
    for (store_id, category_id, month), (net_2024, margin_2024) in sorted(monthly_2024.items()):
        channel = next(s[3] for s in STORES if s[0] == store_id)
        growth = BUDGET_GROWTH[channel] * (BUDGET_LIGHTING_GROWTH if category_id == "C6" else 1.0)
        budget_net = round(net_2024 * growth, -2)
        budget_margin = round(budget_net * (margin_2024 / net_2024), -2)
        budget_rows.append([dt.date(2025, month, 1).isoformat(), store_id, category_id,
                            f"{budget_net:.2f}", f"{budget_margin:.2f}"])

    write(DATA_DIR / "fact_sales.csv",
          ["date", "store_id", "category_id", "units", "gross_sales", "discount", "returns",
           "net_sales", "cost_of_sales"], fact_rows)
    write(DATA_DIR / "fact_budget.csv",
          ["month_start", "store_id", "category_id", "budget_net_sales", "budget_gross_margin"], budget_rows)
    write(DATA_DIR / "dim_store.csv",
          ["store_id", "store_name", "region", "channel", "opened", "surface_m2"],
          [s[:6] for s in STORES])
    write(DATA_DIR / "dim_category.csv", ["category_id", "category"], [c[:2] for c in CATEGORIES])
    date_rows = []
    for day in days():
        date_rows.append([day.isoformat(), day.year, f"Q{(day.month - 1) // 3 + 1}", day.month,
                          MONTHS[day.month - 1], f"{day.year}-{day.month:02d}",
                          day.strftime("%a"), 1 if day.weekday() >= 5 else 0])
    write(DATA_DIR / "dim_date.csv",
          ["date", "year", "quarter", "month_number", "month", "year_month", "weekday", "is_weekend"], date_rows)

    total_2024 = sum(r[7] for r in fact_rows if r[0].startswith("2024"))
    total_2025 = sum(r[7] for r in fact_rows if r[0].startswith("2025"))
    print(f"fact_sales: {len(fact_rows):,} rows | fact_budget: {len(budget_rows):,} rows")
    print(f"Net sales 2024: {total_2024:,.0f} | 2025: {total_2025:,.0f} ({total_2025 / total_2024 - 1:+.1%})")


def write(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


if __name__ == "__main__":
    main()
