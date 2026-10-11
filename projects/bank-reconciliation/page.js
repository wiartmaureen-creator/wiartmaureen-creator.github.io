// Bank reconciliation case study: figures and chart from results/summary.js.
(function () {
  "use strict";

  var cs = window.CaseStudy;
  cs.init();

  var summary = window.RECON_SUMMARY;
  if (!summary || !window.Charts) return;
  var integer = cs.integer;

  cs.setText('[data-kpi="lines"]', integer.format(summary.bank_lines));
  cs.setText('[data-kpi="lines-note"]', "against " + integer.format(summary.ledger_lines) + " ledger lines");
  cs.setText('[data-kpi="matched"]', cs.percent(summary.matched_share));
  cs.setText('[data-kpi="matched-note"]', summary.matched_by_reference + " by reference, " +
    summary.matched_by_amount + " by amount and date");
  cs.setText('[data-kpi="items"]', integer.format(summary.items_to_explain));
  cs.setText('[data-kpi="difference"]', cs.euros(summary.statement.difference));

  var results = [
    { label: "Matched by reference", value: summary.matched_by_reference },
    { label: "Matched by amount and date", value: summary.matched_by_amount },
    { label: "Matched, amount differs", value: summary.amount_differences },
    { label: "Not in the books", value: summary.not_in_books }
  ];
  var card = document.getElementById("match-card");
  var chart = document.getElementById("match-chart");
  Charts.stackedBars(chart, {
    ariaLabel: "Bank lines by matching result",
    series: [{ name: "bank lines", color: "var(--series-1)" }],
    categories: results.map(function (r) { return { label: r.label, title: r.label, values: [r.value] }; }),
    formatValue: function (n) { return integer.format(n); },
    formatTick: function (n) { return integer.format(n); }
  });
  Charts.tableToggle(card, chart, Charts.buildTable([
    { label: "Result", value: function (r) { return r.label; } },
    { label: "Bank lines", value: function (r) { return integer.format(r.value); }, numeric: true },
    { label: "Share", value: function (r) { return cs.percent(r.value / summary.bank_lines); }, numeric: true }
  ], results, "Bank lines by matching result"));
})();
