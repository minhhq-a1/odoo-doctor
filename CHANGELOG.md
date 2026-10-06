# Changelog

All notable changes to Odoo Doctor are documented here.

---

## [Unreleased]

### Changed

- Plugin loading checks the declared API version strictly: `ODOO_DOCTOR_PLUGIN_API` must be
  an integer equal to `PLUGIN_API_VERSION`. `True` and `1.0` used to pass (`True == 1`) and a
  string was refused with a confusing message; now all of them are refused with
  "must be an integer". Plugins that omit the declaration still load, but print a warning
  naming the plugin (it was silent). `PLUGIN_API_VERSION` stays 1 and `plugin_api` is unchanged.

### Fixed

- **A model declared in several modules lost its fields and its owner.** `_name = 'x'` together
  with `_inherit = ['x', mixin]` (how Odoo core adds a mixin to an existing model, e.g. `pos_hr` on
  `hr.employee`, `sale` on `account.move`) extends `x`, but the project graph let the last module
  parsed replace the original definition. The resolver then saw `hr.employee` with 0 fields and
  the wrong owner module. The declarations are now merged (the defining module is the owner, its
  field attributes win, extensions add theirs), independent of module order. On a scan of Odoo
  19.0 community (660 modules) this removes 1,308 `view-field-not-in-model`, 185
  `manifest-missing-dependency`, 79 `button-method-not-found` and 8
  `monetary-missing-currency-field` false positives (18,740 -> 17,244 findings). Some rules now
  see fields they could not see before, so a few findings appear that were hidden (for example
  `compute-missing-depends`).

- **Fields of type `Image`, `Json`, `Many2oneReference`, `Properties` and `PropertiesDefinition`
  were never recorded** (the parser only knew 15 field classes), so every view that showed one
  (`image_1920`, `alerts`, `lot_properties`, ...) was reported as referencing an unknown field.
  Any `fields.<Class>(...)` is now a field, which also covers classes other modules add (for
  example `fields.Serialized`). Odoo 19.0 community: 195 -> 65 `view-field-not-in-model`.

