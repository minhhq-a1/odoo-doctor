(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("od-data").textContent);
  var root = document.getElementById("app");
  var h = document.createElement("h1");
  h.textContent = "Odoo Doctor " + data.report.project_score.overall;
  root.appendChild(h);
})();
