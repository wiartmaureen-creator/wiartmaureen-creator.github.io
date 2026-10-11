"""Build and execute notebooks/fraud_detection.ipynb, the narrative version of the analysis.

The notebook reuses the functions of src/fraud_pipeline.py (one source of truth)
and adds the exploratory analysis and the reasoning between the steps.

Usage:
    python src/build_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

PROJECT_DIR = Path(__file__).resolve().parent.parent
NOTEBOOK = PROJECT_DIR / "notebooks" / "fraud_detection.ipynb"

CELLS = [
    ("md", """# Detecting fraudulent card payments: from rules to a cost-based model

**Business question.** Kestrel Pay (a fictitious payment provider) reviews suspicious card payments with a small
fraud team. Today, alerts come from three rules. Too many alerts are false, and too much fraud gets through.
**Which payments should the team review, so that fraud losses plus review costs are as low as possible?**

**Approach.**
1. Explore six months of payments (January to June 2025) and the fraud patterns in them.
2. Build behavioural features from each customer's *past* payments only.
3. Train on January-March, tune the alert threshold on April, report on May-June, as a real deployment would.
4. Compare the current rules, a logistic regression and gradient boosting **in euros**, not only in model scores.

*The data is synthetic: real payment data is confidential. The simulation includes legitimate behaviour that looks
suspicious (trips abroad, foreign websites, new phones, night workers) so the problem is not artificially easy.*"""),
    ("code", """import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd().parent / "src"))
import fraud_pipeline as fp
%matplotlib inline

pd.set_option("display.float_format", lambda v: f"{v:,.3f}")
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#e1e0d9", "axes.axisbelow": True, "figure.dpi": 110})
data = pd.read_csv(fp.DATA_FILE, parse_dates=["timestamp"])
print(f"{len(data):,} payments, {data.customer_id.nunique():,} customers, "
      f"{data.is_fraud.sum()} fraudulent ({data.is_fraud.mean():.2%})")
data.head()"""),
    ("md", """## 1. Exploring the payments

Fraud is rare: about 4 payments in 1,000. A model that says "never fraud" would be 99.6% accurate and useless,
so accuracy is the wrong yardstick. What matters is how much fraud is caught and how many alerts it takes."""),
    ("code", """fraud = data[data.is_fraud == 1]
summary = fraud.groupby("fraud_type").agg(payments=("amount", "size"), amount_eur=("amount", "sum"),
                                          median_amount=("amount", "median"))
summary.loc["all fraud"] = [len(fraud), fraud.amount.sum(), fraud.amount.median()]
summary"""),
    ("code", """data["hour"] = data.timestamp.dt.hour
data["abroad"] = data.country != data.home_country
fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
data.groupby("hour").is_fraud.mean().mul(100).plot(ax=axes[0], color=fp.BLUE, lw=2)
axes[0].set(title="Fraud rate by hour (%)", xlabel="Hour of day", ylabel="")
(data.groupby("merchant_category").is_fraud.mean().mul(100).sort_values()
     .plot.barh(ax=axes[1], color=fp.BLUE))
axes[1].set(title="Fraud rate by merchant category (%)", ylabel="")
(data.groupby(["channel", "abroad"]).is_fraud.mean().mul(100).unstack()
     .rename(columns={False: "home country", True: "abroad"})
     .plot.bar(ax=axes[2], color=[fp.GREY, fp.ORANGE], rot=0))
axes[2].set(title="Fraud rate by channel and location (%)", xlabel="")
plt.tight_layout()
plt.show()"""),
    ("md", """Fraud concentrates at night, on electronics and gift cards, and online abroad. But each signal alone is weak:
most night-time payments, most foreign payments and most electronics purchases are legitimate. That is exactly
why the current rules raise so many false alerts."""),
    ("md", """## 2. Behavioural features, without looking into the future

Fraud is visible in *behaviour*: a burst of payments, a new device, an amount far above the customer's habits,
tiny "test" payments just before a large one. Each feature is computed from the customer's **previous** payments
only (`closed="left"` time windows, shifted rolling means): a feature that peeks at later payments would make the
model look better on paper than it can ever be in production."""),
    ("code", """df = fp.build_features(data)
features = fp.NUMERIC_FEATURES + fp.CATEGORICAL_FEATURES
df[["customer_id", "timestamp", "amount", "amount_vs_usual", "new_device", "count_1h",
    "small_payments_10min", "is_fraud"]].tail(8)"""),
    ("code", """comparison = df.groupby("is_fraud")[["amount_vs_usual", "new_device", "new_country", "count_1h",
                                      "small_payments_10min", "is_night"]].mean()
comparison.index = ["legitimate", "fraud"]
comparison.T"""),
    ("md", """## 3. A split that mirrors real life

The model is trained on January-March, the alert threshold is chosen on April, and every figure reported below
comes from May-June: payments the model has never seen, later in time."""),
    ("code", """train = df[df.timestamp < fp.TRAIN_END]