- **Views: three more false positives in `view-field-not-in-model` / `button-method-not-found`.**
  (1) Fields declared with a type annotation (`parent_id: Cat = fields.Many2one(...)`, used in
  Odoo 19 core) were not recorded. (2) What an inherited view's `<xpath>` inserts into an x2many's
  inline subview (`//field[@name='order_line']//list//field[...]`, `//page[...]//list/field[...]`)
  was attributed to the view's own model instead of the comodel. (3) A `<field/button ...
  position="...">` only locates a node of the parent view (which may be inside a subview), so it
  is not a reference. Odoo 19.0 community: `view-field-not-in-model` 65 -> 16.

- **Model ownership inside one module, and BaseModel methods.** A module that both defines a model
  (`_name = 'res.users'` in one file) and extends it (`_inherit = 'res.users'` in others) was merged
  into an entry that no longer counted as the definition, so the first extending module (`bus`,
  `point_of_sale`) became the "owner" and every module extending `res.users` or `res.currency` was
  told to depend on it. `ModelInfo.defines` now records whether a class defines the model, and
  the merge no longer depends on file order (the `_inherit` list is kept in a stable order too).
  Methods every model gets from `BaseModel` (`unlink`, `action_archive`, `action_unarchive`,
  `write`, ...) now resolve, so a button calling them is no longer "not found".
- **Refs inserted next to a subview node.** An inherited view's `<xpath expr="//field[@name='X']">`
  where `X` is not a field of the view's model located a node of an inline subview, so the
  fields and buttons it inserts belong to that subview's model; `view-field-not-in-model` and
  `button-method-not-found` no longer check them against the parent model.
  Odoo 19.0 community, with the fixes above: `manifest-missing-dependency` 204 -> 2,
  `view-field-not-in-model` 1,503 -> 7, `removed-model-still-referenced` 172 -> 14.

- **`duplicate-xml-id`: markup ids were counted as XML ids.** Every element with an `id` attribute
  was collected, including `<div id>`, `<span id>` and `<setting id>` inside templates and view
  arches (and `<delete id>`, which removes a record). Only data-level elements (children of
  `<odoo>`/`<data>`, nested `<menuitem>`s) define an XML id now. Odoo 19.0: 234 -> 51.
- **`missing-xml-ref`: implicit ids and report models.** `<module>.field_<model>__<field>` (the id
  Odoo registers for every field, `create_uid` included) now resolves, and classes deriving from
  `models.BaseModel` (SQL-view / report models) are models, which also resolves their
  `model_<name>` ids. Odoo 19.0: 44 -> 6.
- **`deprecated-api-usage`.** `self.pool['model']` is the registry (a model class, used for
  `isinstance` checks in Odoo 19 core) and `Registry.get()` is current; only the old calling
  convention `self.pool.get('model').method(cr, uid, ...)` is reported. `from openerp` in
  `migrations/<version>/` for a version before Odoo 10 ran on databases of that era and is not
  reported. Odoo 19.0: 31 -> 0.

- **`compute-missing-depends`: a compute's own result is not an input.** `team.x = ...` followed by
  `team.x > limit` read the field back and was reported as an undeclared dependency; fields the
  method assigns are now left out. Odoo 19.0: 322 of 936 findings were this (the other 614 read
  fields that really are not declared).

- **`raw-sql-string-interpolation` no longer reports code no request can reach.** Test code
  (`tests/`) and `migrations/` are skipped, as other rules already do, and so are the install-time
  hooks `init` / `_auto_init` that take only `self`, where Odoo core creates SQL views from
  `self._table` and `self._select()`. Odoo 19.0: 15 of the 51 findings were in tests, 7 in `init`
  and 2 in migrations.

- **`missing-access-csv` asked for ACL rows for models a module only extends.** `_name = 'x'` with
  `_inherit = ['x', mixin]` extends `x` (the model's own module owns its ACL); the rule now looks at
  `ModelInfo.defines`. Odoo 19.0: 47 -> 13.
- **`missing-ondelete` flagged Many2one fields that have no column.** `ondelete` configures a foreign
  key; a `related=` or `compute=` Many2one without `store=True` has none. `FieldInfo.store` now
  follows Odoo (computed and related fields are not stored unless asked) and `FieldInfo.related`
  is recorded. Odoo 19.0: 283 of 1,431 findings.
- **Golden corpus case `odoo19_patterns`**: a model defined in one addon and extended with a mixin in
  another (`_name` + `_inherit` listing itself), annotated / `Image` / `Json` fields, a `<groupby>`,
  an xpath into an inline subview, a locator, `unlink` from a button, HTML ids in a template and a
  `field_<model>__<field>` ref. Against `main` before these fixes it produced six false positives.

### Added

- **`odoo-doctor rules new <rule-name> [--out DIR]`** scaffolds a third-party rule pack: a
  `pyproject.toml` with the `odoo_doctor.rules` entry point, a starter rule that imports only
  from `odoo_doctor.plugin_api`, tests that run without installing anything, a README and a
  `.gitignore`. It rejects names that are not kebab-case or already exist as built-in rules and
  never overwrites a directory (exit 3). `docs/custom-rules.md` starts with this quick start.
- The VS Code extension has an icon (`editors/vscode/images/icon.png`, 512 px, transparent
  corners); the SVG wrapper stays in the repo and is not shipped in the `.vsix`.
- Contract tests for the plugin loader: discovery through real `importlib.metadata`
  entry points (a compatible and a future-version plugin), the mismatch message, and a check
  that `docs/custom-rules.md` mentions every name `plugin_api` exports. `docs/custom-rules.md`
  and `docs/stability.md` describe the versioning policy.
- **CI templates for GitLab CI and Bitbucket Pipelines** (`ci-templates/gitlab-ci.yml`,
  `ci-templates/bitbucket-pipelines.yml`): merge/pull request pipelines scan only the changed
  files (against the merge base), other pipelines scan everything; `ODOO_DOCTOR_*` variables set
  the version, path, Odoo version, `--fail-on`, `--min-score` and an advisory mode; the JSON report
  is kept as an artifact. `tests/test_ci_templates.py` checks the YAML, that every flag exists on
  `scan`, and runs the script in a throwaway git repo with a real `origin` (branch pipeline, MR that
  changes a clean addon, MR that changes a bad one, advisory mode). The README documents both.
- **Language server: hover.** Hovering a flagged line shows the rule's explanation from
  `RULE_DOCS` (detects, why, fix, bad/good example, docs link), not repeating the message the
  editor already shows. Findings from Ruff / Pylint-Odoo show their own title and help. A line
  edited since the last save gets no hover (its finding would describe old code). The language
  server and extension stay experimental and outside the stability contract.
- **CI:** the VS Code extension is built and packaged on Linux and Windows (it was only tried on
  macOS), and the language server tests (`tests/lsp`) run on Windows, where file URIs and paths
  differ. `tests/test_ci_workflow.py` keeps both in the workflow.

---

## [0.7.1] — 2026-10-06

A patch release: a restored rule, fixes found by scanning a real Odoo 19 workspace, and
the install path for the language server and VS Code extension. Rule IDs, CLI flags and
JSON keys are unchanged (see `docs/stability.md`); the new rule only adds findings.

### Changed

- The VS Code extension is published on the Marketplace as `MinhHong.odoo-doctor` (preview, 0.7.0):
  install it from the Extensions view or with `code --install-extension MinhHong.odoo-doctor`
  (the server still needs the `lsp` extra). The README and `docs/lsp.md` say so.
- The language server tells you when a scan found no addon at all (a warning in the
  editor), instead of staying silent: a folder whose addons sit deeper than `addons_paths`
  looks exactly like a clean project. `docs/lsp.md` explains how to fix it.
- Install docs for the language server (`docs/lsp.md`, extension README, README) recommend
  `uv tool install` / `pipx` and explain the macOS case where the Xcode `pip3` is Python 3.9
  (Odoo Doctor needs 3.10+) and VS Code started from the Dock cannot see `~/.local/bin`.
- The VS Code extension is bundled with esbuild: the `.vsix` goes from 358 files (583 KB) to
  6 files (140 KB), which also makes it start faster. `npm run compile` now type-checks with
  `tsc` and bundles; `vscode-languageclient` moved to `devDependencies` because it is part
  of the bundle. Checked by running the packaged extension in VS Code 1.140.

### Added

- **Rule `unsafe-template-render`** (Security, P1, medium confidence, Odoo 14+): flags QWeb
  `t-raw`, which renders a value without HTML-escaping (stored or reflected XSS), and ignores
  the safe `t-raw="0"` body idiom of `t-call`. Native rules: 36 -> 37.
  - The rule first shipped in the `v0.3.1` tag, but that line never reached `main`, so
    0.4.0 to 0.7.0 did not have it. It is ported here with its original tests, a rules-docs
    entry, an effort estimate and a golden-corpus case. Its ID is now covered by the
    stability contract.

### Fixed

- `asset-bundle-missing` crashed (`'tuple' object has no attribute 'startswith'`) on manifests
  whose `assets` use Odoo's directive entries such as `('include', ...)`, `('remove', ...)`,
  `('prepend', path)` or `('after', target, path)`, so the rule silently skipped those addons.
  It now checks the file a directive adds (`prepend`, `append`, `before`, `after`, `replace`)
  and ignores `include`, `remove` and entries it cannot read.

---

## [0.7.0] — 2026-10-05

Theme: trust and reach. Tell users which rules are noisy in their own repo, state what is
safe to rely on, and show findings in the editor. All three are local: no hosted service,
no LLM, no new scoring.

### Added

- **Suppression analytics.** `odoo-doctor rules stats [--path DIR] [--cache] [--json]`
  counts, per rule, the findings still shown and the findings the user switched off
  through `# odoo-doctor: disable` (inline, including file-wide), `[ignore] rules` and
  `[severity] = "off"`, and flags rules where at least half of at least 10 findings were
  suppressed. A rule mostly silenced inline gets a suggestion to lower it to `info`;
  rules disabled through config are flagged but get no advice. `[ignore] files/modules`
  and the baseline are not counted.
  - The JSON report gains `modules.<name>.suppression_stats` (additive; `schema_version`
    and `score_schema_version` are unchanged). `scan` prints one hint line when a rule is
    both noisy and actionable.
  - `core/pipeline.py::run_pipeline_with_stats` collects the counts; `run_pipeline` is
    unchanged. The scan cache stores them too, so `CACHE_VERSION` is now 2 (older cache
    files are ignored once). `--diff` scans do not collect stats.
