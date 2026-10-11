// Shared page behaviour: theme toggle, e-mail link and footer year.
(function () {
  "use strict";

  var STORAGE_KEY = "portfolio-theme";
  var root = document.documentElement;

  function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }

  function saveTheme(theme) {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (error) { /* not persisted */ }
  }

  function setupThemeToggle() {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        var current = root.getAttribute("data-theme") || systemTheme();
        var next = current === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        saveTheme(next);
      });
    });
  }

  // The address is assembled here so it is not sitting in the HTML for scrapers.
  function setupEmailLinks() {
    document.querySelectorAll("[data-email-user]").forEach(function (link) {
      var address = link.getAttribute("data-email-user") + "@" + link.getAttribute("data-email-domain");
      link.setAttribute("href", "mailto:" + address);
      link.setAttribute("title", address);
    });
  }

  function setupYear() {
    document.querySelectorAll("[data-current-year]").forEach(function (node) {
      node.textContent = String(new Date().getFullYear());
    });
  }

  setupThemeToggle();
  setupEmailLinks();
  setupYear();
})();