validation = df[(df.timestamp >= fp.TRAIN_END) & (df.timestamp < fp.VALIDATION_END)]
test = df[df.timestamp >= fp.VALIDATION_END]
test_days = (test.timestamp.max().normalize() - test.timestamp.min().normalize()).days + 1
pd.DataFrame({"payments": [len(train), len(validation), len(test)],
              "fraudulent": [train.is_fraud.sum(), validation.is_fraud.sum(), test.is_fraud.sum()]},
             index=["train (Jan-Mar)", "validation (Apr)", "test (May-Jun)"])"""),
    ("md", """## 4. Rules versus models, in euros

**Cost model.** Reviewing an alert costs about **€8** (12 minutes of an analyst at €40/hour). A fraud that is
not alerted costs its full amount. A fraud that is alerted is assumed to be stopped. The best threshold for each
model is the one with the lowest *review cost + fraud missed* on April."""),
    ("code", """rows = [{"approach": "Current rules", **fp.outcome(fp.rules_flag(test), test, test_days)}]
models, scores = fp.make_models(), {}
for name, model in models.items():
    model.fit(train[features], train.is_fraud)
    threshold, _ = fp.best_threshold(model.predict_proba(validation[features])[:, 1], validation)
    scores[name] = model.predict_proba(test[features])[:, 1]
    rows.append({"approach": f"{name} (threshold {threshold:.2f})",
                 **fp.outcome(scores[name] >= threshold, test, test_days)})
results = pd.DataFrame(rows).set_index("approach")
results[["alerts_per_day", "recall_count", "recall_amount", "precision", "review_cost",
         "fraud_amount_missed", "total_cost"]]"""),
    ("md", """Gradient boosting catches far more fraud **with fewer alerts**: the team reviews about 13 payments a day instead
of 43, and one alert in three is a real fraud instead of one in twenty. Over May-June the total cost falls by
roughly three quarters."""),
    ("code", """from IPython.display import Image, display
display(Image(filename=str(fp.IMAGES_DIR / "precision_recall.png"), width=620))
display(Image(filename=str(fp.IMAGES_DIR / "cost_by_threshold.png"), width=620))"""),
    ("md", """The cost curve is flat around its minimum: any threshold between about 0.45 and 0.65 gives a similar total
cost. That matters for the decision: the threshold can be set to match the team's capacity without losing much."""),
    ("md", """## 5. What drives the model, and what it misses

Permutation importance measures how much the model's average precision drops when one signal is shuffled.
The leading signals are the ones a fraud analyst would recognise, which makes the alerts explainable."""),
    ("code", """display(Image(filename=str(fp.IMAGES_DIR / "drivers.png"), width=620))
best = max(scores, key=lambda n: results.loc[results.index.str.startswith(n), "recall_amount"].iloc[0])
flags = scores[best] >= fp.best_threshold(models[best].predict_proba(validation[features])[:, 1], validation)[0]
by_pattern = (test.assign(alerted=flags, rules=fp.rules_flag(test))[test.is_fraud == 1]
                  .groupby("fraud_type")[["alerted", "rules"]].mean()
                  .rename(columns={"alerted": f"caught by {best.lower()}", "rules": "caught by rules"}))
by_pattern"""),
    ("md", """Account takeovers and card testing are caught well. "Quiet" fraud, single payments that look like the
customer's usual spending, mostly gets through: no behavioural model will see it, and it is a small share of the
amount. It needs other controls (strong customer authentication, customer reports)."""),
    ("md", """## 6. Recommendation

| | Current rules | Gradient boosting |
|---|---|---|
| Alerts per day | ~43 | ~13 |
| Share of alerts that are fraud | ~5% | ~33% |
| Fraud caught (amount) | ~44% | ~87% |
| Total cost, May-June | ~€53k | ~€14k |

1. **Replace the rules with the model** for alerting, starting with a two-week shadow run where both run side by side.
2. **Set the threshold from capacity**: at about 13 alerts a day, the team handles the volume with spare time for
   investigations; lowering the threshold catches a little more fraud for many more alerts.
3. **Keep a rule for very large payments** as a safety net, and retrain monthly as fraud patterns change.
4. **Measure** weekly: fraud caught in euros, alerts per day, share of alerts confirmed as fraud.

*Limits: synthetic data; the cost model ignores customer friction from false alerts and assumes alerted fraud is
always stopped. A real project would calibrate both with the fraud team.*"""),
]


def main():
    notebook = nbformat.v4.new_notebook()
    notebook.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    notebook.cells = [nbformat.v4.new_markdown_cell(text) if kind == "md" else nbformat.v4.new_code_cell(text)
                      for kind, text in CELLS]
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(notebook, {"metadata": {"path": str(NOTEBOOK.parent)}})
    nbformat.write(notebook, NOTEBOOK)
    print(f"Executed notebook written to {NOTEBOOK.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
