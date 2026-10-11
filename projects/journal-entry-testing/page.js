// Journal entry testing case study: fills figures, charts and tables from results/summary.js.
(function () {
  "use strict";

  var summary = window.JET_SUMMARY;
  var integer = new Intl.NumberFormat("en-US");
  var money = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var percent = function (share, digits) { return (share * 100).toFixed(digits === undefined ? 1 : digits) + "%"; };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function chips(ids) {
    var list = el("span", "chip-list");
    ids.forEach(function (id) { list.appendChild(el("span", "chip", id)); });
    return list;
  }

  function setText(selector, text) {
    var node = document.querySelector(selector);
    if (node) node.textContent = text;
  }

  function fillKpis() {
    var detection = summary.detection;
    setText('[data-kpi="lines"]', integer.format(summary.dataset.lines));
    setText('[data-kpi="entries-note"]', integer.format(summary.dataset.entries) + " journal entries");
    setText('[data-kpi="tests"]', String(summary.tests.length));
    setText('[data-kpi="detected"]', detection.detected + " / " + detection.planted_cases);
    setText('[data-kpi="reduction"]', "−" + Math.floor((1 - summary.flagged_share) * 100) + "%");
    setText('[data-kpi="flagged-note"]', integer.format(summary.flagged_entries) + " entries to review instead of " +
      integer.format(summary.dataset.entries));
  }

  function renderTestsTable() {
    var host = document.getElementById("tests-table");
    host.appendChild(Charts.buildTable([
      { label: "Test", value: function (t) { return t.id; }, className: "nowrap" },
      { label: "What it looks for", value: function (t) {
        var wrap = el("span");
        wrap.appendChild(el("strong", null, t.title));
        wrap.appendChild(document.createElement("br"));
        wrap.appendChild(el("span", "muted", t.rationale));
        return wrap;
      } },
      { label: "Weight", value: function (t) { return t.weight ? String(t.weight) : "–"; }, numeric: true },
      { label: "Hits", value: function (t) { return integer.format(t.hits); }, numeric: true }
    ], summary.tests, "The 11 journal entry tests"));
    var table = host.querySelector(".table-wrap");
    table.style.border = "0";
  }

  function renderHitsChart() {
    var card = document.getElementById("hits-card");
    var chart = document.getElementById("hits-chart");
    var series = [
      { name: "planted cases", color: "var(--series-1)" },
      { name: "other hits", color: "var(--series-2)" }
    ];
    Charts.stackedBars(chart, {
      ariaLabel: "Entries flagged per test, split between planted cases and other hits",
      series: series,
      categories: summary.tests.map(function (t) {
        return { label: t.id + " · " + t.title, title: t.id + " · " + t.title, values: [t.planted_hits, t.other_hits] };
      }),
      formatValue: function (n) { return integer.format(n); },
      formatTick: function (n) { return integer.format(n); }
    });
    Charts.tableToggle(card, chart, Charts.buildTable([
      { label: "Test", value: function (t) { return t.id + " · " + t.title; } },
      { label: "Planted cases", value: function (t) { return integer.format(t.planted_hits); }, numeric: true },
      { label: "Other hits", value: function (t) { return integer.format(t.other_hits); }, numeric: true },
      { label: "Total", value: function (t) { return integer.format(t.hits); }, numeric: true }
    ], summary.tests, "Entries flagged per test"));
  }

  function renderRiskTable() {
    var host = document.getElementById("risk-table");
    var rows = summary.top_risk.slice(0, 10);
    var maxScore = Math.max.apply(null, rows.map(function (r) { return r.risk_score; }));
    host.appendChild(Charts.buildTable([
      { label: "#", value: function (r) { return String(rows.indexOf(r) + 1); }, numeric: true },
      { label: "Entry", value: function (r) { return el("span", "mono", r.entry_number); }, className: "nowrap" },
      { label: "Date", value: function (r) { return r.entry_date; }, className: "nowrap" },
      { label: "Keyed by", value: function (r) { return r.created_by; } },
      { label: "Amount", value: function (r) { return money.format(r.amount); }, numeric: true },
      { label: "Description", value: function (r) { return r.description; } },
      { label: "Tests", value: function (r) { return chips(r.tests.split(", ")); } },
      { label: "Score", value: function (r) {
        var score = el("span", "score");
        var bar = el("span", "score-bar");
        var fill = el("span");
        fill.style.width = (100 * r.risk_score / maxScore) + "%";
        bar.appendChild(fill);
        score.appendChild(bar);
        score.appendChild(el("span", null, String(r.risk_score)));
        return score;
      }, className: "nowrap" }
    ], rows, "Top 10 entries by risk score"));
  }

  function renderBenford() {
    var card = document.getElementById("benford-card");
    var chart = document.getElementById("benford-chart");
    var benford = summary.benford;
    Charts.columnsWithReference(chart, {
      ariaLabel: "Observed share of each first digit compared with Benford's law",
      valueName: "observed",
      referenceName: "expected",
      valueColor: "var(--series-1)",
      referenceColor: "var(--series-2)",
      axisTitle: "First digit of the amount",
      formatValue: function (share) { return percent(share, 1); },
      formatTick: function (share) { return Math.round(share * 100) + "%"; },
      points: benford.digits.map(function (d) {
        var gap = (d.observed - d.expected) * 100;
        return {
          label: String(d.digit),
          title: "First digit " + d.digit,
          value: d.observed,
          reference: d.expected,
          extraRows: [
            { value: (gap >= 0 ? "+" : "") + gap.toFixed(2) + " pt", name: "difference" },
            { value: integer.format(d.count), name: "amounts" }
          ]
        };
      })
    });
    setText('[data-text="benford-subtitle"]', "Share of " + integer.format(benford.population) +
      " line amounts by first digit, against Benford's law · MAD " + benford.mad + " (" + benford.conformity.toLowerCase() + ")");
    Charts.tableToggle(card, chart, Charts.buildTable([
      { label: "First digit", value: function (d) { return String(d.digit); } },
      { label: "Amounts", value: function (d) { return integer.format(d.count); }, numeric: true },
      { label: "Observed", value: function (d) { return percent(d.observed, 2); }, numeric: true },
      { label: "Expected", value: function (d) { return percent(d.expected, 2); }, numeric: true },
      { label: "Difference", value: function (d) {
        var gap = (d.observed - d.expected) * 100;
        return (gap >= 0 ? "+" : "") + gap.toFixed(2) + " pt";
      }, numeric: true }
    ], benford.digits, "First-digit distribution compared with Benford's law"));
  }

  function renderPlantedTable() {
    var host = document.getElementById("planted-table");
    host.appendChild(Charts.buildTable([
      { label: "Case", value: function (d) { return d.case_id; } },
      { label: "Scenario", value: function (d) {
        var wrap = el("span");
        wrap.appendChild(el("strong", null, d.scenario));
        wrap.appendChild(document.createElement("br"));
        wrap.appendChild(el("span", "muted", d.story));
        return wrap;
      } },
      { label: "Entry", value: function (d) { return el("span", "mono", d.entry_number); }, className: "nowrap" },
      { label: "Designed for", value: function (d) { return chips(d.expected_tests); } },
      { label: "Caught by", value: function (d) { return chips(d.triggered_tests); } },
      { label: "Found", value: function (d) { return d.detected ? "✓ Yes" : "✗ No"; }, className: "nowrap" }
    ], summary.detection.details, "Planted anomalies and the tests that detected them"));
  }

  window.CaseStudy.init();
  if (!summary || !window.Charts) return;
  fillKpis();
  renderTestsTable();
  renderHitsChart();
  renderRiskTable();
  renderBenford();
  renderPlantedTable();
})();
