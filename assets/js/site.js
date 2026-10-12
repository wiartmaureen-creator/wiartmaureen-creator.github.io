// Shared page behaviour: mobile menu, e-mail links and footer year.
(function () {
  "use strict";

  var DESKTOP_QUERY = "(min-width: 960px)";

  // The mobile menu opens under the navigation bar and closes on link click,
  // on Escape, or when the window becomes wide enough for the full navigation.
  function setupMobileMenu() {
    var toggle = document.querySelector("[data-menu-toggle]");
    var menu = document.querySelector("[data-mobile-menu]");
    if (!toggle || !menu) return;

    function setOpen(open) {
      menu.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
    }

    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    menu.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () { setOpen(false); });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        toggle.focus();
      }
    });
    if (window.matchMedia) {
      var desktop = window.matchMedia(DESKTOP_QUERY);
      var onChange = function () { if (desktop.matches) setOpen(false); };
      if (desktop.addEventListener) desktop.addEventListener("change", onChange);
      else if (desktop.addListener) desktop.addListener(onChange);
    }
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

  setupMobileMenu();
  setupEmailLinks();
  setupYear();
})();
