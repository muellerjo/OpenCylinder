// OpenCylinder Manager — tiny progressive enhancements (CSP: no inline scripts).
(function () {
  // CSRF token for every htmx request
  document.body.addEventListener("htmx:configRequest", function (e) {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) e.detail.headers["X-CSRF-Token"] = meta.content;
  });

  // Never fail silently: show a message when an htmx request errors or the
  // server cannot be reached (htmx does not swap error responses by itself).
  function showError(msg) {
    var main = document.querySelector("main") || document.body;
    var box = document.createElement("div");
    box.className = "flash error";
    box.setAttribute("role", "alert");
    box.textContent = msg;
    main.insertBefore(box, main.firstChild);
    window.scrollTo(0, 0);
  }
  document.body.addEventListener("htmx:responseError", function (e) {
    var x = e.detail.xhr;
    showError("Request failed (HTTP " + x.status + "). " + (x.status === 403
      ? "Not allowed or the page is outdated — reload the page." : "Reload the page and try again."));
  });
  document.body.addEventListener("htmx:sendError", function () {
    showError("The manager is not reachable — is it still running (python3 manager/app.py)?");
  });

  // <form data-confirm="..."> asks before submitting (works with and without htmx)
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);

  // <select data-nav> navigates to the selected option's value
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("select[data-nav]") && e.target.value) {
      window.location = e.target.value;
    }
  });

  // <button data-copy="#id"> copies the text of an element
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-copy]");
    if (!b) return;
    var el = document.querySelector(b.getAttribute("data-copy"));
    if (el && navigator.clipboard) {
      navigator.clipboard.writeText(el.innerText).then(function () {
        var t = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = t; }, 1200);
      });
    }
  });
})();
