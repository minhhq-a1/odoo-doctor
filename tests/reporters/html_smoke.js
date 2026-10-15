"use strict";
// Runs the page script from a generated report against a tiny fake DOM and prints
// a JSON summary. Usage: node html_smoke.js report.html
const fs = require("fs");
const vm = require("vm");

class FakeNode {
  constructor(tag) {
    this.tagName = String(tag).toLowerCase();
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this._text = "";
    this.className = "";
    this.hidden = false;
    this.value = "";
    this.checked = false;
    this.parentNode = null;
    const self = this;
    this.classList = {
      add(c) { self.className = (self.className + " " + c).trim(); },
      remove(c) { self.className = self.className.split(/\s+/).filter((x) => x && x !== c).join(" "); },
      contains(c) { return self.className.split(/\s+/).indexOf(c) !== -1; },
      toggle(c) { if (this.contains(c)) this.remove(c); else this.add(c); },
    };
  }
  get firstChild() { return this.children[0] || null; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(" "); }
  set textContent(v) { this.children = []; this._text = String(v); }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === "value") this.value = String(v);
    if (k === "class") this.className = String(v);
  }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  fire(t) { (this.listeners[t] || []).forEach((fn) => fn({ target: this })); }
  scrollIntoView() {}
  walk(fn) { fn(this); this.children.forEach((c) => c.walk(fn)); }
  find(pred) { let hit = null; this.walk((n) => { if (!hit && pred(n)) hit = n; }); return hit; }
  count(pred) { let n = 0; this.walk((x) => { if (pred(x)) n += 1; }); return n; }
}

const html = fs.readFileSync(process.argv[2], "utf8");
const dataText = /<script type="application\/json" id="od-data">([\s\S]*?)<\/script>/.exec(html)[1];
const scriptText = /<script>([\s\S]*?)<\/script>/.exec(html)[1];

const root = new FakeNode("div");
const dataNode = new FakeNode("script");
dataNode.textContent = dataText;
const documentElement = new FakeNode("html");
const byId = { "od-data": dataNode, app: root };
const document = {
  title: "",
  documentElement,
  getElementById: (id) => byId[id] || null,
  createElement: (tag) => new FakeNode(tag),
  createElementNS: (ns, tag) => new FakeNode(tag),
  createTextNode: (s) => { const n = new FakeNode("#text"); n._text = String(s); return n; },
};
const window = { localStorage: { getItem: () => null, setItem: () => {} } };
const t0 = Date.now();
vm.runInNewContext(scriptText, { document, window, console });
const renderMs = Date.now() - t0;

const isFinding = (n) => n.tagName === "details" && n.classList.contains("finding");
const rows = () => root.count(isFinding);
// text is captured before any interaction, so filters below cannot hide rows from it
const out = { rowsDefault: rows(), text: root.textContent, renderMs };

const more = root.find((n) => n.attrs.id === "show-more");
out.moreHiddenDefault = more ? more.hidden : null;
if (more && !more.hidden) { more.fire("click"); out.rowsAfterMore = rows(); out.moreHiddenAfter = more.hidden; }

const low = root.find((n) => n.attrs.id === "show-low");
if (low) { low.checked = true; low.fire("change"); out.rowsWithLow = rows(); }

const moduleSelect = root.find((n) => n.tagName === "select" && n.attrs["data-filter"] === "module");
if (moduleSelect) {
  moduleSelect.value = "n";
  moduleSelect.fire("change");
  out.rowsModuleFilter = rows();
}

const trendSelect = root.find((n) => n.tagName === "select" && n.attrs["aria-label"] === "Trend series");
if (trendSelect) {
  trendSelect.value = "n";
  trendSelect.fire("change");
  out.trendRows = [];
  const table = root.find((n) => n.attrs.id === "trend-table");
  table.walk((n) => { if (n.tagName === "tr") out.trendRows.push(n.children.map((c) => c.textContent)); });
}

out.badElements = root.count((n) => ["img", "iframe", "svg", "script"].indexOf(n.tagName) !== -1 && n.tagName !== "svg");
process.stdout.write(JSON.stringify(out));
