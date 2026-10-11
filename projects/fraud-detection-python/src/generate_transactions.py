"""Simulate six months of card payments for a fictitious payment provider (Kestrel Pay).

Normal behaviour is simulated customer by customer (spending level, active hours,
usual devices, occasional trips abroad), then three fraud patterns are injected:

  * account takeover: a burst of large payments from a new device, often abroad and at night;
  * card testing: a few tiny online payments within minutes, then large ones;
  * "quiet" fraud: single payments that look like the customer's usual spending
    (no model should catch all of these; they keep the results honest).

Output: data/transactions.csv.gz (one row per payment, with the is_fraud label).
Seeded: every run produces exactly the same file.

Usage:
    python src/generate_transactions.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 7
START = pd.Timestamp("2025-01-01")
DAYS = 181  # January to June 2025
N_CUSTOMERS = 3_000

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# category: (share of normal spending, amount factor, online share)
CATEGORIES = {
    "grocery": (0.30, 0.8, 0.05),
    "restaurants": (0.16, 0.7, 0.02),
    "transport": (0.12, 0.5, 0.40),
    "online_retail": (0.16, 1.3, 1.00),
    "electronics": (0.05, 3.5, 0.60),
    "travel": (0.05, 4.0, 0.80),
    "health": (0.08, 0.9, 0.10),
    "gift_cards": (0.02, 1.5, 0.90),
    "entertainment": (0.06, 0.8, 0.70),
}
FOREIGN_COUNTRIES = ["ES", "IT", "PT", "NL", "GB", "US", "MA", "RO", "NG", "BR"]


def simulate_customers(rng):
    home = rng.choice(["FR", "BE", "DE", "ES"], size=N_CUSTOMERS, p=[0.88, 0.06, 0.03, 0.03])
    return pd.DataFrame({
        "customer_id": [f"CU{i:05d}" for i in range(N_CUSTOMERS)],
        "home_country": home,
        "median_amount": np.round(rng.lognormal(np.log(32), 0.5, N_CUSTOMERS), 2),
        "daily_rate": rng.gamma(2.0, 0.22, N_CUSTOMERS).clip(0.05, 2.5),
        # About 7% of customers live at night (shift workers): their peak is around midnight.
        "peak_hour": np.where(rng.random(N_CUSTOMERS) < 0.07, rng.normal(0.5, 1.5, N_CUSTOMERS),
                              rng.normal(14, 2.5, N_CUSTOMERS).clip(9, 20)),
        "n_devices": rng.choice([1, 2, 3], size=N_CUSTOMERS, p=[0.55, 0.38, 0.07]),
        "tenure_days": rng.integers(30, 3_000, N_CUSTOMERS),
    })


def normal_transactions(rng, customers):
    names = list(CATEGORIES)
    shares = np.array([CATEGORIES[c][0] for c in names])
    rows = []
    for c in customers.itertuples():
        count = rng.poisson(c.daily_rate * DAYS)
        if count == 0:
            continue
        day = rng.integers(0, DAYS, count)
        hour = np.mod(rng.normal(c.peak_hour, 3.2, count), 24)
        seconds = (day * 86_400 + hour * 3_600 + rng.integers(0, 60, count)).astype(int)
        category = rng.choice(names, size=count, p=shares)
        factor = np.array([CATEGORIES[x][1] for x in category])
        amount = np.round(np.exp(np.log(c.median_amount * factor) + rng.normal(0, 0.7, count)), 2).clip(0.8, 6_000)
        # Transport tickets and parking: many tiny payments, sometimes several in a row.
        tiny = (category == "transport") & (rng.random(count) < 0.45)
        amount[tiny] = np.round(rng.uniform(1.2, 4.5, tiny.sum()), 2)
        online = rng.random(count) < np.array([CATEGORIES[x][2] for x in category])
        device = np.where(rng.random(count) < 0.985, rng.integers(0, c.n_devices, count), c.n_devices + rng.integers(0, 3, count))
        country = np.full(count, c.home_country, dtype=object)
        # Cross-border e-commerce: online payments to foreign merchants are normal.
        foreign_shop = online & (rng.random(count) < 0.07)
        country[foreign_shop] = rng.choice(["US", "GB", "NL", "IE", "CN", "LU"], size=foreign_shop.sum())
        # Shopping trips: a few bursts of several payments within an hour.
        for _ in range(rng.poisson(1.2)):
            members = rng.choice(count, size=min(count, int(rng.integers(3, 7))), replace=False)
            base = seconds[members[0]]
            seconds[members] = base + np.sort(rng.integers(0, 3_000, len(members)))
        # Occasional trip abroad: a few consecutive days of foreign payments, usual device.
        if rng.random() < 0.08:
            trip_start = rng.integers(0, DAYS - 7)
            trip_country = rng.choice(FOREIGN_COUNTRIES[:6])
            on_trip = (day >= trip_start) & (day < trip_start + rng.integers(3, 8))
            country[on_trip] = trip_country
        rows.append(pd.DataFrame({
            "customer_id": c.customer_id, "seconds": seconds, "amount": amount, "merchant_category": category,
            "channel": np.where(online, "online", "card_present"), "device_id": [f"{c.customer_id}-D{d}" for d in device],
            "country": country, "is_fraud": 0, "fraud_type": "",
        }))
    return pd.concat(rows, ignore_index=True)


def fraud_transactions(rng, customers, n_events):
    rows = []
    victims = customers.sample(n=n_events, random_state=SEED, replace=False)
    kinds = rng.choice(["account_takeover", "card_testing", "quiet"], size=n_events, p=[0.40, 0.28, 0.32])
    for victim, kind in zip(victims.itertuples(), kinds):
        start = int(rng.integers(0, DAYS * 86_400 - 6 * 3_600))
        device = f"{victim.customer_id}-X{rng.integers(100, 999)}"
        abroad = rng.random() < 0.35
        country = rng.choice(FOREIGN_COUNTRIES) if abroad else victim.home_country
        if kind == "account_takeover":
            if rng.random() < 0.3:  # some takeovers happen at night
                start = (start // 86_400) * 86_400 + int(rng.integers(0, 5 * 3_600))
            if rng.random() < 0.3:  # malware on the customer's own phone: usual device
                device = f"{victim.customer_id}-D0"
            n = int(rng.integers(1, 6))
            seconds = start + np.sort(rng.integers(0, 6 * 3_600, n))
            amounts = np.round(rng.lognormal(np.log(220), 0.75, n), 2).clip(20, 4_000)
            categories = rng.choice(["electronics", "gift_cards", "online_retail", "travel", "entertainment"], size=n)
            channel = rng.choice(["online", "card_present"], size=n, p=[0.85, 0.15])
        elif kind == "card_testing":
            tests, hits = int(rng.integers(2, 6)), int(rng.integers(1, 3))
            seconds = start + np.concatenate([np.sort(rng.integers(0, 1_800, tests)),
                                              1_800 + np.sort(rng.integers(0, 3_600, hits))])
            amounts = np.round(np.concatenate([rng.uniform(0.5, 5, tests), rng.lognormal(np.log(300), 0.5, hits)]), 2)
            categories = np.array(["online_retail"] * tests + list(rng.choice(["electronics", "gift_cards"], size=hits)))
            channel = np.array(["online"] * (tests + hits))
            n = tests + hits
        else:  # quiet fraud: one payment close to the customer's habits
            n = 1
            seconds = np.array([start])
            amounts = np.round(np.array([victim.median_amount * rng.uniform(1.5, 4.0)]), 2)
            categories = np.array([rng.choice(["online_retail", "entertainment", "restaurants"])])
            channel = np.array(["online"])
            device = f"{victim.customer_id}-D0"
            country = victim.home_country
        rows.append(pd.DataFrame({
            "customer_id": victim.customer_id, "seconds": seconds.astype(int), "amount": amounts,
            "merchant_category": categories, "channel": channel, "device_id": device, "country": country,
            "is_fraud": 1, "fraud_type": kind,
        }))
    return pd.concat(rows, ignore_index=True)


def main():
    rng = np.random.default_rng(SEED)
    customers = simulate_customers(rng)
    normal = normal_transactions(rng, customers)
    fraud = fraud_transactions(rng, customers, n_events=320)
    data = pd.concat([normal, fraud], ignore_index=True)
    data = data.merge(customers[["customer_id", "home_country", "tenure_days"]], on="customer_id")
    data["timestamp"] = START + pd.to_timedelta(data["seconds"], unit="s")
    data = data.sort_values(["timestamp", "customer_id"]).reset_index(drop=True)
    data.insert(0, "transaction_id", [f"T{i:07d}" for i in range(len(data))])
    columns = ["transaction_id", "timestamp", "customer_id", "amount", "merchant_category", "channel",
               "device_id", "country", "home_country", "tenure_days", "is_fraud", "fraud_type"]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data[columns].to_csv(DATA_DIR / "transactions.csv.gz", index=False, compression="gzip")
    fraud_rate = data["is_fraud"].mean()
    print(f"{len(data):,} transactions, {data['customer_id'].nunique():,} customers, "
          f"{int(data['is_fraud'].sum())} fraudulent ({fraud_rate:.2%}), "
          f"fraud amount {data.loc[data.is_fraud == 1, 'amount'].sum():,.0f} EUR")
    print(data.groupby("fraud_type")["amount"].agg(["count", "sum"]).round(0))


if __name__ == "__main__":
    main()
