// Progressive enhancement ONLY: client-side show/hide filtering for the
// Assumptions table. No scoring, no data fetching, no recomputation — the
// pages are fully readable with JavaScript disabled.
(function () {
  "use strict";
  var opp = document.getElementById("f-opp");
  var status = document.getElementById("f-status");
  var table = document.getElementById("atable");
  if (!table || !(opp || status)) return;

  function apply() {
    var o = opp ? opp.value : "";
    var s = status ? status.value : "";
    var rows = table.querySelectorAll("tbody tr.arow");
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (!o || r.getAttribute("data-opp") === o) &&
               (!s || r.getAttribute("data-status") === s);
      r.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    var note = document.getElementById("filter-count");
    if (note) note.textContent = shown + " row(s) shown";
  }
  if (opp) opp.addEventListener("change", apply);
  if (status) status.addEventListener("change", apply);
})();