- **Stability contract.** [`docs/stability.md`](docs/stability.md) states what is public
  and what is not (CLI flags and exit codes, JSON report keys, `rules stats --json`,
  history and baseline files, SARIF, rule IDs, inline-suppression syntax, config keys,
  `odoo_doctor.plugin_api`) and the policy for changing it: additions are free, removals
  go through at least one minor release marked `### Deprecated`, rule IDs are permanent.
  `tests/test_stability_contract.py` fences it with subset checks, so adding names never
  fails it and removing or renaming one does. No behaviour change.
- **Language server and VS Code extension (experimental).** `odoo-doctor lsp` serves LSP
  over stdio (pygls 2.x, optional extra `pip install 'odoo-doctor[lsp]'`, also part of
  `dev`; without it the command exits 3 with a hint). It publishes every finding of the
  workspace folder as diagnostics (rule name as code, link to the rule docs) and offers
  quick fixes: the deterministic auto-fix when the rule has one, disable on this line,
  disable in this file, and disable in `odoo-doctor.toml`. Findings refresh on startup, on
  save and on the `odooDoctor.rescan` command; a scan covers the whole folder because
  cross-module rules need every addon, scans never overlap and saves during a scan are
  merged. Settings come from `odoo-doctor.toml`.
  - Code: `odoo_doctor/lsp/` (`convert`, `actions`, `engine` are pure; `server` is the
    pygls glue), covered by unit tests and an end-to-end JSON-RPC test.
  - `editors/vscode/` is a TypeScript extension (`odooDoctor.enable`, `odooDoctor.path`,
    commands to rescan and restart). Build a `.vsix` with `npm run package`; it is not
    published to the Marketplace. CI compiles and packages it.
  - Safety: quick fixes that depend on the finding's line are withheld while the buffer has
    unsaved changes around it; *disable on this line* is only offered where a comment is
    valid (not inside strings, after a backslash or inside XML tags), keeps CRLF files
    CRLF, and extends an existing `disable=` comment instead of stacking another. The
    extension is off in untrusted workspaces. Folders opened through a symlink,
    nested folders and added/removed folders are handled.
  - Docs in [`docs/lsp.md`](docs/lsp.md) (VS Code, Neovim, Helix). The language server is
    outside the stability contract until a later release lists it.

