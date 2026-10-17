(function () {
  "use strict";

  var TIERS = ["P0", "P1", "P2", "P3"];
  var PAGE_SIZE = 200;
  var SVG_NS = "http://www.w3.org/2000/svg";

  var data = JSON.parse(document.getElementById("od-data").textContent);
  var report = data.report;
  var meta = data.meta || {};
  var ruleUrls = data.rule_urls || {};
  var truncated = data.truncated || {};
  var root = document.getElementById("app");

  // ---- DOM helpers: text and attributes only, never markup strings ----------
  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (k === "text") node.textContent = v;
        else if (k === "class") node.className = v;
        else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
      });
    }
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, String(attrs[k])); });
    return node;
  }
  function text(s) { return document.createTextNode(String(s)); }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function section(title, kids) {
    return el("section", null, [el("h2", { text: title })].concat(kids));
  }
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  function band(v) {
    if (v >= 90) return "excellent";
    if (v >= 75) return "good";
    if (v >= 50) return "needs-work";
    return "critical";
  }
  function bandLabel(v) {
    return { excellent: "Excellent", good: "Good", "needs-work": "Needs work", critical: "Critical" }[band(v)];
  }

  // ---- data ----------------------------------------------------------------
  var moduleNames = Object.keys(report.modules);
  var findings = [];
  moduleNames.forEach(function (name) {
    (report.modules[name].diagnostics || []).forEach(function (d) { findings.push(d); });
  });
  findings.sort(function (a, b) {
    return cmp(TIERS.indexOf(a.tier), TIERS.indexOf(b.tier)) || cmp(a.file_path, b.file_path) || cmp(a.line, b.line);
  });
  var lowCount = findings.filter(function (d) { return d.confidence === "low"; }).length;
  var findingsTotal = typeof truncated.findings_total === "number" ? truncated.findings_total : findings.length;

  function uniqueSorted(values) {
    var seen = {};
    values.forEach(function (v) { seen[v] = true; });
    return Object.keys(seen).sort();
  }

  // ---- header --------------------------------------------------------------
  function renderHeader() {
    var ps = report.project_score || {};
    var overall = Number(ps.overall);
    var scope = meta.scope || {};
    var lines = [];
    lines.push("Odoo Doctor " + (meta.tool_version || report.version || "") + " · generated " + (meta.generated_at || ""));
    lines.push("Modules: " + (ps.module_count || moduleNames.length) + " · Findings: " + findingsTotal);
    if (meta.branch || meta.commit) lines.push((meta.branch || "unknown branch") + " @ " + (meta.commit || "no commit") + (meta.dirty === true ? " (uncommitted changes)" : ""));

    var themeBtn = el("button", { type: "button", text: "Toggle theme", onclick: toggleTheme });
    var head = el("header", { class: "top" }, [
      el("div", null, [
        el("h1", { text: "Odoo Doctor — " + (meta.project || "report") }),
        el("div", { class: "muted", text: lines.join(" · ") }),
      ]),
      el("div", null, [
        el("div", { class: "score band-" + band(overall) }, [
          el("span", { class: "score-num", text: overall.toFixed(1) }),
          el("span", { class: "score-label", text: ps.label || bandLabel(overall) }),
        ]),
        text(" "),
        themeBtn,
      ]),
    ]);

    var box = el("div", null, [head]);
    if (scope.partial) {
      var what = scope.diff ? "files changed vs " + scope.diff : "modules: " + (scope.modules || []).join(", ");
      box.appendChild(el("div", { class: "banner", text: "Partial scan (" + what + "). The scores cover only the scanned part." }));
    }
    if (meta.baseline) {
      box.appendChild(el("div", { class: "banner", text: "Baseline applied: " + meta.baseline + ". Findings already in the baseline are not shown." }));
    }
    if (truncated.low_findings > 0) {
      box.appendChild(el("div", { class: "banner", text: truncated.low_findings + " low-confidence findings were not embedded because of the file size; use --json for the full list." }));
    }
    return box;
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute("data-theme");
    if (!current) {
      var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      current = dark ? "dark" : "light";
    }
    var next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { window.localStorage.setItem("od-theme", next); } catch (e) { /* storage unavailable */ }
  }
  function restoreTheme() {
    var saved = null;
    try { saved = window.localStorage.getItem("od-theme"); } catch (e) { saved = null; }
    if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved);
  }

  // ---- module x category table ----------------------------------------------
  var categories = [];
  moduleNames.forEach(function (n) {
    (report.modules[n].score.categories || []).forEach(function (c) {
      if (categories.indexOf(c.category) === -1) categories.push(c.category);
    });
  });
  var tableSort = { key: "overall", dir: 1 };

  function scoreOf(name, key) {
    var score = report.modules[name].score;
    if (key === "overall") return score.overall;
    var hit = (score.categories || []).filter(function (c) { return c.category === key; })[0];
    return hit ? hit.score : null;
  }

  function renderTable(box) {
    clear(box);
    var names = moduleNames.slice().sort(function (a, b) {
      var va = scoreOf(a, tableSort.key), vb = scoreOf(b, tableSort.key);
      if (va === null && vb === null) return cmp(a, b);
      if (va === null) return 1;
      if (vb === null) return -1;
      return (cmp(va, vb) * tableSort.dir) || cmp(a, b);
    });
    function th(label, key) {
      return el("th", null, [el("button", {
        class: "link", type: "button", text: label,
        onclick: function () {
          tableSort = { key: key, dir: tableSort.key === key ? -tableSort.dir : 1 };
          renderTable(box);
        },
      })]);
    }
    var head = el("tr", null, [el("th", { text: "Module" })].concat(
      categories.map(function (c) { return th(c, c); }), [th("Overall", "overall")]));
    var rows = names.map(function (name) {
      var cells = [el("td", null, [el("button", {
        class: "link", type: "button", text: name,
        onclick: function () { selectModule(name); },
      })])];
      categories.concat(["overall"]).forEach(function (key) {
        var v = scoreOf(name, key);
        cells.push(v === null
          ? el("td", { class: "cell muted", text: "–" })
          : el("td", { class: "cell band-" + band(v), text: v.toFixed(1) }));
      });
      return el("tr", null, cells);
    });
    box.appendChild(el("div", { class: "scroll" }, [el("table", null, [el("thead", null, [head]), el("tbody", null, rows)])]));
  }

  // ---- fix first -------------------------------------------------------------
  function renderFixFirst() {
    var box = el("div");
    moduleNames.forEach(function (name) {
      var fixes = report.modules[name].fix_priorities || [];
      if (!fixes.length) return;
      var items = fixes.map(function (f) {
        var tail = " · " + f.tier + " · +" + Number(f.score_gain).toFixed(1) + " pts" + (f.fixable ? " · auto-fixable" : "");
        return el("li", null, [el("code", { text: f.file_path + ":" + f.line }), text(" " + f.rule + tail)]);
      });
      box.appendChild(el("details", null, [el("summary", { text: name + " (" + fixes.length + ")" }), el("ol", null, items)]));
    });
    if (!box.firstChild) box.appendChild(el("p", { class: "muted", text: "No ranked fixes." }));
    return box;
  }

  // ---- findings ---------------------------------------------------------------
  var state = { module: "", category: "", tier: "", confidence: "", rule: "", query: "", showLow: false, shown: PAGE_SIZE };
  var controls = {};
  var listBox = el("div");
  var countLine = el("p", { class: "muted" });
  var moreBtn = el("button", { id: "show-more", type: "button", text: "Show more", onclick: function () { state.shown += PAGE_SIZE; renderList(); } });
  var findingsSection = null;

  function visible() {
    var q = state.query.toLowerCase();
    return findings.filter(function (d) {
      if (d.confidence === "low" && !state.showLow) return false;
      if (state.module && d.module !== state.module) return false;
      if (state.category && d.category !== state.category) return false;
      if (state.tier && d.tier !== state.tier) return false;
      if (state.confidence && d.confidence !== state.confidence) return false;
      if (state.rule && d.rule !== state.rule) return false;
      if (q && (d.file_path + " " + d.message + " " + d.title).toLowerCase().indexOf(q) === -1) return false;
      return true;
    });
  }

  function ruleLink(rule) {
    var url = ruleUrls[rule];
    if (typeof url === "string" && url.indexOf("https://") === 0) {
      return el("a", { class: "rule", href: url, rel: "noopener noreferrer", text: rule });
    }
    return el("span", { class: "rule", text: rule });
  }

  function findingRow(d) {
    var summary = el("summary", null, [
      el("code", { class: "loc", text: d.file_path + ":" + d.line }),
      el("span", { class: "pill tier-" + d.tier, text: d.tier }),
      el("span", { class: "pill conf-" + d.confidence, text: d.confidence }),
      ruleLink(d.rule),
      el("span", { text: d.title }),
    ]);
    var body = el("div", { class: "detail" }, [
      el("p", { text: d.message }),
      d.help ? el("p", { class: "muted", text: d.help }) : null,
      el("p", { class: "muted", text: "Module " + d.module + " · " + d.category + " · " + d.severity + " · source " + d.source + " · Odoo " + d.odoo_version }),
    ]);
    return el("details", { class: "finding" }, [summary, body]);
  }

  function renderList() {
    var rows = visible();
    clear(listBox);
    if (!rows.length) {
      listBox.appendChild(el("p", { class: "muted", text: findings.length ? "No findings match the filters." : "No findings." }));
    }
    rows.slice(0, state.shown).forEach(function (d) { listBox.appendChild(findingRow(d)); });
    countLine.textContent = "Showing " + Math.min(state.shown, rows.length) + " of " + rows.length + " matching (" + findingsTotal + " findings in this report)";
    moreBtn.hidden = rows.length <= state.shown;
  }

  function makeSelect(key, label, values) {
    var select = el("select", { "data-filter": key, "aria-label": label }, [el("option", { value: "", text: label + ": all" })]
      .concat(values.map(function (v) { return el("option", { value: v, text: v }); })));
    select.addEventListener("change", function () {
      state[key] = select.value;
      if (key === "confidence" && select.value === "low") {
        state.showLow = true;
        controls.low.checked = true;
      }
      state.shown = PAGE_SIZE;
      renderList();
    });
    controls[key] = select;
    return select;
  }

  function selectModule(name) {
    state.module = name;
    state.shown = PAGE_SIZE;
    controls.module.value = name;
    renderList();
    if (findingsSection && findingsSection.scrollIntoView) findingsSection.scrollIntoView();
  }

  function renderFindings() {
    var low = el("input", { id: "show-low", type: "checkbox" });
    low.addEventListener("change", function () {
      state.showLow = low.checked;
      state.shown = PAGE_SIZE;
      renderList();
    });
    controls.low = low;
    var search = el("input", { type: "search", placeholder: "Search path or message", "aria-label": "Search path or message" });
    search.addEventListener("input", function () {
      state.query = search.value;
      state.shown = PAGE_SIZE;
      renderList();
    });
    var bar = el("div", { class: "controls" }, [
      makeSelect("module", "Module", moduleNames.slice().sort()),
      makeSelect("category", "Category", uniqueSorted(findings.map(function (d) { return d.category; }))),
      makeSelect("tier", "Tier", TIERS),
      makeSelect("confidence", "Confidence", ["high", "medium", "low"]),
      makeSelect("rule", "Rule", uniqueSorted(findings.map(function (d) { return d.rule; }))),
      search,
      el("label", null, [low, text("Show low-confidence findings (" + lowCount + ")")]),
    ]);
    renderList();
    findingsSection = section("Findings", [bar, countLine, listBox, moreBtn]);
    return findingsSection;
  }

  // ---- suppression ---------------------------------------------------------------
  function renderSuppression() {
    var totals = {};
    moduleNames.forEach(function (n) {
      var stats = report.modules[n].suppression_stats || {};
      Object.keys(stats).forEach(function (rule) {
        var t = totals[rule] || (totals[rule] = { surfaced: 0, inline: 0, ignore_rule: 0, severity_off: 0 });
        Object.keys(t).forEach(function (k) { t[k] += Number(stats[rule][k] || 0); });
      });
    });
    var rules = Object.keys(totals).sort(function (a, b) {
      function dropped(r) { return totals[r].inline + totals[r].ignore_rule + totals[r].severity_off; }
      return (dropped(b) - dropped(a)) || cmp(a, b);
    });
    if (!rules.length) {
      var scope = meta.scope || {};
      return el("p", { class: "muted", text: scope.diff ? "No suppression data for --diff scans." : "No suppression data." });
    }
    var rows = rules.map(function (r) {
      var t = totals[r];
      return el("tr", null, [el("td", { text: r }), el("td", { class: "cell", text: String(t.surfaced) }), el("td", { class: "cell", text: String(t.inline) }),
        el("td", { class: "cell", text: String(t.ignore_rule) }), el("td", { class: "cell", text: String(t.severity_off) })]);
    });
    var head = el("tr", null, ["Rule", "Shown", "Inline disable", "[ignore] rules", "Severity off"].map(function (h) { return el("th", { text: h }); }));
    return el("div", { class: "scroll" }, [el("table", null, [el("thead", null, [head]), el("tbody", null, rows)])]);
  }

  // ---- trend ----------------------------------------------------------------------
  function trendValue(r, name) {
    if (!name) return r.project;
    return typeof r.modules[name] === "number" ? r.modules[name] : null;
  }

  function buildTrendTable(records, name) {
    var head = el("tr", null, ["Time", "Branch", "Commit", "Score (" + (name || "project") + ")"].map(function (h) {
      return el("th", { text: h });
    }));
    var rows = records.map(function (r) {
      var v = trendValue(r, name);
      return el("tr", null, [
        el("td", { text: String(r.timestamp) }),
        el("td", { text: r.branch || "" }),
        el("td", { text: r.commit ? String(r.commit).slice(0, 7) : "" }),
        el("td", { class: "cell", text: v === null ? "–" : v.toFixed(1) }),
      ]);
    });
    return el("table", { id: "trend-table" }, [el("thead", null, [head]), el("tbody", null, rows)]);
  }

  function buildChart(records, name) {
    var W = 640, H = 220, L = 36, R = 12, T = 12, B = 24;
    var n = records.length;
    function x(i) { return L + (W - L - R) * (n === 1 ? 0 : i / (n - 1)); }
    function y(v) { return T + (H - T - B) * (1 - v / 100); }
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Score trend", class: "trend" });
    [0, 25, 50, 75, 100].forEach(function (v) {
      svg.appendChild(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid" }));
      var t = svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end", class: "tick" });
      t.textContent = String(v);
      svg.appendChild(t);
    });
    var d = "";
    var pen = false;
    records.forEach(function (r, i) {
      var v = trendValue(r, name);
      if (v === null) { pen = false; return; }
      d += (pen ? " L " : " M ") + x(i).toFixed(1) + " " + y(v).toFixed(1);
      pen = true;
    });
    svg.appendChild(svgEl("path", { d: d.trim(), class: "line" }));
    records.forEach(function (r, i) {
      var v = trendValue(r, name);
      if (v === null) return;
      var dot = svgEl("circle", { cx: x(i).toFixed(1), cy: y(v).toFixed(1), r: 3.5, class: "dot" });
      var tip = svgEl("title");
      tip.textContent = (r.branch || "unknown branch") + " @ " + (r.commit ? String(r.commit).slice(0, 7) : "no commit") + " · " + r.timestamp + " · " + v.toFixed(1);
      dot.appendChild(tip);
      svg.appendChild(dot);
    });
    return svg;
  }

  function renderTrend() {
    var records = data.history;
    if (!records) return null;
    var box = el("div");
    if (records.length < 2) {
      box.appendChild(el("p", { class: "muted", text: "At least 2 scans are needed for a trend." }));
    } else {
      var select = el("select", { "aria-label": "Trend series" }, [el("option", { value: "", text: "Whole project" })]
        .concat(moduleNames.map(function (n) { return el("option", { value: n, text: n }); })));
      var chart = el("div", { class: "chart" });
      var tableBox = el("div", { class: "scroll" });
      var draw = function () {
        clear(chart);
        chart.appendChild(buildChart(records, select.value));
        clear(tableBox);
        tableBox.appendChild(buildTrendTable(records, select.value));
      };
      select.addEventListener("change", draw);
      draw();
      box.appendChild(select);
      box.appendChild(chart);
      box.appendChild(el("details", null, [el("summary", { text: "Data table" }), tableBox]));
    }
    box.appendChild(el("p", { class: "muted", text: "May span several branches." }));
    if (data.history_dropped_schema > 0) {
      box.appendChild(el("p", { class: "muted", text: data.history_dropped_schema + " older scan(s) with a different score schema are not shown." }));
    }
    if (data.history_skipped > 0) {
      box.appendChild(el("p", { class: "muted", text: data.history_skipped + " unreadable history line(s) were skipped." }));
    }
    return box;
  }

  // ---- page ------------------------------------------------------------------------
  function renderFooter() {
    var links = data.links || {};
    var kids = [text("Generated by Odoo Doctor " + (meta.tool_version || "") + ". This file is self-contained: it makes no network requests.")];
    [["repo", "Project"], ["rules", "Rule reference"]].forEach(function (pair) {
      var url = links[pair[0]];
      if (typeof url === "string" && url.indexOf("https://") === 0) {
        kids.push(text(" · "));
        kids.push(el("a", { href: url, rel: "noopener noreferrer", text: pair[1] }));
      }
    });
    return el("footer", null, kids);
  }

  restoreTheme();
  document.title = "Odoo Doctor — " + (meta.project || "report");
  var tableBox = el("div");
  renderTable(tableBox);
  root.appendChild(renderHeader());
  root.appendChild(section("Modules", [tableBox]));
  root.appendChild(section("Fix first", [renderFixFirst()]));
  root.appendChild(renderFindings());
  root.appendChild(section("Suppression", [renderSuppression()]));
  var trend = renderTrend();
  if (trend) root.appendChild(section("Score trend", [trend]));
  root.appendChild(renderFooter());
})();
