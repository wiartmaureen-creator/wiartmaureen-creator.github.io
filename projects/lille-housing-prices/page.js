// Lille housing case study: figures and charts from results/summary.js (written by R/02_analysis.R).
(function () {
  "use strict";

  var cs = window.CaseStudy;
  cs.init();

  var s = window.HOUSING_SUMMARY;
  if (!s || !window.Charts) return;
  var integer = cs.integer;
  var euro = function (v) { return integer.format(Math.round(v)) + " €"; };

  var steps = s.preparation;
  cs.setText('[data-kpi="sales"]', integer.format(s.sales));
  cs.setText('[data-kpi="sales-note"]', "from " + integer.format(steps.all_rows) + " raw records");
  var last = s.index[s.index.length - 1];
  var peak = s.index.reduce(function (a, b) { return b.hedonic > a.hedonic ? b : a; });
  var trough = s.index.filter(function (p) { return p.year > peak.year; })
    .reduce(function (a, b) { return b.hedonic < a.hedonic ? b : a; });
  cs.setText('[data-kpi="index"]', last.hedonic.toFixed(1));
  cs.setText('[data-kpi="index-note"]', "2021 = 100 · peak " + peak.hedonic.toFixed(1) + " in " + peak.year);
  var lille = s.communes.filter(function (c) { return c.commune === "Lille"; })[0];
  var roubaix = s.communes.filter(function (c) { return c.commune === "Roubaix"; })[0];
  if (lille && roubaix) cs.setText('[data-kpi="ratio"]', (lille.median_price_m2 / roubaix.median_price_m2).toFixed(1) + "×");
  cs.setText('[data-kpi="error"]', "±" + Math.round(s.model.median_abs_error_pct) + "%");
  cs.setText('[data-text="index-note"]', "Comparable homes rose to " + peak.hedonic.toFixed(1) + " in " + peak.year +
    ", fell " + Math.abs((trough.hedonic / peak.hedonic - 1) * 100).toFixed(1) + "% by " + trough.year +
    " and stood at " + last.hedonic.toFixed(1) + " in " + last.year + ".");
  cs.setText('[data-text="model"]', "The model explains " + Math.round(s.model.r_squared * 100) +
    "% of the variation in prices. On " + integer.format(s.model.test_sales) + " sales it never saw, the median error is ±" +
    s.model.median_abs_error_pct + "%: honest for data that says nothing about condition, floor, view or energy rating. " +
    "Good enough to screen sales, not to value one specific home.");
  cs.setText('[data-text="bank"]', s.model.above_50_pct + "% of sales are more than 50% above the model's estimate, " +
    s.model.below_50_pct + "% more than 50% below.");

  // Preparation funnel.
  var funnel = [
    { step: "Rows in the Nord department files, 2021–2025", rows: steps.all_rows },
    { step: "Sale rows in the 95 communes of the metropolitan area", rows: steps.mel_sale_rows },
    { step: "Sales of exactly one dwelling", rows: steps.single_dwelling_sales },
    { step: "After quality filters (surface, price, price per m²)", rows: steps.after_quality_filters }
  ];
  document.getElementById("steps-table").appendChild(Charts.buildTable([
    { label: "Step", value: function (r) { return r.step; } },
    { label: "Rows", value: function (r) { return integer.format(r.rows); }, numeric: true },
    { label: "Kept", value: function (r) { return Math.round(r.rows / steps.all_rows * 100) + "%"; }, numeric: true }
  ], funnel, "Data preparation steps"));
  document.querySelector("#steps-table .table-wrap").style.border = "0";

  // Price index.
  var indexCard = document.getElementById("index-card");
  var indexChart = document.getElementById("index-chart");
  Charts.lineChart(indexChart, {
    ariaLabel: "Quality-adjusted and raw price index, 2021 = 100",
    labels: s.index.map(function (p) { return String(p.year); }),
    series: [
      { name: "quality-adjusted", color: "var(--series-1)", values: s.index.map(function (p) { return p.hedonic; }) },
      { name: "raw median", color: "var(--axis)", values: s.index.map(function (p) { return p.raw; }) }
    ],
    formatValue: function (v) { return v.toFixed(1); },
    formatTick: function (v) { return v.toFixed(0); }
  });
  Charts.tableToggle(indexCard, indexChart, Charts.buildTable([
    { label: "Year", value: function (p) { return String(p.year); } },
    { label: "Quality-adjusted", value: function (p) { return p.hedonic.toFixed(1); }, numeric: true },
    { label: "Raw median", value: function (p) { return p.raw.toFixed(1); }, numeric: true }
  ], s.index, "Price index"));

  // Communes: the 20 with the most sales, ranked by price per m2.
  var busiest = s.communes.slice().sort(function (a, b) { return b.sales - a.sales; }).slice(0, 20)
    .sort(function (a, b) { return b.median_price_m2 - a.median_price_m2; });
  var communesCard = document.getElementById("communes-card");
  var communesChart = document.getElementById("communes-chart");
  Charts.stackedBars(communesChart, {
    ariaLabel: "Median price per square metre in the 20 busiest communes, 2024-2025",
    series: [{ name: "per m²", color: "var(--series-1)" }],
    categories: busiest.map(function (c) { return { label: c.commune, title: c.commune + " (" + integer.format(c.sales) + " sales)", values: [c.median_price_m2] }; }),
    formatValue: euro,
    formatTick: function (v) { return integer.format(v); }
  });
  Charts.tableToggle(communesCard, communesChart, Charts.buildTable([
    { label: "Commune", value: function (c) { return c.commune; } },
    { label: "Sales", value: function (c) { return integer.format(c.sales); }, numeric: true },
    { label: "Price per m²", value: function (c) { return euro(c.median_price_m2); }, numeric: true },
    { label: "Flats", value: function (c) { return Math.round(c.flats_share * 100) + "%"; }, numeric: true }
  ], busiest, "Median price per square metre by commune"));

  // Example valuations.
  var host = document.getElementById("example-table");
  host.appendChild(cs.el("p", "muted", "Estimated price of a 60 m², 3-room flat sold at the end of 2025:"));
  host.appendChild(Charts.buildTable([
    { label: "Commune", value: function (e) { return e.commune; } },
    { label: "Estimate", value: function (e) { return euro(e.estimate); }, numeric: true }
  ], s.example, "Example valuations"));
})();