### Changed

- Internal: the code base now follows the ruff 0.16 default rule set (CI pins `ruff>=0.16,<0.17`)
  instead of the old `E4,E7,E9,F` selection. No behaviour change: `scan` and `rules` output is
  identical. The side-effect imports that register rules stay in `isort: off` blocks because
  registration order is the order of `rules list`; `tests/test_registration_order.py` guards it.

### Roadmap decisions (explicit close-or-defer)

Closed in 0.7.0: suppression analytics (local, per repo), the stability contract and
the language server with a VS Code extension (experimental). The cache is now version 2
(see above), so the first `--cache` scan after upgrading is a full scan.

Deferred, with owner version:

| Item | Target | Reason |
|------|--------|--------|
| Language server follow-ups: hover, per-keystroke analysis, Marketplace publishing, listing it in the stability contract | 0.8.0 (candidate) | first release is deliberately small; needs real-world use first |
| Aggregating suppression data across users; confidence calibration from a labelled corpus and a feedback channel | not scheduled | needs the remote score service decision and a labelled corpus (9 cases today) |
| Percentile score vs. other repos | not scheduled | needs an anonymised dataset and the remote service decision |
| LLM-assisted fix suggestions | not scheduled | needs an opt-in / privacy design (which model, cost, does source leave the machine) |
| Hosted remote score service, auth, server-side trends; Odoo in-app reporting module | not scheduled | needs a product decision (open source or hosted) |
| Inter-procedural / type-aware taint | not scheduled | unchanged from 0.6.0 |
| Scan daemon / persistent cache | not scheduled | scaling is linear; the language server rescans per save at about 0.06 s per addon |
| Abandoned-dependency warning | not scheduled | optional in 0.6.0, still no demand |
| LTS line, security audit, performance SLA, migration guide | toward 1.0 | the stability contract is the first step |
| Rule-alias mechanism; warning on unknown config keys | when first needed | the policy already requires an alias on a rename; unknown keys are documented as ignored |

---

## [0.6.0] — 2026-10-05

Theme: trust the findings (golden corpus, taint analysis, fix ROI) and cover
multi-company / multi-currency. Also false-positive fixes found by scanning real
OCA/custom addons (`queue_job`, `purchase_request` and others): 229 -> 188
findings on one such repo.

### Performance

- **Scans are about 2x faster** (0.93s -> 0.48s on 14 addons / 169 files / 18.8k
  lines; same findings, same order, same scores). Cause, found by profiling: every
  file-based rule read and `ast.parse`d every file itself, about 11 parses per file.
  - `core/source.py` gains `parse_python(path)`: a small (16 entries) cache keyed
    by path and `(mtime_ns, size)`, shared by `read_source`, so a rewritten file is
    never served stale. Parses per scan: 1316 -> 277.
  - The scanner runs file-based rules file-first (each file is parsed once and
    every rule runs on it), then concatenates results in rule order, so output
    order is unchanged and memory stays flat (peak RSS +4 MB).
  - `raw-sql-string-interpolation` and the inline-suppression scanner no longer
    tokenize files that cannot contain a `pylint:` / `odoo-doctor:` marker.
  - Scaling is linear (~0.06 s per addon from 14 to 112 addons). A native (Rust)
    core is not needed at this size: graph building is under 20% of the time.
  - Contract: the tree returned by `parse_python` is shared, treat it as read-only.

### Added

- **Taint analysis for the Security rules** (`rules/_taint.py`). Values are
  classified SAFE (provably constant), UNKNOWN (opaque, e.g. a parameter) or
  UNSAFE (a string built from non-constant parts) and followed through local
  variables, lists (`append`/`extend`/`+=`), `if`/`try`/loop branches (worst case
  wins) and module-level constants.
  - `raw-sql-string-interpolation` no longer reports SQL built only from
    constants, `int()` casts, `self._table`, `SQL(...)` or
    `','.join(['%s'] * n)` placeholder lists, and now reports dynamic fragments
    that reach `execute()` through a `join()` over a list or through one branch
    of an `if`/`else` (previously missed).
  - `eval-usage` no longer reports `eval(expr)` when `expr` is bound only to
    constants.
  - Behaviour change: interpolating a variable that was bound to a string
    constant is no longer reported (it cannot be injected); a parameter still is.
