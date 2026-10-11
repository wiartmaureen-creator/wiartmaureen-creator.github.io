# Detecting fraudulent card payments: from rules to a cost-based model

**Which payments should the fraud team review, so that fraud losses plus review costs are as low as possible?**

Six months of card payments for a fictitious payment provider (241,831 payments, 0.40% fraudulent).
The current alert rules are compared with a logistic regression and gradient boosting, and the alert
threshold is chosen **in euros**: review cost (about €8 an alert) plus the amount of fraud missed.

➡️ **Notebook:** [`notebooks/fraud_detection.ipynb`](notebooks/fraud_detection.ipynb) · **Case study:** [`index.html`](index.html)

## Results on May-June 2025 (data the models never saw)

| | Current rules | Logistic regression | Gradient boosting |
|---|---|---|---|
| Alerts per day | 42.8 | 14.8 | **13.2** |
| Share of alerts that are fraud (precision) | 4.7% | 23.2% | **32.5%** |
| Fraudulent payments caught | 38.6% | 66.1% | **82.6%** |
| Fraud amount caught | 44.2% | 78.1% | **87.0%** |
| Total cost (review + fraud missed) | €52.6k | €19.7k | **€13.8k** |
| Average precision | – | 0.45 | **0.72** |

**Decision:** replace the rules with the gradient boosting model (after a two-week shadow run), alert at
the threshold that matches the team's capacity (about 13 alerts a day), keep a safety-net rule for very
large payments and retrain monthly. Estimated saving: about **€19k a month** with a third of the alerts.

| Fraud pattern | Caught by rules | Caught by the model |
|---|---|---|
| Account takeover | 39% | 79% |
| Card testing | 47% | 99% |
| "Quiet" fraud (looks like normal spending) | 0% | 22% |

Quiet fraud is the honest limit: no behavioural model sees it; it calls for other controls such as
strong customer authentication.

## Method

- **Behavioural features from past payments only** (`src/fraud_pipeline.py`): amount vs the customer's
  usual amount, new device, first payment in a country, payments in the last hour / 24 hours, tiny
  "test" payments in the last 10 minutes, time since the previous payment, night-time, channel, merchant
  category, tenure. Time windows use `closed="left"` and rolling means are shifted, so no information
  from later payments leaks into a feature.
- **Time-based split**: train January-March, choose the threshold on April, report on May-June.
- **Models**: scikit-learn pipelines (scaling and one-hot encoding), `LogisticRegression` and
  `HistGradientBoostingClassifier`, both with class weights for the 0.4% fraud rate.
- **Explainability**: permutation importance (amount, merchant category, time since the previous
  payment, online, new device, paid abroad).

## The data

Synthetic (`src/generate_transactions.py`, seeded): 3,000 customers with their own spending level,
hours, devices and trips abroad. Legitimate behaviour deliberately looks suspicious at times (foreign
websites, new phones, night workers, bursts of shopping, strings of transport tickets), so the problem
is not artificially easy. Three fraud patterns are injected: account takeover, card testing and quiet fraud.

## Run it

```bash
pip install pandas scikit-learn matplotlib nbformat nbconvert ipykernel
python src/generate_transactions.py   # data/transactions.csv.gz
python src/fraud_pipeline.py          # results/summary.json, images/*.png
python src/build_notebook.py          # notebooks/fraud_detection.ipynb (executed)
```

---
*Kestrel Pay is fictitious; all data is synthetic.*
