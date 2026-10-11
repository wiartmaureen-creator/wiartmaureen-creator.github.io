// Fraud detection case study: figures, tables and charts from results/summary.js.
(function () {
  "use strict";

  var cs = window.CaseStudy;
  cs.init();

  var summary = window.FRAUD_SUMMARY;
  if (!summary || !window.Charts) return;

  var approaches = summary.approaches;
  var rules = approaches[0];
  var best = approaches.filter(function (a) { return a.name === summary.best_model; })[0];
  var pct = function (share) { return Math.round(share * 100) + "%"; };
  var keur = function (value) { return "€" + (value / 1000).toFixed(1) + "k"; };

  cs.setText('[data-kpi="alerts"]', String(Math.round(best.alerts_per_day)));
  cs.setText('[data-kpi="alerts-note"]', "instead of " + Math.round(rules.alerts_per_day) + " with the rules");
  cs.setText('[data-kpi="recall"]', pct(best.recall_amount));
  cs.setText('[data-kpi="recall-note"]', "instead of " + pct(rules.recall_amount));
  cs.setText('[data-kpi="precision"]', pct(best.precision));
  cs.setText('[data-kpi="precision-note"]', "instead of " + pct(rules.precision));
  cs.setText('[data-kpi="saving"]', "€" + Math.round(summary.savings_vs_rules_monthly / 1000) + "k");
  cs.setText('[data-text="threshold-note"]', "The threshold chosen on April (" + best.threshold.toFixed(2) +
    ") sits in the flat bottom of the curve. Review cost assumes €" + summary.assumptions.review_cost_eur + " per alert.");

  // Comparison of the three approaches.
  document.getElementById("approaches-table").appendChild(Charts.buildTable([
    { label: "Approach", value: function (a) {
      var wrap = cs.el("span");
      wrap.appendChild(cs.el("strong", null, a.name));
      if (a.threshold) wrap.appendChild(cs.el("span", "muted", " · threshold " + a.threshold.toFixed(2)));
      return wrap;
    } },
    { label: "Alerts / day", value: function (a) { return a.alerts_per_day.toFixed(1); }, numeric: true },
    { label: "Alerts that are fraud", value: function (a) { return (a.precision * 100).toFixed(1) + "%"; }, numeric: true },
    { label: "Frauds caught", value: function (a) { return (a.recall_count * 100).toFixed(1) + "%"; }, numeric: true },
    { label: "Fraud € caught", value: function (a) { return (a.recall_amount * 100).toFixed(1) + "%"; }, numeric: true },
    { label: "Review cost", value: function (a) { return keur(a.review_cost); }, numeric: true },
    { label: "Fraud missed", value: function (a) { return keur(a.fraud_amount_missed); }, numeric: true },
    { label: "Total cost", value: function (a) { return cs.el("strong", null, keur(a.total_cost)); }, numeric: true }
  ], approaches, "Current rules, logistic regression and gradient boosting compared on May-June 2025"));
  document.querySelector("#approaches-table .table-wrap").style.border = "0";

  // Cost by threshold.
  var points = summary.cost_by_threshold;
  var costCard = document.getElementById("cost-card");
  var costChart = document.getElementById("cost-chart");
  Charts.lineChart(costChart, {
    ariaLabel: "Cost over May-June by alert threshold",
    labels: points.map(function (p) { return p.threshold.toFixed(2); }),
    series: [
      { name: "total cost", color: "var(--series-1)", values: points.map(function (p) { return p.review_cost + p.fraud_missed; }) },
      { name: "fraud missed", color: "var(--series-2)", values: points.map(function (p) { return p.fraud_missed; }) },
      { name: "review cost", color: "var(--axis)", values: points.map(function (p) { return p.review_cost; }) }
    ],
    formatValue: keur,
    formatTick: function (v) { return "€" + Math.round(v / 1000) + "k"; }
  });
  Charts.tableToggle(costCard, costChart, Charts.buildTable([
    { label: "Threshold", value: function (p) { return p.threshold.toFixed(2); } },
    { label: "Alerts / day", value: function (p) { return p.alerts_per_day.toFixed(1); }, numeric: true },
    { label: "Review cost", value: function (p) { return keur(p.review_cost); }, numeric: true },
    { label: "Fraud missed", value: function (p) { return keur(p.fraud_missed); }, numeric: true },
    { label: "Total", value: function (p) { return keur(p.review_cost + p.fraud_missed); }, numeric: true }
  ], points, "Cost by alert threshold"));

  // Recall by fraud pattern: rules vs model, as paired meters.
  var host = document.getElementById("pattern-bars");
  summary.by_pattern.forEach(function (p) {
    var row = cs.el("div", "pair");
    var head = cs.el("div", "pair-head");
    head.appendChild(cs.el("strong", null, p.pattern));
    head.appendChild(cs.el("span", "muted", p.count + " payments · €" + Math.round(p.amount).toLocaleString("en-US")));
    row.appendChild(head);
    [["Rules", p.recall_rules, "var(--axis)"], ["Model", p.recall_model, "var(--series-1)"]].forEach(function (item) {
      var line = cs.el("div", "pair-line");
      line.appendChild(cs.el("span", "pair-label", item[0]));
      var track = cs.el("span", "pair-track");
      var fill = cs.el("span", "pair-fill");
      fill.style.width = Math.max(item[1] * 100, 0.5) + "%";
      fill.style.background = item[2];
      track.appendChild(fill);
      line.appendChild(track);
      line.appendChild(cs.el("span", "pair-value", pct(item[1])));
      row.appendChild(line);
    });
    host.appendChild(row);
  });

  // Drivers of the model.
  var driversCard = document.getElementById("drivers-card");
  var driversChart = document.getElementById("drivers-chart");
  var drivers = summary.drivers.slice(0, 8);
  Charts.stackedBars(driversChart, {
    ariaLabel: "Permutation importance of the model's signals",
    series: [{ name: "importance", color: "var(--series-1)" }],
    categories: drivers.map(function (d) { return { label: d.feature, title: d.feature, values: [d.importance] }; }),
    formatValue: function (v) { return v.toFixed(3); },
    formatTick: function (v) { return v.toFixed(2); }
  });
  Charts.tableToggle(driversCard, driversChart, Charts.buildTable([
    { label: "Signal", value: function (d) { return d.feature; } },
    { label: "Importance", value: function (d) { return d.importance.toFixed(3); }, numeric: true }
  ], drivers, "Permutation importance"));
})();
