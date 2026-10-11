/* Small dependency-free SVG charts for the case studies.
   Colours are CSS custom properties, so switching light/dark needs no re-render.
   Every chart has a hover/focus tooltip and a table twin (see tableToggle). */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (parent) parent.appendChild(node);
    return node;
  }

  function htmlEl(tag, className, text, parent) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function niceStep(max, targetTicks) {
    var raw = max / targetTicks;
    var magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    var normalised = raw / magnitude;
    var step = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 2.5 ? 2.5 : normalised <= 5 ? 5 : 10;
    return step * magnitude;
  }

  // A rectangle with only its data end rounded: "right" for bars, "top" for columns.
  function roundedEndPath(x, y, w, h, r, direction) {
    if (w <= 0 || h <= 0) return "";
    r = direction === "right" ? Math.min(r, w, h / 2) : Math.min(r, h, w / 2);
    if (direction === "right") {
      return "M" + x + "," + y + "h" + (w - r) + "a" + r + "," + r + " 0 0 1 " + r + "," + r +
        "v" + (h - 2 * r) + "a" + r + "," + r + " 0 0 1 " + (-r) + "," + r + "h" + (-(w - r)) + "Z";
    }
    return "M" + x + "," + (y + h) + "v" + (-(h - r)) + "a" + r + "," + r + " 0 0 1 " + r + "," + (-r) +
      "h" + (w - 2 * r) + "a" + r + "," + r + " 0 0 1 " + r + "," + r + "v" + (h - r) + "Z";
  }

  function squarePath(x, y, w, h) {
    if (w <= 0 || h <= 0) return "";
    return "M" + x + "," + y + "h" + w + "v" + h + "h" + (-w) + "Z";
  }

  // Shorten an SVG label with an ellipsis until it fits the available width.
  function fitText(textNode, maxWidth) {
    var full = textNode.textContent;
    if (textNode.getComputedTextLength() <= maxWidth) return;
    var text = full;
    while (text.length > 4 && textNode.getComputedTextLength() > maxWidth) {
      text = text.slice(0, -1);
      textNode.textContent = text.trimEnd() + "…";
    }
    var title = svgEl("title", {}, textNode);
    title.textContent = full;
  }

  function createTooltip(container) {
    var tip = htmlEl("div", "tooltip", null, container);
    tip.setAttribute("aria-hidden", "true");
    return {
      show: function (title, rows, x, y) {
        tip.textContent = "";
        htmlEl("div", "tooltip-title", title, tip);
        rows.forEach(function (row) {
          var line = htmlEl("div", "tooltip-row", null, tip);
          var key = htmlEl("span", "tooltip-key", null, line);
          if (row.color) key.style.background = row.color; else key.style.background = "transparent";
          htmlEl("span", "tooltip-value", row.value, line);
          htmlEl("span", "tooltip-name", row.name, line);
        });
        tip.classList.add("is-visible");
        var width = tip.offsetWidth;
        var height = tip.offsetHeight;
        var left = x + 14;
        if (left + width > container.clientWidth) left = x - width - 14;
        if (left < 0) left = 0;
        var top = y - height - 12;
        if (top < 0) top = y + 18;
        tip.style.left = left + "px";
        tip.style.top = top + "px";
      },
      hide: function () { tip.classList.remove("is-visible"); }
    };
  }

  function pointerPosition(event, container) {
    var box = container.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  }

  function elementCentre(node, container) {
    var box = container.getBoundingClientRect();
    var rect = node.getBoundingClientRect();
    return { x: rect.left - box.left + rect.width / 2, y: rect.top - box.top + rect.height / 3 };
  }

  // Wire hover + keyboard focus on a mark group to the shared tooltip.
  function bindTooltip(group, hitTarget, container, tooltip, content) {
    function activate(position) {
      group.classList.add("is-active");
      var data = content();
      tooltip.show(data.title, data.rows, position.x, position.y);
    }
    function deactivate() {
      group.classList.remove("is-active");
      tooltip.hide();
    }
    hitTarget.addEventListener("pointermove", function (event) { activate(pointerPosition(event, container)); });
    hitTarget.addEventListener("pointerleave", deactivate);
    group.addEventListener("focus", function () { activate(elementCentre(hitTarget, container)); });
    group.addEventListener("blur", deactivate);
  }

  function onResize(container, render) {
    var lastWidth = container.clientWidth;
    if (!("ResizeObserver" in window)) {
      window.addEventListener("resize", render);
      return;
    }
    new ResizeObserver(function () {
      if (Math.abs(container.clientWidth - lastWidth) > 4) {
        lastWidth = container.clientWidth;
        render();
      }
    }).observe(container);
  }

  /* Horizontal stacked bars.
     config = { categories: [{ label, title, values: [..] }], series: [{ name, color }],
                ariaLabel, formatValue(n), formatTick(n) } */
  function stackedBars(container, config) {
    var tooltip = createTooltip(container);
    var format = config.formatValue || String;

    function render() {
      var previous = container.querySelector("svg");
      if (previous) previous.remove();

      var width = Math.max(container.clientWidth, 260);
      var narrow = width < 560;
      var labelWidth = narrow ? 0 : Math.min(300, Math.round(width * 0.38));
      var rowHeight = narrow ? 50 : 36;
      var barHeight = 16;
      var categories = config.categories;
      var totals = categories.map(function (c) { return c.values.reduce(function (a, b) { return a + b; }, 0); });
      var maxTotal = Math.max.apply(null, totals.concat([1]));
      var step = niceStep(maxTotal, narrow ? 3 : 5);
      var axisMax = Math.ceil(maxTotal / step) * step;
      var plotLeft = narrow ? 0 : labelWidth + 14;
      var plotRight = width - 36;
      var plotBottom = categories.length * rowHeight;
      var height = plotBottom + 30;
      var x = function (value) { return plotLeft + (value / axisMax) * (plotRight - plotLeft); };

      var svg = svgEl("svg", { width: width, height: height, viewBox: "0 0 " + width + " " + height,
        role: "img", "aria-label": config.ariaLabel });
      container.insertBefore(svg, container.firstChild);

      for (var tick = 0; tick <= axisMax + 1e-9; tick += step) {
        var gx = Math.round(x(tick)) + 0.5;
        svgEl("line", { "class": tick === 0 ? "baseline" : "grid", x1: gx, x2: gx, y1: 0, y2: plotBottom }, svg);
        // In the narrow layout the zero tick sits on the left edge: anchor it at its start.
        var label = svgEl("text", { "class": "axis-label", x: gx, y: plotBottom + 20,
          "text-anchor": narrow && tick === 0 ? "start" : "middle" }, svg);
        label.textContent = config.formatTick ? config.formatTick(tick) : String(tick);
      }

      categories.forEach(function (category, index) {
        var rowTop = index * rowHeight;
        var group = svgEl("g", { tabindex: "0", "aria-label": category.title + ": " +
          category.values.map(function (v, s) { return config.series[s].name + " " + format(v); }).join(", ") }, svg);
        svgEl("rect", { "class": "row-bg", x: -6, y: rowTop + 2, width: width + 12, height: rowHeight - 4, rx: 6 }, group);

        var barY = narrow ? rowTop + 26 : rowTop + (rowHeight - barHeight) / 2;
        var text = svgEl("text", { "class": "category-label",
          x: narrow ? 0 : labelWidth, y: narrow ? rowTop + 17 : rowTop + rowHeight / 2 + 4.5,
          "text-anchor": narrow ? "start" : "end" }, group);
        text.textContent = category.label;
        fitText(text, narrow ? width - 8 : labelWidth - 4);

        var segments = category.values
          .map(function (value, seriesIndex) { return { value: value, seriesIndex: seriesIndex }; })
          .filter(function (segment) { return segment.value > 0; });
        var cursor = 0;
        segments.forEach(function (segment, k) {
          var isLast = k === segments.length - 1;
          var x0 = x(cursor);
          var w = x(cursor + segment.value) - x0 - (isLast ? 0 : 2); // 2px surface gap between segments
          svgEl("path", { "class": "mark",
            d: isLast ? roundedEndPath(x0, barY, w, barHeight, 4, "right") : squarePath(x0, barY, w, barHeight),
            style: "fill:" + config.series[segment.seriesIndex].color }, group);
          cursor += segment.value;
        });

        var valueText = svgEl("text", { "class": "value-label", x: x(totals[index]) + 8, y: barY + barHeight / 2 + 4.5 }, group);
        valueText.textContent = format(totals[index]);

        var hit = svgEl("rect", { "class": "hit", x: -6, y: rowTop, width: width + 12, height: rowHeight }, group);
        bindTooltip(group, hit, container, tooltip, function () {
          return {
            title: category.title,
            rows: category.values.map(function (value, s) {
              return { color: config.series[s].color, value: format(value), name: config.series[s].name };
            })
          };
        });
      });
    }

    render();
    onResize(container, render);
  }

  /* Columns with a reference line (e.g. observed vs expected shares).
     config = { points: [{ label, value, reference, title, extraRows: [] }],
                valueName, referenceName, valueColor, referenceColor,
                formatValue(n), formatTick(n), axisTitle, ariaLabel } */
  function columnsWithReference(container, config) {
    var tooltip = createTooltip(container);

    function render() {
      var previous = container.querySelector("svg");
      if (previous) previous.remove();

      var width = Math.max(container.clientWidth, 260);
      var narrow = width < 520;
      var margin = { top: 12, right: 8, bottom: 52, left: 46 };
      var height = narrow ? 270 : 320;
      var plotWidth = width - margin.left - margin.right;
      var plotHeight = height - margin.top - margin.bottom;
      var points = config.points;
      var maxValue = Math.max.apply(null, points.map(function (p) { return Math.max(p.value, p.reference); }));
      var step = niceStep(maxValue, 5);
      var axisMax = Math.ceil(maxValue / step) * step;
      var baseY = margin.top + plotHeight;
      var y = function (value) { return margin.top + plotHeight - (value / axisMax) * plotHeight; };
      var band = plotWidth / points.length;
      var barWidth = Math.min(24, band * 0.5);
      var cx = function (index) { return margin.left + band * index + band / 2; };

      var svg = svgEl("svg", { width: width, height: height, viewBox: "0 0 " + width + " " + height,
        role: "img", "aria-label": config.ariaLabel });
      container.insertBefore(svg, container.firstChild);

      for (var tick = 0; tick <= axisMax + 1e-9; tick += step) {
        var gy = Math.round(y(tick)) + 0.5;
        svgEl("line", { "class": tick === 0 ? "baseline" : "grid", x1: margin.left, x2: width - margin.right, y1: gy, y2: gy }, svg);
        var label = svgEl("text", { "class": "axis-label", x: margin.left - 8, y: gy + 4, "text-anchor": "end" }, svg);
        label.textContent = config.formatTick(tick);
      }

      var groups = points.map(function (point, index) {
        var group = svgEl("g", { tabindex: "0", "aria-label": point.title + ": " + config.valueName + " " +
          config.formatValue(point.value) + ", " + config.referenceName + " " + config.formatValue(point.reference) }, svg);
        svgEl("rect", { "class": "row-bg", x: cx(index) - band / 2 + 2, y: margin.top, width: band - 4, height: plotHeight, rx: 6 }, group);
        svgEl("path", { "class": "mark", d: roundedEndPath(cx(index) - barWidth / 2, y(point.value), barWidth, baseY - y(point.value), 4, "top"),
          style: "fill:" + config.valueColor }, group);
        var xLabel = svgEl("text", { "class": "category-label", x: cx(index), y: baseY + 20, "text-anchor": "middle" }, group);
        xLabel.textContent = point.label;
        return group;
      });

      // Reference line drawn above the columns, with ringed markers.
      var linePoints = points.map(function (point, index) { return cx(index) + "," + y(point.reference); }).join(" ");
      svgEl("polyline", { points: linePoints, fill: "none", "stroke-width": 2, "stroke-linejoin": "round",
        "stroke-linecap": "round", style: "stroke:" + config.referenceColor, "pointer-events": "none" }, svg);
      points.forEach(function (point, index) {
        svgEl("circle", { cx: cx(index), cy: y(point.reference), r: 4, "stroke-width": 2,
          style: "fill:" + config.referenceColor + ";stroke:var(--surface)", "pointer-events": "none" }, svg);
      });

      var axisTitle = svgEl("text", { "class": "axis-label", x: margin.left + plotWidth / 2, y: height - 8, "text-anchor": "middle" }, svg);
      axisTitle.textContent = config.axisTitle;

      points.forEach(function (point, index) {
        var hit = svgEl("rect", { "class": "hit", x: cx(index) - band / 2, y: margin.top, width: band, height: plotHeight + 28 }, groups[index]);
        bindTooltip(groups[index], hit, container, tooltip, function () {
          return {
            title: point.title,
            rows: [
              { color: config.valueColor, value: config.formatValue(point.value), name: config.valueName },
              { color: config.referenceColor, value: config.formatValue(point.reference), name: config.referenceName }
            ].concat(point.extraRows || [])
          };
        });
      });
    }

    render();
    onResize(container, render);
  }

  /* Build an accessible table from column definitions and rows.
     columns = [{ label, value(row), numeric }] */
  function buildTable(columns, rows, caption) {
    var wrap = htmlEl("div", "table-wrap");
    var table = htmlEl("table", null, null, wrap);
    if (caption) {
      var cap = htmlEl("caption", null, caption, table);
      cap.style.cssText = "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);";
    }
    var headRow = htmlEl("tr", null, null, htmlEl("thead", null, null, table));
    columns.forEach(function (column) {
      var th = htmlEl("th", column.numeric ? "num" : null, column.label, headRow);
      th.setAttribute("scope", "col");
    });
    var body = htmlEl("tbody", null, null, table);
    rows.forEach(function (row) {
      var tr = htmlEl("tr", null, null, body);
      columns.forEach(function (column) {
        var cell = htmlEl("td", column.numeric ? "num" : (column.className || null), null, tr);
        var value = column.value(row);
        if (value instanceof Node) cell.appendChild(value); else cell.textContent = value;
      });
    });
    return wrap;
  }

  // Swap a chart for its table twin with the card's toggle button.
  function tableToggle(card, chartNode, tableNode) {
    var button = card.querySelector(".chart-toggle");
    if (!button) return;
    tableNode.hidden = true;
    chartNode.parentNode.insertBefore(tableNode, chartNode.nextSibling);
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", function () {
      var showTable = tableNode.hidden;
      tableNode.hidden = !showTable;
      chartNode.hidden = showTable;
      var legend = card.querySelector(".legend");
      if (legend) legend.hidden = showTable;
      button.textContent = showTable ? "Show chart" : "Show table";
      button.setAttribute("aria-pressed", String(showTable));
    });
  }

  function niceRange(min, max, ticks) {
    min = Math.min(0, min);
    max = Math.max(0, max);
    if (max === min) max = min + 1;
    var step = niceStep(max - min, ticks);
    return { min: Math.floor(min / step) * step, max: Math.ceil(max / step) * step, step: step };
  }

  /* Multi-series line chart with a crosshair tooltip. Returns { update(config) }.
     config = { labels: [..], series: [{ name, color, values: [..], dashed }],
                formatValue(n), formatTick(n), ariaLabel } */
  function lineChart(container, initialConfig) {
    var config = initialConfig;
    var tooltip = createTooltip(container);
    var activeIndex = null;

    function render() {
      var previous = container.querySelector("svg");
      if (previous) previous.remove();
      var width = Math.max(container.clientWidth, 260);
      var height = width < 520 ? 240 : 290;
      var margin = { top: 14, right: 16, bottom: 34, left: 64 };
      var plotWidth = width - margin.left - margin.right;
      var plotHeight = height - margin.top - margin.bottom;
      var all = [];
      config.series.forEach(function (s) { s.values.forEach(function (v) { if (v !== null) all.push(v); }); });
      var range = niceRange(Math.min.apply(null, all), Math.max.apply(null, all), 4);
      var count = config.labels.length;
      var x = function (i) { return margin.left + (count === 1 ? plotWidth / 2 : (i / (count - 1)) * plotWidth); };
      var y = function (v) { return margin.top + plotHeight - ((v - range.min) / (range.max - range.min)) * plotHeight; };

      var svg = svgEl("svg", { width: width, height: height, viewBox: "0 0 " + width + " " + height,
        role: "img", tabindex: "0", "aria-label": config.ariaLabel + ". Use the left and right arrow keys to read each month." });
      container.insertBefore(svg, container.firstChild);

      for (var tick = range.min; tick <= range.max + range.step / 2; tick += range.step) {
        var gy = Math.round(y(tick)) + 0.5;
        svgEl("line", { "class": Math.abs(tick) < 1e-9 ? "baseline" : "grid", x1: margin.left, x2: width - margin.right, y1: gy, y2: gy }, svg);
        var label = svgEl("text", { "class": "axis-label", x: margin.left - 8, y: gy + 4, "text-anchor": "end" }, svg);
        label.textContent = config.formatTick(tick);
      }
      var every = width < 520 ? 2 : 1;
      config.labels.forEach(function (text, i) {
        if (i % every) return;
        var label = svgEl("text", { "class": "axis-label", x: x(i), y: height - 12, "text-anchor": "middle" }, svg);
        label.textContent = text;
      });

      var crosshair = svgEl("line", { "class": "baseline", y1: margin.top, y2: margin.top + plotHeight, x1: -10, x2: -10, visibility: "hidden" }, svg);
      config.series.forEach(function (s) {
        var points = s.values.map(function (v, i) { return v === null ? null : x(i) + "," + y(v); }).filter(Boolean).join(" ");
        var attrs = { points: points, fill: "none", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
          style: "stroke:" + s.color };
        if (s.dashed) attrs["stroke-dasharray"] = "5 4";
        svgEl("polyline", attrs, svg);
        var last = s.values.length - 1;
        while (last >= 0 && s.values[last] === null) last -= 1;
        if (last >= 0) {
          svgEl("circle", { cx: x(last), cy: y(s.values[last]), r: 4, "stroke-width": 2,
            style: "fill:" + s.color + ";stroke:var(--surface)" }, svg);
        }
      });
      var markers = config.series.map(function (s) {
        return svgEl("circle", { r: 4, "stroke-width": 2, visibility: "hidden", style: "fill:" + s.color + ";stroke:var(--surface)" }, svg);
      });

      function show(index, pointer) {
        activeIndex = index;
        var cx = x(index);
        crosshair.setAttribute("x1", cx);
        crosshair.setAttribute("x2", cx);
        crosshair.setAttribute("visibility", "visible");
        config.series.forEach(function (s, k) {
          var value = s.values[index];
          markers[k].setAttribute("visibility", value === null ? "hidden" : "visible");
          if (value !== null) {
            markers[k].setAttribute("cx", cx);
            markers[k].setAttribute("cy", y(value));
          }
        });
        tooltip.show(config.labels[index], config.series.map(function (s) {
          return { color: s.color, value: s.values[index] === null ? "–" : config.formatValue(s.values[index]), name: s.name };
        }), pointer ? pointer.x : cx, pointer ? pointer.y : margin.top + 20);
      }
      function hide() {
        activeIndex = null;
        crosshair.setAttribute("visibility", "hidden");
        markers.forEach(function (m) { m.setAttribute("visibility", "hidden"); });
        tooltip.hide();
      }
      var hit = svgEl("rect", { "class": "hit", x: margin.left - 10, y: margin.top, width: plotWidth + 20, height: plotHeight }, svg);
      hit.addEventListener("pointermove", function (event) {
        var position = pointerPosition(event, container);
        var index = Math.round(((position.x - margin.left) / plotWidth) * (count - 1));
        show(Math.max(0, Math.min(count - 1, index)), position);
      });
      hit.addEventListener("pointerleave", hide);
      svg.addEventListener("focus", function () { show(activeIndex === null ? count - 1 : activeIndex); });
      svg.addEventListener("blur", hide);
      svg.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        var next = (activeIndex === null ? count - 1 : activeIndex) + (event.key === "ArrowRight" ? 1 : -1);
        show(Math.max(0, Math.min(count - 1, next)));
      });
    }

    render();
    onResize(container, render);
    return { update: function (next) { config = next; tooltip.hide(); render(); } };
  }

  /* Horizontal bars around zero (above / below a baseline). Returns { update(config) }.
     config = { categories: [{ label, title, value }], formatValue(n), formatTick(n), ariaLabel,
                positiveColor, negativeColor } */
  function divergingBars(container, initialConfig) {
    var config = initialConfig;
    var tooltip = createTooltip(container);

    function render() {
      var previous = container.querySelector("svg");
      if (previous) previous.remove();
      var width = Math.max(container.clientWidth, 260);
      var narrow = width < 520;
      var labelWidth = narrow ? 0 : Math.min(190, Math.round(width * 0.34));
      var rowHeight = narrow ? 46 : 30;
      var barHeight = 14;
      var categories = config.categories;
      var values = categories.map(function (c) { return c.value; });
      // 30% headroom on each side so the value label at a bar's tip stays inside the chart.
      var range = niceRange(Math.min.apply(null, values) * 1.3, Math.max.apply(null, values) * 1.3, narrow ? 3 : 4);
      var plotLeft = narrow ? 34 : labelWidth + 44;
      var plotRight = width - 52;
      var plotBottom = categories.length * rowHeight;
      var height = plotBottom + 28;
      var x = function (v) { return plotLeft + ((v - range.min) / (range.max - range.min)) * (plotRight - plotLeft); };

      var svg = svgEl("svg", { width: width, height: height, viewBox: "0 0 " + width + " " + height,
        role: "img", "aria-label": config.ariaLabel });
      container.insertBefore(svg, container.firstChild);
      for (var tick = range.min; tick <= range.max + range.step / 2; tick += range.step) {
        var gx = Math.round(x(tick)) + 0.5;
        svgEl("line", { "class": Math.abs(tick) < 1e-9 ? "baseline" : "grid", x1: gx, x2: gx, y1: 0, y2: plotBottom }, svg);
        var label = svgEl("text", { "class": "axis-label", x: gx, y: plotBottom + 18, "text-anchor": "middle" }, svg);
        label.textContent = config.formatTick(tick);
      }
      var zero = x(0);
      categories.forEach(function (category, index) {
        var rowTop = index * rowHeight;
        var group = svgEl("g", { tabindex: "0", "aria-label": category.title + ": " + config.formatValue(category.value) }, svg);
        svgEl("rect", { "class": "row-bg", x: -6, y: rowTop + 2, width: width + 12, height: rowHeight - 4, rx: 6 }, group);
        var text = svgEl("text", { "class": "category-label", x: narrow ? 0 : labelWidth, y: narrow ? rowTop + 15 : rowTop + rowHeight / 2 + 4.5,
          "text-anchor": narrow ? "start" : "end" }, group);
        text.textContent = category.label;
        fitText(text, narrow ? width - 8 : labelWidth - 4);
        var barY = narrow ? rowTop + 24 : rowTop + (rowHeight - barHeight) / 2;
        var positive = category.value >= 0;
        var end = x(category.value);
        var path = positive
          ? roundedEndPath(zero, barY, end - zero, barHeight, 4, "right")
          : roundedStartPath(end, barY, zero - end, barHeight, 4);
        svgEl("path", { "class": "mark", d: path,
          style: "fill:" + (positive ? config.positiveColor : config.negativeColor) }, group);
        var valueText = svgEl("text", { "class": "value-label", x: positive ? end + 6 : end - 6, y: barY + barHeight / 2 + 4.5,
          "text-anchor": positive ? "start" : "end" }, group);
        valueText.textContent = config.formatValue(category.value);
        var hit = svgEl("rect", { "class": "hit", x: -6, y: rowTop, width: width + 12, height: rowHeight }, group);
        bindTooltip(group, hit, container, tooltip, function () {
          return { title: category.title, rows: (category.tooltipRows || [{ value: config.formatValue(category.value), name: "" }]) };
        });
      });
    }

    render();
    onResize(container, render);
    return { update: function (next) { config = next; tooltip.hide(); render(); } };
  }

  // Bar growing to the left from the baseline: only its left (data) end is rounded.
  function roundedStartPath(x, y, w, h, r) {
    if (w <= 0) return "";
    r = Math.min(r, w, h / 2);
    return "M" + (x + w) + "," + y + "h" + (-(w - r)) + "a" + r + "," + r + " 0 0 0 " + (-r) + "," + r +
      "v" + (h - 2 * r) + "a" + r + "," + r + " 0 0 0 " + r + "," + r + "h" + (w - r) + "Z";
  }

  window.Charts = {
    stackedBars: stackedBars,
    columnsWithReference: columnsWithReference,
    lineChart: lineChart,
    divergingBars: divergingBars,
    buildTable: buildTable,
    tableToggle: tableToggle
  };
})();
