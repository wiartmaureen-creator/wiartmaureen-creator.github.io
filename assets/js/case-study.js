// Helpers shared by every case-study page: number formats, small DOM builders,
// accessible code tabs and syntax highlighting. Each page calls CaseStudy.init().
(function () {
  "use strict";

  var integer = new Intl.NumberFormat("en-US");
  var decimal = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function chips(labels) {
    var list = el("span", "chip-list");
    labels.forEach(function (label) { list.appendChild(el("span", "chip", label)); });
    return list;
  }

  function setText(selector, text) {
    var node = document.querySelector(selector);
    if (node) node.textContent = text;
  }

  function euros(value, digits) {
    var sign = value < 0 ? "−" : "";
    var abs = Math.abs(value);
    var body = digits === 0 ? integer.format(Math.round(abs)) : decimal.format(abs);
    return sign + "€" + body;
  }

  function percent(share, digits) {
    return (share * 100).toFixed(digits === undefined ? 1 : digits) + "%";
  }

  function setupTabs() {
    document.querySelectorAll("[data-tabs]").forEach(function (group) {
      var tabs = Array.prototype.slice.call(group.querySelectorAll('[role="tab"]'));
      function select(tab, focus) {
        tabs.forEach(function (other) {
          var selected = other === tab;
          other.setAttribute("aria-selected", String(selected));
          other.tabIndex = selected ? 0 : -1;
          document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
        });
        if (focus) tab.focus();
      }
      tabs.forEach(function (tab, index) {
        tab.addEventListener("click", function () { select(tab, false); });
        tab.addEventListener("keydown", function (event) {
          if (event.key === "ArrowRight") select(tabs[(index + 1) % tabs.length], true);
          if (event.key === "ArrowLeft") select(tabs[(index - 1 + tabs.length) % tabs.length], true);
        });
      });
    });
  }

  function highlightCode() {
    if (!window.hljs) return; // plain text is fine if the CDN is unreachable
    document.querySelectorAll("pre code").forEach(function (block) {
      var language = (block.className.match(/language-(\S+)/) || [])[1];
      if (language === "plaintext" || language === "excel") return;
      if (language && !window.hljs.getLanguage(language)) return;
      window.hljs.highlightElement(block);
    });
  }

  window.CaseStudy = {
    integer: integer,
    decimal: decimal,
    el: el,
    chips: chips,
    setText: setText,
    euros: euros,
    percent: percent,
    init: function () {
      setupTabs();
      highlightCode();
    }
  };
})();
