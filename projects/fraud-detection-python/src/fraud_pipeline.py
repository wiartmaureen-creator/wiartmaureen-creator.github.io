"""Fraud detection pipeline: features, rules baseline, models, cost-based threshold.

Business question: which payments should the fraud team review, so that the
money lost to fraud plus the cost of reviewing alerts is as low as possible?

Steps
  1. Behavioural features computed per customer from PAST payments only
     (no information from the future leaks into a payment's features).
  2. Time-based split: train on January-March, tune the alert threshold on
     April, report on May-June, as a real deployment would.
  3. Compare the current rules with a logistic regression and gradient boosting.
  4. Choose the alert threshold that minimises: review cost + fraud missed.

Usage:
    python src/fraud_pipeline.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_DIR / "data" / "transactions.csv.gz"
RESULTS_DIR = PROJECT_DIR / "results"
IMAGES_DIR = PROJECT_DIR / "images"

REVIEW_COST = 8.0          # EUR per alert reviewed: about 12 minutes of an analyst at 40 EUR/hour
ALERTS_PER_ANALYST_DAY = 40
TRAIN_END = pd.Timestamp("2025-04-01")
VALIDATION_END = pd.Timestamp("2025-05-01")
SEED = 42

NUMERIC_FEATURES = [
    "log_amount", "amount_vs_usual", "hour", "is_night", "is_foreign", "is_online", "new_device",
    "new_country", "log_secs_since_prev", "count_1h", "count_24h", "amount_24h_vs_usual",
    "small_payments_10min", "log_tenure", "prev_count_capped",
]
CATEGORICAL_FEATURES = ["merchant_category"]
FEATURE_LABELS = {
    "log_amount": "Amount", "amount_vs_usual": "Amount vs customer's usual", "hour": "Hour of day",
    "is_night": "Night-time (0-6h)", "is_foreign": "Paid abroad", "is_online": "Online payment",
    "new_device": "New device", "new_country": "First payment in this country",
    "log_secs_since_prev": "Time since previous payment", "count_1h": "Payments in the last hour",
    "count_24h": "Payments in the last 24 hours", "amount_24h_vs_usual": "Spending last 24h vs usual",
    "small_payments_10min": "Tiny payments in the last 10 min", "log_tenure": "Customer tenure",
    "prev_count_capped": "Payment history length", "merchant_category": "Merchant category",
}

# Brand-neutral palette (validated categorical slots 1-3) for the static figures.
BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#898781"


# --- Features -------------------------------------------------------------------------

def rolling_past(frame: pd.DataFrame, column: str, window: str, how: str) -> pd.Series:
    """Per-customer rolling statistic over a time window, excluding the current payment."""
    rolled = (frame.set_index("timestamp").groupby("customer_id")[column]
              .rolling(window, closed="left").agg(how))
    return pd.Series(rolled.to_numpy(), index=frame.index).fillna(0)


def build_features(data: pd.DataFrame) -> pd.DataFrame:
    df = data.sort_values(["customer_id", "timestamp"]).reset_index(drop=True)
    by_customer = df.groupby("customer_id")
    df["hour"] = df["timestamp"].dt.hour
    df["is_night"] = (df["hour"] < 6).astype(int)
    df["is_foreign"] = (df["country"] != df["home_country"]).astype(int)
    df["is_online"] = (df["channel"] == "online").astype(int)
    df["log_amount"] = np.log1p(df["amount"])
    df["prev_count"] = by_customer.cumcount()
    df["prev_count_capped"] = df["prev_count"].clip(upper=50)
    previous = by_customer["timestamp"].shift()
    df["log_secs_since_prev"] = np.log1p((df["timestamp"] - previous).dt.total_seconds().fillna(1e7))
    df["new_device"] = ((df.groupby(["customer_id", "device_id"]).cumcount() == 0) & (df["prev_count"] > 0)).astype(int)
    df["new_country"] = ((df.groupby(["customer_id", "country"]).cumcount() == 0) & (df["is_foreign"] == 1)).astype(int)
    usual = by_customer["amount"].transform(lambda s: s.shift().rolling(20, min_periods=1).mean())
    usual = usual.fillna(df["amount"].median())
    df["amount_vs_usual"] = (df["amount"] / usual).clip(upper=50)
    df["count_1h"] = rolling_past(df, "amount", "1h", "count")
    df["count_24h"] = rolling_past(df, "amount", "24h", "count")
    df["amount_24h_vs_usual"] = (rolling_past(df, "amount", "24h", "sum") / usual).clip(upper=100)
    df["is_small"] = (df["amount"] < 5).astype(int)
    df["small_payments_10min"] = rolling_past(df, "is_small", "10min", "sum")
    df["log_tenure"] = np.log1p(df["tenure_days"])
    return df.sort_values("timestamp").reset_index(drop=True)


def rules_flag(df: pd.DataFrame) -> np.ndarray:
    """The rules in place today: large amount, online payment abroad, or a burst of payments."""
    return ((df["amount"] >= 1_000) | ((df["is_foreign"] == 1) & (df["is_online"] == 1))
            | (df["count_1h"] >= 5)).to_numpy()


# --- Models -----------------------------------------------------------------------------

def make_models():
    preprocess_linear = ColumnTransformer([
        ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ("category", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    preprocess_trees = ColumnTransformer([
        ("numeric", "passthrough", NUMERIC_FEATURES),
        ("category", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
    ])
    return {
        "Logistic regression": Pipeline([
            ("prepare", preprocess_linear),
            ("model", LogisticRegression(max_iter=2_000, class_weight="balanced", C=0.5)),
        ]),
        "Gradient boosting": Pipeline([
            ("prepare", preprocess_trees),
            ("model", HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                                     l2_regularization=1.0, class_weight="balanced",
                                                     random_state=SEED)),
        ]),
    }


def outcome(flags: np.ndarray, frame: pd.DataFrame, days: int) -> dict:
    """What a set of alerts means for the business over a period."""
    fraud = frame["is_fraud"].to_numpy() == 1
    amount = frame["amount"].to_numpy()
    caught_amount = amount[flags & fraud].sum()
    missed_amount = amount[~flags & fraud].sum()
    alerts = int(flags.sum())
    return {
        "alerts": alerts,
        "alerts_per_day": round(alerts / days, 1),
        "fraud_caught": int((flags & fraud).sum()),
        "fraud_total": int(fraud.sum()),
        "recall_count": round((flags & fraud).sum() / fraud.sum(), 4),
        "fraud_amount_caught": round(float(caught_amount), 2),
        "fraud_amount_missed": round(float(missed_amount), 2),
        "recall_amount": round(float(caught_amount / (caught_amount + missed_amount)), 4),
        "precision": round(float((flags & fraud).sum() / alerts), 4) if alerts else 0.0,
        "review_cost": round(alerts * REVIEW_COST, 2),
        "total_cost": round(alerts * REVIEW_COST + float(missed_amount), 2),
    }


def best_threshold(scores: np.ndarray, frame: pd.DataFrame):
    """Scan thresholds and keep the one with the lowest review cost + fraud missed."""
    grid = np.unique(np.concatenate([np.linspace(0.01, 0.99, 99), np.quantile(scores, np.linspace(0.9, 0.9999, 200))]))
    fraud = frame["is_fraud"].to_numpy() == 1
    amount = frame["amount"].to_numpy()
    curve = []
    for t in grid:
        flags = scores >= t
        cost = flags.sum() * REVIEW_COST + amount[~flags & fraud].sum()
        curve.append((float(t), float(cost)))
    best = min(curve, key=lambda item: item[1])
    return best[0], curve


# --- Main ----------------------------------------------------------------------------------

def main():
    data = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
    df = build_features(data)
    train = df[df["timestamp"] < TRAIN_END]
    validation = df[(df["timestamp"] >= TRAIN_END) & (df["timestamp"] < VALIDATION_END)]
    test = df[df["timestamp"] >= VALIDATION_END]
    test_days = (test["timestamp"].max().normalize() - test["timestamp"].min().normalize()).days + 1
    features = NUMERIC_FEATURES + CATEGORICAL_FEATURES

    results = {"rules": {"name": "Current rules", "test": outcome(rules_flag(test), test, test_days)}}
    scores_test, curves = {}, {}
    for name, model in make_models().items():
        model.fit(train[features], train["is_fraud"])
        threshold, cost_curve = best_threshold(model.predict_proba(validation[features])[:, 1], validation)
        scores = model.predict_proba(test[features])[:, 1]
        scores_test[name] = scores
        curves[name] = cost_curve
        results[name] = {
            "name": name,
            "threshold": round(threshold, 4),
            "average_precision": round(float(average_precision_score(test["is_fraud"], scores)), 4),
            "test": outcome(scores >= threshold, test, test_days),
            "model": model,
        }
    best_name = min(("Logistic regression", "Gradient boosting"), key=lambda n: results[n]["test"]["total_cost"])
    best = results[best_name]

    # Which signals drive the best model (permutation importance on the test months).
    importance = permutation_importance(best["model"], test[features], test["is_fraud"], scoring="average_precision",
                                        n_repeats=5, random_state=SEED, n_jobs=1)
    drivers = sorted(({"feature": FEATURE_LABELS[f], "importance": round(float(m), 4)}
                      for f, m in zip(features, importance.importances_mean)), key=lambda d: -d["importance"])

    # Recall by fraud pattern for the best model and for the rules.
    flags_best = scores_test[best_name] >= best["threshold"]
    flags_rules = rules_flag(test)
    by_pattern = []
    for pattern, group in test[test["is_fraud"] == 1].groupby("fraud_type"):
        mask = test.index.isin(group.index)
        by_pattern.append({
            "pattern": pattern.replace("_", " ").capitalize(),
            "count": int(len(group)),
            "amount": round(float(group["amount"].sum()), 2),
            "recall_model": round(float(flags_best[mask].sum() / len(group)), 4),
            "recall_rules": round(float(flags_rules[mask].sum() / len(group)), 4),
        })

    # Cost by threshold on the test months, for the chart.
    fraud = test["is_fraud"].to_numpy() == 1
    amount = test["amount"].to_numpy()
    thresholds = [round(x, 2) for x in np.linspace(0.05, 0.95, 19)]
    cost_by_threshold = []
    for t in thresholds:
        flags = scores_test[best_name] >= t
        cost_by_threshold.append({"threshold": t, "review_cost": round(float(flags.sum() * REVIEW_COST), 2),
                                  "fraud_missed": round(float(amount[~flags & fraud].sum()), 2),
                                  "alerts_per_day": round(float(flags.sum() / test_days), 1)})

    rules_cost = results["rules"]["test"]["total_cost"]
    model_cost = best["test"]["total_cost"]
    summary = {
        "company": "Kestrel Pay (fictitious)",
        "transactions": len(df),
        "customers": int(df["customer_id"].nunique()),
        "fraud_rate": round(float(df["is_fraud"].mean()), 5),
        "fraud_amount_total": round(float(df.loc[df["is_fraud"] == 1, "amount"].sum()), 2),
        "periods": {"train": "January-March 2025", "validation": "April 2025", "test": "May-June 2025",
                    "test_days": int(test_days), "test_transactions": len(test),
                    "test_fraud": int(test["is_fraud"].sum())},
        "assumptions": {"review_cost_eur": REVIEW_COST, "alerts_per_analyst_day": ALERTS_PER_ANALYST_DAY},
        "approaches": [
            {"name": "Current rules", **results["rules"]["test"]},
            *[{"name": n, "threshold": results[n]["threshold"], "average_precision": results[n]["average_precision"],
               **results[n]["test"]} for n in ("Logistic regression", "Gradient boosting")],
        ],
        "best_model": best_name,
        "savings_vs_rules_test": round(rules_cost - model_cost, 2),
        "savings_vs_rules_monthly": round((rules_cost - model_cost) / test_days * 30.4, 2),
        "analysts_needed": {
            "rules": round(results["rules"]["test"]["alerts_per_day"] / ALERTS_PER_ANALYST_DAY, 1),
            "model": round(best["test"]["alerts_per_day"] / ALERTS_PER_ANALYST_DAY, 1),
        },
        "drivers": drivers[:10],
        "by_pattern": by_pattern,
        "cost_by_threshold": cost_by_threshold,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2)
    (RESULTS_DIR / "summary.json").write_text(payload, encoding="utf-8")
    (RESULTS_DIR / "summary.js").write_text("// Generated by src/fraud_pipeline.py - do not edit by hand.\n"
                                            f"window.FRAUD_SUMMARY = {payload};\n", encoding="utf-8")
    save_figures(test, scores_test, results, best_name, drivers, cost_by_threshold)

    print(f"Test months: {len(test):,} payments, {int(test['is_fraud'].sum())} fraudulent, {test_days} days")
    print(f"{'Approach':<22}{'AP':>7}{'Alerts/day':>12}{'Recall #':>10}{'Recall EUR':>12}{'Precision':>11}{'Total cost':>12}")
    for approach in summary["approaches"]:
        print(f"{approach['name']:<22}{(format(approach['average_precision'], '.3f') if 'average_precision' in approach else '-'):>7}"
              f"{approach['alerts_per_day']:>12.1f}{approach['recall_count']:>10.1%}{approach['recall_amount']:>12.1%}"
              f"{approach['precision']:>11.1%}{approach['total_cost']:>12,.0f}")
    print(f"Best: {best_name} (threshold {best['threshold']}); saves {summary['savings_vs_rules_test']:,.0f} EUR "
          f"over the test months vs rules (~{summary['savings_vs_rules_monthly']:,.0f} EUR/month)")
    print("Recall by pattern:", by_pattern)
    print("Top drivers:", [d["feature"] for d in drivers[:6]])


def save_figures(test, scores_test, results, best_name, drivers, cost_by_threshold):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#c3c2b7", "axes.grid": True,
                         "grid.color": "#e1e0d9", "grid.linewidth": 0.8, "axes.axisbelow": True})

    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    for name, color in (("Logistic regression", ORANGE), ("Gradient boosting", BLUE)):
        precision, recall, _ = precision_recall_curve(test["is_fraud"], scores_test[name])
        ax.plot(recall, precision, color=color, linewidth=2,
                label=f"{name} (AP {results[name]['average_precision']:.2f})")
    rules = results["rules"]["test"]
    ax.scatter([rules["recall_count"]], [rules["precision"]], s=60, color=GREY, zorder=3, edgecolor="white",
               linewidth=1.5, label="Current rules")
    ax.set_xlabel("Recall (share of fraudulent payments caught)")
    ax.set_ylabel("Precision (share of alerts that are fraud)")
    ax.set_title("Precision-recall on May-June 2025", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "precision_recall.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    t = [c["threshold"] for c in cost_by_threshold]
    review = np.array([c["review_cost"] for c in cost_by_threshold])
    missed = np.array([c["fraud_missed"] for c in cost_by_threshold])
    ax.plot(t, review / 1000, color=GREY, linewidth=2, label="Review cost")
    ax.plot(t, missed / 1000, color=ORANGE, linewidth=2, label="Fraud missed")
    ax.plot(t, (review + missed) / 1000, color=BLUE, linewidth=2.4, label="Total")
    i = int(np.argmin(review + missed))
    ax.scatter([t[i]], [(review + missed)[i] / 1000], s=50, color=BLUE, edgecolor="white", linewidth=1.5, zorder=3)
    ax.set_xlabel(f"Alert threshold ({best_name.lower()} score)")
    ax.set_ylabel("Cost over May-June (thousand EUR)")
    ax.set_title("Choosing the alert threshold", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "cost_by_threshold.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    top = drivers[:8][::-1]
    ax.barh([d["feature"] for d in top], [d["importance"] for d in top], color=BLUE, height=0.55)
    ax.set_xlabel("Drop in average precision when the signal is shuffled")
    ax.set_title(f"What drives the {best_name.lower()}", loc="left", fontweight="bold")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "drivers.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
