// Home page: real code outputs in the terminals, and the project tabs.
(function () {
  "use strict";

  // --- Code and the output it really produced (assets/data/code_outputs.js) -------------
  var outputs = window.CODE_OUTPUTS;
  if (outputs) {
    document.querySelectorAll("[data-code]").forEach(function (node) {
      var item = outputs[node.getAttribute("data-code")];
      if (item) node.textContent = item.code;
    });
    document.querySelectorAll("[data-output]").forEach(function (node) {
      var item = outputs[node.getAttribute("data-output")];
      if (item) node.textContent = item.output;
    });
    document.querySelectorAll("[data-source]").forEach(function (node) {
      var item = outputs[node.getAttribute("data-source")];
      if (item) node.textContent = item.source + " · captured on " + outputs.captured_on;
    });
  }
  if (window.hljs) {
    document.querySelectorAll("pre code[data-code]").forEach(function (block) {
      var language = (block.className.match(/language-(\S+)/) || [])[1];
      if (language && language !== "plaintext" && window.hljs.getLanguage(language)) window.hljs.highlightElement(block);
    });
  }

  // --- Project tabs ---------------------------------------------------------------------------
  var root = document.querySelector("[data-project-tabs]");
  if (!root) return;
  var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
  var section = document.getElementById("projects");

  function indexOfPanel(panelId) {
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].getAttribute("aria-controls") === panelId) return i;
    }
    return -1;
  }

  function current() {
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].getAttribute("aria-selected") === "true") return i;
    }
    return 0;
  }

  function select(index, options) {
    options = options || {};
    index = (index + tabs.length) % tabs.length;
    tabs.forEach(function (tab, i) {
      var selected = i === index;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
    });
    var active = tabs[index];
    // Keep the active tab visible in the scrolling bar without moving the page.
    var bar = active.parentNode;
    var left = active.offsetLeft - bar.offsetLeft;
    if (left < bar.scrollLeft || left + active.offsetWidth > bar.scrollLeft + bar.clientWidth) {
      bar.scrollTo({ left: left - 8, behavior: "smooth" });
    }
    if (options.focus) active.focus();
    if (options.scroll) section.scrollIntoView({ behavior: "smooth", block: "start" });
    if (options.updateHash !== false) {
      try { history.replaceState(null, "", "#" + active.getAttribute("aria-controls")); } catch (error) { /* file:// */ }
    }
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener("click", function () { select(i); });
    tab.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight") { event.preventDefault(); select(i + 1, { focus: true }); }
      if (event.key === "ArrowLeft") { event.preventDefault(); select(i - 1, { focus: true }); }
      if (event.key === "Home") { event.preventDefault(); select(0, { focus: true }); }
      if (event.key === "End") { event.preventDefault(); select(tabs.length - 1, { focus: true }); }
    });
  });

  root.querySelectorAll("[data-tab-step]").forEach(function (button) {
    button.addEventListener("click", function () {
      var inPanel = button.closest('[role="tabpanel"]') !== null;
      select(current() + Number(button.getAttribute("data-tab-step")), { scroll: inPanel });
    });
  });

  // Any link to a project panel (utility bar, tool strip, cards) opens that tab.
  document.querySelectorAll('a[href^="#project-"]').forEach(function (link) {
    link.addEventListener("click", function (event) {
      var index = indexOfPanel(link.getAttribute("href").slice(1));
      if (index < 0) return;
      event.preventDefault();
      select(index, { scroll: true });
    });
  });

  function fromHash() {
    var index = indexOfPanel(location.hash.slice(1));
    if (index >= 0) select(index, { scroll: true, updateHash: false });
  }
  window.addEventListener("hashchange", fromHash);
  fromHash();
})();
