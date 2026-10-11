// Management reporting case study: interactive web version of the dashboard.
// Every figure is recomputed in the browser from the monthly cube in results/dashboard_data.js,
// with the same definitions as the DAX measures of the Power BI model.
(function () {
  "use strict";

  var cs = window.CaseStudy;
  cs.init();

  var cube = window.SALES_CUBE;
  if (!cube || !window.Charts) return;

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var stores = {};
  cube.stores.forEach(function (s) { stores[s.store_id] = s; });
  var categories = {};
  cube.categories.forEach(function (c) { categories[c.category_id] = c.category; });

  // Row arrays -> objects once.
  var rows = cube.rows.map(function (r) {
    return { year: r[0], month: r[1], store: r[2], category: r[3], net: r[4], gross: r[5],
             discount: r[6], returns: r[7], cost: r[8], units: r[9] };
  });
  var budget = cube.budget.map(function (b) {
    return { month: b[0], store: b[1], category: b[2], net: b[3], margin: b[4] };
  });

  var filters = { region: "", channel: "", category: "" };

  function keep(row) {
    var store = stores[row.store];
    return (!filters.region || store.region === filters.region) &&
           (!filters.channel || store.channel === filters.channel) &&
           (!filters.category || row.category === filters.category);
  }

  function totals(list) {
    var t = { net: 0, gross: 0, discount: 0, returns: 0, cost: 0, units: 0 };
    list.forEach(function (r) { t.net += r.net; t.gross += r.gross; t.discount += r.discount; t.returns += r.returns; t.cost += r.cost; t.units += r.units; });
    t.margin = t.net - t.cost;
    t.marginPct = t.net ? t.margin / t.net : 0;
    return t;
  }

  function compact(value) {
    var abs = Math.abs(value);
    var sign = value < 0 ? "−" : "";
    if (abs >= 1e6) return sign + "€" + (abs / 1e6).toFixed(abs >= 1e7 ? 1 : 2) + "M";
    if (abs >= 1e3) return sign + "€" + Math.round(abs / 1e3) + "k";
    return sign + "€" + Math.round(abs);
  }
  function signedPercent(share, digits) {
    var text = (Math.abs(share) * 100).toFixed(digits === undefined ? 1 : digits) + "%";
    return (share > 0 ? "+" : share < 0 ? "−" : "") + text;
  }
  function signedPoints(points) {
    return (points > 0 ? "+" : points < 0 ? "−" : "") + Math.abs(points).toFixed(1) + " pts";
  }

  // --- Filters ------------------------------------------------------------------
  function fillSelect(id, values, label) {
    var select = document.getElementById(id);
    var all = document.createElement("option");
    all.value = "";
    all.textContent = "All " + label;
    select.appendChild(all);
    values.forEach(function (v) {
      var option = document.createElement("option");
      option.value = v.value;
      option.textContent = v.label;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      filters[select.getAttribute("data-filter")] = select.value;
      render();
    });
  }
  var regions = Array.from(new Set(cube.stores.map(function (s) { return s.region; }))).sort();
  fillSelect("filter-region", regions.map(function (r) { return { value: r, label: r.replace(/-/g, " ") }; }), "regions");
  fillSelect("filter-channel", [{ value: "Store", label: "Stores" }, { value: "Online", label: "Online shop" }], "channels");
  fillSelect("filter-category", cube.categories.map(function (c) { return { value: c.category_id, label: c.category }; }), "categories");
  document.getElementById("filter-reset").addEventListener("click", function () {
    filters = { region: "", channel: "", category: "" };
    document.querySelectorAll("[data-filter]").forEach(function (s) { s.value = ""; });
    render();
  });

  // --- Charts --------------------------------------------------------------------
  var trend = null;
  var storeChart = null;
  var categoryChart = null;

  function render() {
    var current = rows.filter(function (r) { return r.year === 2025 && keep(r); });
    var previous = rows.filter(function (r) { return r.year === 2024 && keep(r); });
    var plan = budget.filter(keep);
    var t25 = totals(current);
    var t24 = totals(previous);
    var budgetNet = plan.reduce(function (s, b) { return s + b.net; }, 0);
    var budgetMargin = plan.reduce(function (s, b) { return s + b.margin; }, 0);

    cs.setText('[data-kpi="net"]', compact(t25.net));
    cs.setText('[data-kpi="net-note"]', signedPercent(t25.net / t24.net - 1) + " vs 2024");
    cs.setText('[data-kpi="budget"]', signedPercent(t25.net / budgetNet - 1));
    cs.setText('[data-kpi="budget-note"]', "budget " + compact(budgetNet));
    cs.setText('[data-kpi="gm"]', (t25.marginPct * 100).toFixed(1) + "%");
    cs.setText('[data-kpi="gm-note"]', signedPoints((t25.marginPct - t24.marginPct) * 100) + " vs 2024");
    var marginGap = t25.margin - budgetMargin;
    cs.setText('[data-kpi="gm-budget"]', (marginGap >= 0 ? "+" : "") + compact(marginGap));
    var gapNode = document.querySelector('[data-kpi="gm-budget"]');
    gapNode.classList.toggle("is-bad", marginGap < 0);
    gapNode.classList.toggle("is-good", marginGap >= 0);

    // Monthly trend: 2025, 2024 and budget.
    var byMonth = function (list, field) {
      var out = MONTHS.map(function () { return 0; });
      list.forEach(function (r) { out[r.month - 1] += r[field]; });
      return out;
    };
    var trendConfig = {
      ariaLabel: "Net sales by month: 2025, 2024 and 2025 budget",
      labels: MONTHS,
      series: [
        { name: "2025", color: "var(--series-1)", values: byMonth(current, "net") },
        { name: "2024", color: "var(--axis)", values: byMonth(previous, "net") },
        { name: "Budget 2025", color: "var(--series-2)", values: byMonth(plan, "net"), dashed: true }
      ],
      formatValue: compact,
      formatTick: compact
    };
    if (trend) trend.update(trendConfig); else trend = Charts.lineChart(document.getElementById("trend-chart"), trendConfig);

    // Stores against budget.
    var storeIds = Object.keys(stores).filter(function (id) {
      var s = stores[id];
      return (!filters.region || s.region === filters.region) && (!filters.channel || s.channel === filters.channel);
    });
    var storeRows = storeIds.map(function (id) {
      var actual = totals(current.filter(function (r) { return r.store === id; }));
      var last = totals(previous.filter(function (r) { return r.store === id; }));
      var target = plan.filter(function (b) { return b.store === id; }).reduce(function (s, b) { return s + b.net; }, 0);
      return { id: id, name: stores[id].store_name, region: stores[id].region, net: actual.net,
               yoy: actual.net / last.net - 1, vsBudget: actual.net / target - 1, budget: target,
               marginPct: actual.marginPct, marginPts: (actual.marginPct - last.marginPct) * 100 };
    }).sort(function (a, b) { return a.vsBudget - b.vsBudget; });
    var storeConfig = {
      ariaLabel: "Net sales against budget by store",
      categories: storeRows.map(function (s) {
        return { label: s.name, title: s.name, value: s.vsBudget * 100,
                 tooltipRows: [{ value: signedPercent(s.vsBudget), name: "vs budget" },
                               { value: compact(s.net - s.budget), name: "gap" },
                               { value: signedPercent(s.yoy), name: "vs 2024" }] };
      }),
      formatValue: function (v) { return signedPercent(v / 100); },
      formatTick: function (v) { return (v > 0 ? "+" : "") + Math.round(v) + "%"; },
      positiveColor: "var(--series-1)",
      negativeColor: "var(--critical)"
    };
    if (storeChart) storeChart.update(storeConfig); else storeChart = Charts.divergingBars(document.getElementById("store-chart"), storeConfig);

    // Categories: margin rate change against last year.
    var categoryIds = Object.keys(categories).filter(function (id) { return !filters.category || id === filters.category; });
    var categoryRows = categoryIds.map(function (id) {
      var a = totals(current.filter(function (r) { return r.category === id; }));
      var l = totals(previous.filter(function (r) { return r.category === id; }));
      return { name: categories[id], pts: (a.marginPct - l.marginPct) * 100, yoy: a.net / l.net - 1,
               units: a.units / l.units - 1, discount: a.gross ? a.discount / a.gross : 0 };
    }).sort(function (a, b) { return a.pts - b.pts; });
    var categoryConfig = {
      ariaLabel: "Gross margin rate change against 2024 by category, in points",
      categories: categoryRows.map(function (c) {
        return { label: c.name, title: c.name, value: c.pts,
                 tooltipRows: [{ value: signedPoints(c.pts), name: "margin rate" },
                               { value: signedPercent(c.yoy), name: "net sales" },
                               { value: signedPercent(c.units), name: "units" },
                               { value: (c.discount * 100).toFixed(1) + "%", name: "discount rate" }] };
      }),
      formatValue: function (v) { return signedPoints(v); },
      formatTick: function (v) { return (v > 0 ? "+" : "") + v.toFixed(Math.abs(v) < 2 && v !== 0 ? 1 : 0); },
      positiveColor: "var(--series-1)",
      negativeColor: "var(--critical)"
    };
    if (categoryChart) categoryChart.update(categoryConfig); else categoryChart = Charts.divergingBars(document.getElementById("category-chart"), categoryConfig);

    // Store table.
    var host = document.getElementById("store-table");
    host.textContent = "";
    host.appendChild(Charts.buildTable([
      { label: "Store", value: function (s) { return s.name; } },
      { label: "Region", value: function (s) { return s.region.replace(/-/g, " "); } },
      { label: "Net sales 2025", value: function (s) { return compact(s.net); }, numeric: true },
      { label: "vs 2024", value: function (s) { return signedPercent(s.yoy); }, numeric: true },
      { label: "vs budget", value: function (s) { return signedPercent(s.vsBudget); }, numeric: true },
      { label: "Gross margin %", value: function (s) { return (s.marginPct * 100).toFixed(1) + "%"; }, numeric: true },
      { label: "Margin vs 2024", value: function (s) { return signedPoints(s.marginPts); }, numeric: true }
    ], storeRows, "Stores: net sales, budget and margin"));
  }

  render();
})();