- **Supply-chain rules** (native rules: 33 -> 36; kept inside the existing
  categories so scores stay comparable): `manifest-license-incompatible`
  (Module Hygiene), `missing-external-dependency` (Module Hygiene, skips stdlib,
  Odoo's own requirements, guarded imports, tests) and `vendored-python-code`
  (Maintainability, medium confidence).
- **Multi-company / multi-currency rules** (native rules: 30 -> 33):
  - `monetary-missing-currency-field` (Correctness, P1, high): a `fields.Monetary`
    whose currency field (`currency_id` or `currency_field=`) provably does not
    exist on the model, following `_inherit`/`_inherits` and extensions in other
    scanned modules. Models extending an upstream model are skipped.
  - `missing-multicompany-rule` (Security, P1, medium): a model defined in the
    addon with a `company_id` to `res.company` that no `ir.rule` in the scanned
    modules protects.
  - `hardcoded-company-or-currency` (Correctness, P2, medium):
    `env.ref('base.main_company')` / `env.ref('base.USD')` in business code
    (install hooks, `migrations/` and `tests/` are skipped).
  - The parser now records `currency_field` on Monetary fields and the resolver
    can tell whether any scanned module declares an `ir.rule` for a model.
- **Fix ROI ranking** (`core/roi.py`). Each module's score-eligible findings are
  ranked by marginal score gain per effort (greedy on the unclamped
  `0.4 x min + 0.6 x avg` blend, so the weakest category is attacked first).
  Terminal: a *Fix first* list per module. JSON: `modules.<name>.fix_priorities`
  (top 10: `rank`, `rule`, `file_path`, `line`, `tier`, `impact`, `effort`, `roi`,
  `projected_score`, `score_gain`, `fixable`). `EFFORT_BY_RULE` holds a 1-3 effort
  per native rule (a test enforces an entry for every rule).
- **Golden corpus** (`tests/corpus/`, `tests/test_golden_corpus.py`): sample addons
  scanned end to end and compared with a frozen list of findings, so both true
  positives and previously fixed false positives are regression-guarded.
  Refresh with `UPDATE_GOLDEN=1 pytest tests/test_golden_corpus.py`.

### Fixed

- **`missing-xml-ref`** no longer flags the implicit `model_<model_name>` XML IDs
  Odoo generates for every model (e.g. `ref="model_my_model"` in `ir.rule` and
  report actions).
- **`manifest-missing-dependency`** follows `depends` transitively through every
  manifest it has seen (scanned addons and `odoo_source_path`). When the chain
  passes through a module with an unknown manifest, the finding is medium
  confidence instead of high, so it no longer affects the score.
- **`view-field-not-in-model` / `button-method-not-found`** resolve fields and
  methods inherited through `_inherit` + a new `_name` (and `_inherits`).
- **`missing-ondelete`** skips required `Many2one` fields (Odoo defaults them to
  `restrict`).
- **`search-in-loop`** no longer flags `browse()`, which does not query the
  database.
- **Performance rules** (`search-in-loop`, `create-in-loop`, `write-in-loop`,
  `n-plus-one-read`, `unbounded-search`) skip files inside an addon's `tests/`
  directory.
- **`manifest-data-order-risk`**: a data file named like a view/action/menu is no
  longer treated as a security file just because it lives in `security/`.
- **`data-noupdate-risk`**: `ir.rule` records are reported with medium confidence
  (not scored). Core and OCA disagree on `noupdate` for rules, so neither is a
  defect; `ir.config_parameter` and `ir.cron` stay high confidence.
- **`raw-sql-string-interpolation`** honours pylint-odoo's
  `# pylint: disable=sql-injection` marker (trailing comment: that line; own-line
  comment: the rest of the enclosing function), so explicitly vetted dynamic
  `WHERE` fragments are no longer reported.
- **`manifest-missing-required-fields`** no longer requires `installable` (Odoo
  defaults it to `True`) and no longer requires `data` when the manifest declares
  `assets` or `demo`. `odoo-doctor fix` no longer inserts `installable`.

### Roadmap decisions (explicit close-or-defer)

Closed in 0.6.0: multi-company / multi-currency rules, golden corpus, taint
analysis for the Security rules, fix ROI ranking, supply-chain rules, 2x faster
scans.

Deferred, with owner version:

| Item | Target | Reason |
|------|--------|--------|
| LSP server + VS Code extension | 0.7.0 | new stack (pygls + TypeScript); 0.6.0 spent its budget on rule trust and speed |
| Percentile score vs. other repos | 0.7.0 | needs an anonymised dataset and the remote service decision |
| LLM-assisted fix suggestions | 0.7.0 | deterministic fixers and ROI ranking come first; needs an opt-in/privacy design |
| Suppression analytics and calibration | 0.7.0 | the golden corpus is the first calibration input |
| Inter-procedural / type-aware taint | not scheduled | intra-procedural taint removed most noise; revisit with corpus evidence |
| Scan daemon / persistent cache | not scheduled | scaling is linear and a scan of 14 addons takes about 0.5 s |
| Hosted remote score service, auth, server-side trends | 0.7.0 (needs a product decision) | unchanged from 0.5.0 |
| Odoo in-app reporting module | 0.7.0 (depends on the remote service decision) | unchanged from 0.5.0 |

---

## [0.5.0] — 2026-10-03

Theme: close the proposal backlog and make findings explainable and trackable
without adding a hosted service.

### Added

- **Rules documentation from one source.** `src/odoo_doctor/rules/rule_docs.py`
  feeds `odoo-doctor rules explain` (now with description, why, fix and
  before/after examples), the generated `docs/rules.md`, SARIF `helpUri` and
  `Diagnostic.url`. New `odoo-doctor rules docs [--out FILE] [--format
  markdown|html] [--check]`; a test fails when `docs/rules.md` is stale.
- **Deep links.** Native findings carry a link to their rule docs, shown in the
  terminal, GitHub annotations, the PR comment and SARIF.
- **`rules disable|enable <rule>`** edit `[ignore] rules` in `odoo-doctor.toml`
  (comments and other keys untouched); `rules list` marks disabled rules.
- **Rule `expensive-nonstored-compute`** (Performance, P2, medium confidence).
  Native rules: 29 -> 30.
- **Score history** (`scan --history FILE`), **trend and regression detection**
  (`history show --max-drop N`, exit 2) and **legacy ingestion** (`history import`)
  that normalizes pre-0.4.0 reports lacking `score_schema_version` as schema 1.
  Scores of different schema versions are never compared. See
  `docs/score-history.md`.
- **Score badge** (`scan --badge FILE`): SVG or shields.io endpoint JSON, generated
  locally.
- **Plugin API v1 (GA).** Stable `odoo_doctor.plugin_api`; `@rule` validates
  category/tier/severity/confidence; duplicate names are rejected so plugins can't
  override built-ins; a failing plugin is rolled back; `ODOO_DOCTOR_PLUGIN_API`
  version check; `[plugins].allow` allowlist. `docs/custom-rules.md` rewritten.

### Changed

- **Default CI policy:** `--fail-on` now only counts findings admitted by
  `[surfaces.ci_failure]`, which defaults to **P0/P1 at high confidence**. P2/P3 and
  low-confidence findings are still reported but no longer fail the build. To keep
  the old behavior set `[surfaces.ci_failure] tiers = []` and `min_confidence = "low"`.
  New `tiers` key for every surface.
- `__version__` is now the single version source (it was stale at 0.1.0) and the
  JSON report reads it. `SCORE_SCHEMA_VERSION` and `project_score()` live in
  `core.scoring`.
- `rule()` registration is stricter: invalid metadata or a duplicate rule name
  raises `ValueError`.

### Roadmap decisions (explicit close-or-defer)

Closed in 0.5.0: advisory mode, `--fail-on`, multi-module scoring, `--module`,
`--odoo-version`, `rules list/disable`, `[severity]`/`[ignore]` config, version
detection from the installed `odoo` package, CI policy, `expensive-nonstored-compute`,
plugin API GA, rules docs, score history/badge.

Deferred, with owner version:

| Item | Target | Reason |
|------|--------|--------|
| Multi-company / multi-currency rules | 0.6.0 | needs model-level heuristics and fixtures; rule quality pass |
| LSP server + VS Code extension | 0.6.0 | new stack (pygls + TypeScript); builds on the fixer engine and rule docs links |
| Hosted remote score service, auth, server-side trends | 0.7.0 (needs a product decision) | serverless history/badge covers the trend use case first |
| Odoo in-app reporting module | 0.7.0 (depends on the remote service decision) | separate codebase per Odoo version |
| Split monorepo into `core`/`cli`/`rules`/`api` | not scheduled | high churn for users, no feature gain until `api` exists |
| Plugin marketplace/registry | not scheduled | plugin API only just reached GA; naming convention `odoo-doctor-rules-*` documented |
| OCA standards cross-check | not scheduled | scope undefined |

---

## [0.4.0] — 2026-06-28

### Added

- **5 new native rules** across 3 new categories:
  - **Data Integrity**: `missing-ondelete` (P1) — flags Many2one fields without explicit `ondelete`; `data-noupdate-risk` (P2) — flags critical model records (ir.rule, ir.config_parameter, ir.cron) not wrapped in `noupdate="1"`.
  - **Upgrade Safety**: `deprecated-api-usage` (P1) — detects old-API patterns (`from openerp`, `_columns`, `osv.osv`, `.pool`); `removed-model-still-referenced` (P1) — flags `_inherit` references to models not found in project or stubs.
  - **Frontend**: `asset-bundle-missing` (P2) — detects asset files listed in manifest `assets` dict that don't exist on disk (Odoo 15.0+).
- **Default Category Weights**: Scoring now applies sensible default weights per category (Security/Correctness: 1.5, Performance/Data Integrity/Upgrade Safety: 1.0, Module Hygiene: 0.8, Maintainability/Frontend: 0.5). User config overrides merge with defaults.
- **Score Schema Version**: JSON output now includes `score_schema_version: 2` for downstream tooling compatibility.
- **Parser Enhancements**: `FieldInfo` now tracks `ondelete` keyword; `XmlIdInfo` now tracks `noupdate` context from ancestor XML elements.
- **Manifest Assets Parsing**: `ManifestData` now parses the `assets` dict from `__manifest__.py` for frontend rule support.

### Changed

- Total native rules: 24 → 29. Active categories: 5 → 8.
- Version bumped to 0.4.0.

---

## [0.3.0] — 2026-06-12

### Added

- **Auto-Fix Engine**: Built `FixResult` for deterministic file modifications. Wired `--fix` and `--fix-dry-run` to safely apply non-destructive automated changes (e.g., missing manifest fields, data ordering).
- **Scanner Extraction & Caching**: Extracted orchestration logic to `core/scanner.py`. Introduced project-level `ScanCache` (`--cache`) based on content-hash fingerprinting to skip clean files and drastically speed up scans.
- **SARIF Reporter**: Developed `SARIF 2.1.0` output formatter (`--format sarif`) enabling native GitHub Code Scanning and advanced IDE integration.
- **Baseline Filtering**: Implemented a line-independent identity hash system (`--baseline` and `--write-baseline`) to freeze existing technical debt and only fail the CI on net-new issues.
- **Ecosystem Plugins**: Shipped an entry-point system allowing third-party Python packages to inject custom rules via the `odoo_doctor.rules` group. Gated by explicit `[plugins].enabled = true` config for security.
- **9 new native rules**: Spanning Security, Performance, and Correctness: `create-in-loop`, `write-in-loop`, `eval-usage`, `orphan-view`, `record-rule-without-domain`, `field-no-string-on-required`, `missing-translation`, `n-plus-one-read`, `sudo-without-comment`.

### Fixed

- **AST Heuristics**: Improved `receiver_is_orm` helper to accurately track loop variables originating from ORM records (`for rec in self: rec.write()`), fixing false negatives in loop-based rules.
- Odoo version detection regex adjusted to strictly match standard Odoo manifest formats (e.g., `17.0.1.0.0`).

---

## [0.2.0] — 2026-06-08

### Added

- **Capability Gates**: Gating mechanism to run rules only if version and capabilities criteria are met. Gating is evaluated before execution in CLI (preventing crashes/improving performance) and also filtered defensively in the pipeline. Supports `capabilities` configuration in `odoo-doctor.toml`.
- **LOCAL_NOT_FOUND Resolver State**: Explicit representation of local-scope missing symbols. Treat proven local absence as high confidence and score-impacting, eliminating ad-hoc rule-level logic.
- **Aggregated Dependency Inference**: Expanded `manifest-missing-dependency` to scan XML references, eval ref attributes, and inherited views. Diagnostics are aggregated by missing dependency module, presenting multiple evidence items in a single report.
- **eval="ref(...)" Parsing**: XML parser extracts referenced IDs within `eval` attributes using a conservative regex, enabling XML ref and missing dependency checks.
- **odoo_source_path Indexing**: Lightweight indexer (`build_source_index`) scans configured Odoo source addons for model ownership and XML IDs, resolving them without importing Odoo.
- **5 new native rules:** public-controller-sudo-risk (Security/P1), unbounded-search (Performance/P2), manifest-data-order-risk (Module Hygiene/P2), override-missing-super (Correctness/P1), compute-missing-depends (Correctness/P2). Registry now 15 native rules.
- **CI/PR surfaces:** `--format {terminal,json,github}` (GitHub Actions annotations); opt-in `--score-delta <base-ref>` (worktree-isolated base scan, aggregate delta); sticky idempotent PR comment via `gh`; composite `action.yml`; `[surfaces.pr_comment]` / `[surfaces.ci_failure]` config (min_confidence + categories).
- pylint-odoo D7 mapping: E8103=sql-injection (Security/P0) added; E8102=invalid-commit re-tiered to P2.

### Fixed

- `missing-xml-ref` now reports missing local/current-module XML references, including view `inherit_id` refs.
- `--diff` now preserves module context diagnostics when any file in that module changed, preventing missed findings such as missing ACLs after adding a model.
- `--fail-on` now treats the selected severity as a threshold, so `--fail-on warning` also fails on errors.
- Deduplication key now includes `rule` to ensure different rules reporting at the same location are not erroneously merged.
- Crash safety (Part B): non-UTF-8 source files, null adapter JSON fields, and non-zero adapter subprocess exits no longer abort a scan or fake a clean module.
- Part C correctness: `--diff` typos / unresolvable refs fail loudly (exit 3); `--min-score` out of 0–100 rejected (exit 3).
- Overall score rounded to 1 decimal so the terminal report and the `--min-score` gate agree.

### Changed

- `schema_version` remains `1.0` — the JSON shape is unchanged; 0.2.0 adds findings and render surfaces, not new payload fields.
- `oca` adapter key dropped from the `init` template (tolerated-but-inert if present in existing configs).

---

## [0.1.0] — 2026-06-03

### Added

**Core pipeline**
- `Diagnostic` dataclass — shared contract for all findings (frozen, typed)
- 7-stage pipeline: dedup → severity-override → ignore-filter → inline-suppression → version-gate → score-eligibility
- Scoring engine: `0.4 × min(category) + 0.6 × avg(category)` blend with per-category weights
- Config loader from `odoo-doctor.toml` (tomllib / tomli)

**Discovery & graph**
- Addon discovery from `__manifest__.py`
- Odoo version detection from manifest version string
- Manifest parser (ast.literal_eval)
- Python AST parser: `_name`, `_inherit`, `_fields`, methods, controllers
- XML/view parser: record IDs, field refs, button refs, inline suppression comments
- Security CSV parser: `ir.model.access.csv`
- `ModuleContext` + `ProjectGraph` builder with shared `SymbolResolver`
- Confidence-aware resolver: repo → stubs → UNKNOWN (no false positives)
- Bundled stubs for **17.0**, **18.0**, **19.0**
- `build_stubs.py`: generate stubs from Odoo source (AST) or live instance (XML-RPC)

**Rules (10 native)**
- `raw-sql-string-interpolation` — P0, Security
- `missing-access-csv` — P0, Security
- `unknown-model-in-access-csv` — P1, Correctness (UNKNOWN→finding only for current-module models)
- `duplicate-xml-id` — P1, Correctness
- `view-field-not-in-model` — P1, Correctness
- `button-method-not-found` — P1, Correctness
- `missing-xml-ref` — P1, Correctness
- `manifest-missing-dependency` — P1, Module Hygiene
- `manifest-missing-required-fields` — P2, Module Hygiene
- `search-in-loop` — P1, Performance
- Inline suppression scanner (`# odoo-doctor: disable=<rule>` in Python and XML)

**Adapters**
- Ruff adapter with `rule_mapping.toml`
- Pylint-Odoo adapter with `rule_mapping.toml`

**CLI** (`odoo-doctor`)
- `scan PATH` — scan addons, terminal or `--json` output
  - `--odoo-version` — override detected version
  - `--module` — scan only one module
  - `--diff BRANCH` — only findings on changed files (absolute-path resolved from git root)
  - `--fail-on error|warning` — exit 1 if severity found
  - `--min-score N` — exit 2 if any module scores below N (CLI flag overrides config)
- `rules list` — list all registered rules
- `rules explain <name>` — show rule metadata
- `init` — create `odoo-doctor.toml`
- `install` — copy SKILL.md files to `.odoo-doctor/skills/`

**Agent skills**
- `skills/odoo-doctor/SKILL.md` — scan & fix workflow
- `skills/odoo-doctor-explain/SKILL.md` — explain & configure workflow

### Fixed
- Resolver now checks extended fields from `_inherit` extensions (fixes false positives on `view-field-not-in-model` for custom fields on Odoo models)
- XML view parser: `_extract_arch_refs` no longer includes the `<field name="arch">` element itself as a field reference
- `unknown-model-in-access-csv`: UNKNOWN resolution upgraded to high-confidence finding when the CSV's external ID belongs to the current module
- `--diff`: paths resolved from git worktree root; absolute path comparison instead of fragile `endswith()`

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/).  
Breaking changes to the JSON output schema or CLI exit codes will be documented here.
