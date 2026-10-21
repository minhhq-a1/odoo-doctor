# Changelog

All notable changes to Odoo Doctor are documented here.

---

## [Unreleased]

---

## [0.11.2] — 2026-10-21

### Security

- The Ruff adapter no longer applies the scanned repo's Ruff configuration. This reverses the change in
  0.11.1 (PR #71) that made Ruff honour `ruff.toml`, `.ruff.toml` and `pyproject.toml` `[tool.ruff]`
  (0.11.0 and earlier also read them): a repo could use that configuration (`ignore`, `exclude`,
  `extend-exclude`, `per-file-ignores`, `extend`, `select = []`) to hide Ruff's findings from the
  report and the score, and `extend` made Ruff open any path (a FIFO hung it). Ruff now runs with
  `--isolated` (no configuration at all, Ruff's own default rule set), `--no-respect-gitignore` (a repo's
  `.gitignore`, `.ignore` or `.git/info/exclude` hid files from Ruff otherwise), `--no-cache`, a scratch
  working directory and `HOME`, no stdin and a secret-free environment. When the repo holds a Ruff
  configuration, one `[INFO]` line on stderr says it is ignored (once per configuration file per process,
  so the language server says it once, not on every rescan). Filter Ruff findings with `[ignore] rules`
  in `odoo-doctor.toml`. A `# noqa` or `# ruff: noqa` comment in a source file is still honoured by Ruff.
  Rules a repo configuration had switched on (beyond Ruff's defaults) are not reported; findings it
  had ignored are reported again.
- The scan cache and the language server's reuse key no longer include Ruff configuration files, their
  `extend` targets or ignore files (they are no longer inputs to Ruff); the Ruff and Pylint executables
  and versions still are. The code that checked an `extend` chain for special files and fell back to
  `--isolated` is removed, since Ruff is always isolated.

### Changed

- `search-in-loop`, `create-in-loop` and `write-in-loop` are `high` only for the loop shape that is
  provably wasted, no longer for every call on a plain `self` / `env[...]` receiver. A per-record query
  or write is how Odoo's own addons are written (core 19 holds 405 / 185 / 138 such findings that were
  `high`), so by the confidence policy those are now `medium`. `high` is kept for a call the loop cannot
  change: a query that is a plain statement of a `for` body (not under `if` / `try` / `match` /
  `assert`, not past a short circuit such as `and` / `or` / `x if c else y` / `a < b < query`, in no
  comprehension, `while` or nested function, no `break` / `continue` / `return` / `yield` in the body),
  whose receiver and arguments use no loop variable or rebound name (assignment, `except ... as`, a
  `match` capture, `import ... as`, `def` or `class`), in a loop that stores no attribute or item (also
  inside a tuple target or as the `for` target: `rec.a, b = ...`, `for rec.state in ...`) and calls
  nothing but plain reads (`search*`, `read*`, `browse`, `mapped`, `filtered`, `get`, `len` ... ;
  `create` / `write` / `unlink` / `flush*` / `invalidate*` / `message_post` / `action_*` or a helper of
  the class keep it `medium`), so it can be hoisted. A query that is a plain statement of an inner `for`
  is reported against that inner loop (and names the outer loops rebind count too). A `write` /
  `create` is `high` when it is the only statement of a `for` body, its values and context do not use
  the loop and call nothing that may return another value on the next pass (`fields.Datetime.now()` /
  `today()`, builtins, `_()` and `with_context` / `sudo` only; a sequence `next_by_code`, `uuid` /
  `random`, `next()`, a helper or another ORM call keep it `medium`): `for r in recs: r.write(vals)` is
  `recs.write(vals)`. Blind spot: a helper the loop calls is not followed (it only lowers the
  confidence); calls are allowed by name, so a user-defined `get` / `format` that writes, or a name that
  aliases one the loop mutates (`d = domain; d.append(..)`), is not seen; and a `write` / `create` is
  not checked for what the batched form would change (order of effects, per-record `write` overrides).
  Finding titles are unchanged, so baselines stay valid. The default `--fail-on` (P0/P1, high
  confidence) no longer fails on these loop findings. Golden corpus case `loop_confidence` holds one
  file per shape, named for its tier; the `performance_loops` and `loop_setup_not_flagged` cases now
  expect `medium`.
  Measured with native rules only (`[adapters] ruff = false, pylint_odoo = false`),
  `odoo-doctor scan <addons> --odoo-version 19.0 --json`, before = `4fcd49f` (main after 0.11.1),
  after = this change; the finding sets are identical apart from confidence. Odoo core 19 addons
  (`high` / `medium`): `search-in-loop` 405 / 75 to 0 / 480, `create-in-loop` 185 / 27 to 0 / 212,
  `write-in-loop` 138 / 43 to 1 / 180 (the one left is `mrp_production.py`: `for production in self:
  production.write({...})` whose values are constants and `fields.Datetime.now()`); project score 93.3
  to 95.1. On a private 14-module addon set the 10 `high` loop findings became `medium` (create 2 to 0,
  search 7 to 0, write 1 to 0) and the score went 96.4 to 99.0. A whole core 19 scan took about 88 s
  before and after (the two scans ran side by side).

### Fixed

- `fix` no longer rewrites line endings: a file is read and kept byte for byte, so a CRLF file stays CRLF and a
  BOM stays. A file that is not valid UTF-8 is skipped (counted in "skipped") instead of stopping the command with
  a traceback. After each fixer the engine checks that an `.xml` file still parses and a `.py` file still
  compiles, and drops a result that does not. Findings of one file are fixed from the last line to the first.

### Internal

- Groundwork for the 0.12 migration fixers: `FixerRegistry` knows `migration` fixers (skipped unless the caller
  passes `include_migration`) and a per-finding `applies` predicate; `rules/upgrade_safety/_xml_text.py` finds
  tags and `<record>` spans in XML text. Nothing uses them yet.

---

## [0.11.1] — 2026-10-21

### Security

- The terminal report (the default format, which lands in CI logs) wrapped a repo-chosen `::error::`
  word onto a line of its own, where GitHub treats it as a workflow command. Every `::` in repo-derived
  text now has an invisible zero-width space between the colons. In the PR comment, `@name` in a module name
  or finding title no longer mentions (notifies) anyone.
- The GitHub Action passed its inputs (`diff-base`, `paths` ...) into the shell script text; they now reach
  it as environment variables. `--diff` follows the ref with `--` so a ref that is also a path is never read
  as a path.
- `fix --fix` and discovery no longer follow a symlinked `__manifest__.py` (or any fixed file) out of the
  addon directory: a manifest that resolves outside its addon directory is skipped with one warning (the
  whole addon is then skipped) and is never read as a manifest or written, so a manifest symlinked to a shared
  file elsewhere in the same repository is skipped too, and `fix` then reports "Applied 0". An absolute path
  in a manifest `data` list that points outside the addon is skipped as well. A hard link cannot be
  detected: a manifest that is a hard link to a file outside the repository is still read and rewritten
  by `fix`.
- `scan --cache` no longer trusts `.odoo_doctor_cache/` in the scanned repo: a FIFO there hung the scan, and a
  symlinked cache file or directory let the cache write overwrite a file elsewhere. The cache is read only
  if it is a regular file inside the repo (and under 16 MiB, else ignored with a warning and rewritten) and
  is written through a temporary file plus rename. This does not stop a forged hit: a
  `.odoo_doctor_cache/scan_cache.json` committed to a repository carries a key its author can compute, so
  use `--cache` only on repositories you trust (CI on your own repository is fine).
- Repo-derived names (files, modules, versions, git's stderr) in the warning and error lines printed to
  stderr and stdout (skipped-file warnings, `[FAIL] <module>`, rule-crash warnings, `--diff`, `--score-delta`,
  `--history` and `--upgrade-report` messages, the `fix` diff header) go through the same sanitiser as the
  terminal report: control characters are shown escaped and `::` gets a zero-width space, so a file named
  `a<newline>::error::x.py` can no longer start a GitHub workflow command in a CI log.
- A git older than 2.31 cannot be told to ignore a repository filter driver whose name contains `=`; git is
  then skipped with one warning per run (not one per call), and `--score-delta` says so instead of
  "Not a git repository".
- Files are opened non-blocking and re-checked on the open descriptor, closing the gap between the file-type
  check and the read.
- A scan no longer blocks or exhausts memory on a special or huge file in the scanned repo. A FIFO
  named `*.py` (opening it blocks forever), a symlink to `/dev/zero` or to a FIFO, and a file over
  16 MiB are now skipped with one `[WARN] skipped <file>: ...` line on stderr; only regular files
  are read, the type being checked with `stat` before any `open`. A symlink (or `..` path) that
  leaves the addon directory is skipped too. This covers Python, XML and CSV files, manifests,
  inline suppressions, the scan-cache fingerprint, the Odoo source index, the language server and
  `fix`. A symlink to a regular file inside the addon is still scanned.
- git no longer runs code chosen by the scanned repo. `scan --diff`, `--score-delta`, `--history`,
  `--badge` and the HTML report's dirty flag ran git inside the repo, whose `.git/config` or hooks
  could name a program: `core.fsmonitor` (run by `status` and `diff`), `core.hooksPath` or a
  `post-checkout` hook (run by `worktree add`), a clean/smudge filter driver selected by
  `.gitattributes`, `core.sshCommand`, `diff.external`. Every git call now goes through one helper
  (`core/git.py`) that sets `core.fsmonitor=false`, `core.hooksPath` to the null device, an empty
  `core.sshCommand`, `--no-optional-locks`, blanks every configured filter driver, passes
  `--no-ext-diff --no-textconv` to `diff`, and runs git with a minimal environment (no tokens, no
  `GIT_*` variables except `GIT_CONFIG_GLOBAL` and the ones it sets itself: `GIT_TERMINAL_PROMPT`,
  `GIT_OPTIONAL_LOCKS`, `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n`). Your own global and system git
  config still applies, and so do your own filter drivers (git-lfs): only drivers the repository itself
  defines are blanked, through `GIT_CONFIG_COUNT` (git 2.31 or newer; older git is refused with a warning when
  a driver name holds `=`). git output is decoded leniently, so a non-UTF-8 config value or file name no
  longer crashes a scan.
- The Ruff adapter is hardened without giving up the repo's own Ruff configuration. A repo `ruff.toml` or
  `pyproject.toml` `[tool.ruff]` is still honoured (ruff finds it from the linted paths, so the team's rules
  and `ignore` apply), but ruff now runs with `--no-cache` (no `.ruff_cache` folder in the scanned repo, and a
  `cache-dir` in the repo config cannot make ruff write elsewhere), from a temporary working directory with
  `HOME`/`TMPDIR` there (no user-level config is read, nothing is written to the repo) and with a minimal
  environment (no tokens, no `RUFF_*`). A `required-version` the installed ruff does not satisfy gives a
  clear `adapter-ruff-warning` naming the cause instead of silence. Ruff config cannot run code (checked in
  ruff's documentation and by probes: `extend`, `per-file-ignores`, `exclude`, `src`, `preview` and
  `select` only change what ruff reads or reports). Residual risk: a hostile repo's ruff config can
  disable or change ruff's own findings (never odoo-doctor's native rules); the cache key already holds the
  repo's ruff configuration. Pylint is different and stays isolated: its configuration is ignored because
  pylint executes `init-hook` from it (see the Pylint-Odoo entry under Security in 0.11.0).
  Ruff and Pylint-Odoo also open every Python file they find, so a FIFO named `*.py` hung them; when
  the addon holds a file that must not be opened, they now get the regular `.py` files one by one.
  Ruff also opens the config files and every `extend` target itself: `extend = "evil.toml"` with a FIFO
  there (or a symlink to `/dev/zero`) held it until the 60 s adapter timeout, per addon. Before running
  Ruff the adapter now walks the config files it would find and their `extend` chain; if a link is not a
  regular file, is over 16 MiB or cannot be read, Ruff runs with `--isolated` for that addon and one
  `[WARN]` line names the file and says the repo's Ruff configuration is ignored. Any other config is
  honoured as before.
- A file name in the scanned repo can no longer inject GitHub workflow commands. `--format github`
  wrote the path into `file=` unescaped, so a name holding a newline and `::stop-commands::` or
  `::error::` ended the annotation and started a command of its own (the title and message were
  already escaped). The path now gets the same property escaping (`%`, `\r`, `\n`, `:`, `,`) as
  the title. The same hostile names are also neutralised in the other places that echo a path
  into a line-based channel: the terminal report (a newline could start a `::` line in a CI log, a
  raw ESC could drive the terminal; control characters now print as `\n`, `\x1b`) and the PR
  comment (the module table cell, the finding's code span and title could break out of the
  markdown table, list or code span). SARIF and the HTML report were already safe (JSON, hashed
  CSP, `textContent`).
- `--diff` and `--score-delta` no longer hand the ref to git as a possible option. `--diff=--output=<file>`
  made `git diff` write its output to that file (any path the user can write); a ref starting with `-`
  is now refused with exit 3 and a message before git runs. A ref that git itself can resolve is
  unchanged. `--end-of-options` is not used: it needs git 2.24 and the check above already leaves
  nothing for git to read as an option.

- Residual, not fixed here (backlog): the PR comment (`--format github` in a pull request) runs `gh pr view` /
  `gh api` / `gh pr comment` with the scanned repository as working directory and the inherited
  environment, and `gh` finds the repository (`{owner}/{repo}`) through `git` there, so the repo's own git
  config can apply to those calls; pinning `--repo` and the PR number needs the CI event data and was left
  alone to keep the behaviour on GitHub Actions. Use `--no-pr-comment` on a repository you do not trust.
  Pylint-Odoo adds the addon's parent directory to `sys.path` when it lints, so a repo file that shadows a
  module pylint imports lazily could be loaded (not verified here).

### Changed

- `raw-sql-string-interpolation` audited against Odoo 19 under the confidence policy (measured on
  `20f5882e`; Odoo 17.0 `02d3a1d8` scanned as 19.0 for comparison; skw has no finding of the rule).
  All 12 `high` hits on core 19 were read one by one; none is a proven injection:

  | class | core 19 | core17as19 (47) | what changed |
  |---|---|---|---|
  | rule wrong, no longer reported | 3 | 25 | an operator checked against literal choices before use (`if op not in ('<', '='): return`); a record's `.id` and `Datetime.now()` in a string; `LIMIT %d` / `%i` / `%f` formatting; the clauses of an Odoo 14-17 `Query` (`get_sql()`, `select()`, `subselect()`); `sql.Placeholder` |
  | core convention, now `medium` | 9 | 22 | SQL built from model metadata (`self._sequence_field`), ORM-built fragments (`self._get_seen_list_extra()`, `_select_companies_rates()`) or the parameter of a `_private` helper whose callers pass literals |
  | true positive, `high` | 0 | 0 | |

  `high` now means that the text of the query is built from something a caller outside the module
  controls: a parameter (including `**kw` / `post`) of a public method (RPC reaches those) or of a route;
  `request.params`, `request.httprequest`, `request.get_json_data()` and cookies; a public field of `self`
  (`self.name`, `self.mapped('name')`, `for rec in self`: the fields of a wizard are typed in by the user);
  and the same values passed on to a private helper of the same class or a module-level function of the
  same file (up to 3 hops). It stays `high` even if model metadata is interpolated next to them.
  Everything else that is dynamic is `medium`: model metadata and ORM-built fragments, `self.env.context`,
  a private helper only literals reach, a module-level function no entry point calls, and the ORM hooks
  with a leading underscore that the ORM feeds from RPC arguments (`_search`, `_read_group`,
  `_name_search`, `_search_*`; an `order`, `groupby` or name typed by a client can reach them, a
  documented limit). `medium` is listed but does not lower the score and does not trip the default
  `--fail-on` policy (P0/P1 high confidence). Core 19: 12 `high` -> 0 `high` + 9 `medium` (3 gone);
  core17as19: 47 `high` -> 0 `high` + 22 `medium` (25 gone); skw: no finding of the rule, as before.
  The message of a `high` finding now reads "... uses dynamic SQL string construction from a parameter a
  caller controls" (a `medium` one says it comes from model metadata, ORM-built fragments or a private
  helper's parameter); it appears in JSON, SARIF, GitHub annotations and the HTML report. Odoo 17+
  `env.execute_query(SQL(f"...{x}"))` (on `self.env`, `env`, `request.env`) and `cr.copy_expert(...)` are
  checked like `cr.execute`; this adds no `high` on core 19, core 17 scanned as 19 or skw.
  The shared taint analysis (`rules/_taint.py`) also follows `with ... as` targets and unpacking of a
  constant value, which `eval-usage` gets too. Scores of 7 core 19 modules rise (`phone_validation`
  64.4 -> 100.0, `product_margin` 64.4 -> 100.0, `mass_mailing_sms` 59.8 -> 77.9); none falls.
- The language server no longer redoes everything on each save. It keeps, per workspace folder and in
  memory only, the results of the previous scan and reuses what cannot have changed: the whole scan when no
  file moved, the file-based native rules per unchanged file, Ruff and Pylint-Odoo per addon (an addon is
  linted again when one of its files, or a file of an addon it depends on, changed) and the index of
  `odoo_source_path`. Cross-module rules and the graph are still rebuilt on every changed scan, so the
  findings and scores equal a scan from scratch (`tests/test_scan_reuse.py` backs this). A file is told apart
  by size, mtime, ctime and inode (plus a content hash for files written in the last 2 s); the whole result
  is never reused while a plugin rule is registered. Saves arriving within 0.3 s
  of each other share one scan. Measured on a copy of the 14-addon skw repo (save of one file, median):
  1.5 s -> 0.6 s without linters, 10.6 s -> 1.9 s (p95 11.2 s -> 3.1 s) with Ruff and Pylint-Odoo,
  12.6 s -> 0.8 s with `odoo_source_path` set; a save that changes nothing relevant takes about 0.01 s.
  On a 29-addon slice of Odoo 19 core: 29.7 s -> 13.3 s. Set `ODOO_DOCTOR_LSP_REUSE=0` to turn it off.
  The command line is unchanged. *Rescan workspace* forgets the kept state first (the escape hatch if a result looks stale), and forgetting
  never waits for a running scan.
- `public-controller-sudo-risk` grades a route by whether `auth=` is written on it. `auth='public'` or
  `'none'` on the route stays `high` (`medium` after an access check). A route that omits `auth` now takes
  the auth of the route it overrides (see Fixed) and is `medium` (`low` after an access check) when that
  auth is public or cannot be resolved: Odoo's own addons override public routes and elevate in them as a
  convention. Measured on Odoo 19 community: 7 routes (6 public, 1 unresolved) newly reported, all reviewed as
  conventions (`cloud_storage` `mail_attachment_upload` elevates the attachment its own `super()` call just
  created, `im_livechat` `channel_call_join` a documented read-only `search` that raises `NotFound`,
  `website_crm_partner_assign` `partners_detail` shows only published partners, `website_event_sale` and
  `website_sale_collect` read the session's own cart and website configuration,
  `pos_online_payment_self_order` `pos_order_pay_confirmation` reads one transaction after `super()` checked
  the access token). Hence no new `high` on core 19 (151 high stay, medium 68 -> 74, low 0 -> 1) or on core 17
  scanned as 19 (medium 57 -> 62, low 0 -> 2). `scripts/measure.py` shows no new `high` for any rule and no
  change on the working repository. The grade of an explicit `auth='public'` with `sudo()` (`high`, 151 hits in
  Odoo 19 community, mostly conventions like the above) is a pre-existing choice and is not touched here; the
  inherited grade is deliberately `medium`.
- `search-in-loop`, `create-in-loop` and `write-in-loop` report a finding as `medium` (not `high`, no effect on
  the score) when it rests on an inferred receiver or an aggregate query: a local that was assigned a recordset
  (`recs = self.env['x'].search([])` then `recs.write(..)`, or the model handle `Model = self.env['x']`), a
  comprehension, or `search_read` / `search_fetch` / `read_group` / `_read_group`. `self` and `env[...]`
  receivers in a `for` / `while` loop stay `high` and are unchanged (no `high` finding of these rules changed
  on core 19, core 17 scanned as 19, or the working repository; the rule that treats a clearly ORM-local
  recordset as `medium` lost 8 `medium` findings on core 19 (5 on core 17 scanned as 19) and 0 `high`;
  otherwise `scripts/measure.py` shows only `medium` increases). Odoo's own addons query per company or per group inside loops: of the 145 new core 19
  findings 35 are `_read_group` / `search_fetch` / `search_read` calls (often per entry of a `grouped(..).items()`
  dict or per company), 107 follow a local (many are `Model = self.env['x']` handles used per file, warehouse or
  company) and 3 are in comprehensions, so the policy keeps them out of `high`. Measured: Odoo 19 community
  75 + 27 + 43 new `medium`
  (`search` / `create` / `write`; `high` 405 / 185 / 138 unchanged), core 17 scanned as 19 61 + 30 + 35, the
  working repository 3 + 2 + 2.

### Fixed

- `view-field-not-in-model` reported `message_ids`, `activity_ids` and every field of a parent as unknown (error,
  high) for a model whose `_inherit` is a tuple (`_inherit = ("mail.thread", "mail.activity.mixin")`): the
  parser read only strings and lists, so the model looked complete. `_inherit` and `_inherits` are now read as
  a string, a list or a tuple (an extension written with a tuple adds its fields too), and a parent that is not
  written out (`_inherit = MIXINS`, `_inherit = _name`, `*args`, a computed entry) makes the model incomplete,
  so no field is reported missing. Parents that an extension in another module adds (`_inherit = ['x.base',
  'mail.thread']` without `_name`, in a module that does not define `x.base`) now count for `x.base`: a view on
  it using `message_ids` was still reported. An extension whose `_inherit` is computed (`['x.base'] + MIXINS`)
  still names `x.base` and makes it unresolved; one that names no model (`_inherit = MIXINS`, no `_name`) used to
  lose its fields, which are now never reported missing. On Odoo 17 scanned as 19, 11 false `high` findings go (24 -> 13): the 9
  `ir.module.module` views of `website`, whose model is declared with `_inherit = _name`, and 2 `res.company`
  views using `message_follower_ids` / `message_ids`, a model that `account` extends with `mail.thread`; none change on Odoo 19.
- A route that omits `auth` (a bare `@http.route()` override, or `@http.route('/x', website=True)`) was
  recorded as `auth='user'`, although Odoo merges the parent route's routing into the override. Overridden
  public routes (`/shop`, portal pages) therefore escaped `public-controller-sudo-risk`. The auth is now taken
  from the route of the same name in the class's bases, found by class name through every scanned addon
  (several levels, an explicit `auth=` wins). A parent that is not among the scanned classes (an addon that is
  not scanned) or a computed `auth=` leaves it `unknown` rather than `user`; a route with no parent at all
  still runs as `user`. Several scanned classes of one name (two addons that each override `WebsiteSale`) no
  longer make each other `user`: a class reached again while it is being resolved gives no evidence, and the
  route is `unknown` when nothing else answers (a cycle `A(B)`/`B(A)` too). On Odoo 19 community this moves 6
  routes from `unknown` to `public` (undeclared routes: public 20 -> 25, unknown 18 -> 13) and one public to
  unknown (`website` `bundle`, behind two same-named `WebClient` classes). Limits: only `auth` is inherited,
  not `csrf`, `type` or `methods`; a parent is found by class NAME, so an unrelated scanned
  `class Main(http.Controller)` with `auth='user'` can capture a subclass that imports another addon's `Main`,
  and an import alias (`import X as Y`) is an unresolved parent; `[target_modules]` limits discovery, so a
  parent in a module that is not a target is not found (unknown).
- `rpc-sudo-without-access-check` treated a class as a controller only when a base was literally named
  `Controller`, so routes of a `CustomerPortal` or `WebsiteSale` subclass were never looked at. A class with a
  `@http.route` method is now a controller whatever its base is called (a method needs a route to be reachable,
  so resolving the base would add nothing). The rule takes each route's auth from the same resolution; a route
  whose auth is public or unknown is left to `public-controller-sudo-risk`, so the rule is silent on a bare
  override of a parent route that is not scanned and on a computed `auth=CONST`. Measured: no new `high` on core;
  4 new `medium` on core 19 (6 -> 10) and 3 on core 17 scanned as 19 (4 -> 7).
- `scan --diff` missed changed files whose name has non-ASCII characters (`modèle.py`), a tab or a
  newline: git prints such names quoted and escaped (`"mod\303\250le.py"`), which matched no file, so
  their findings were silently left out of the diff scan. Changed files are now read with `-z`
  (NUL-separated, never quoted).
- `--cache` could answer differently from an uncached scan, or keep answering after an input changed:
  - A cache hit scored with the Odoo version from the config (often `unknown`) instead of the one the
    live scan detected from the manifests, so the in-scope categories, and with them the scores, could
    differ for a ruleset with version- or capability-gated rules. The entry now stores each module's
    Odoo version and a hit scores every module with its own (the same fix as the per-module gating below).
  - A hit listed modules in an order set by the process's hash seed, not the scan order, so `--json`
    differed byte for byte between a live run and a hit. The order is now the scan's.
  - The key held only `name@min_version` of each rule, so a plugin rule whose code changed kept
    returning the old findings. It now also holds, for every rule that is not built in, the
    distribution name and version that ships it (when installed) and a hash of the rule module's
    source file.
  - The key did not hold the version of `ruff` or `pylint`, so upgrading a linter kept the old
    findings. It now holds the output of `<tool> --version` (run once per process; `unavailable` when
    the tool is missing) for every enabled adapter. The enabled flags were already in the key.
  - The config part of the key put a Python `set` (`explicit_adapters`) through `repr()`, whose order
    changes with the hash seed, so a config with two or more `[adapters]` entries could miss on every
    run. It is now serialised in sorted order.
  - The key also holds the pylint-odoo distribution version, read by the interpreter behind the `pylint`
    executable (`pylint --version` does not name its plugins); `unknown` when that interpreter cannot be
    found.
  - Known limit of the key: a rule registered outside `[plugins] enabled` (library use) is identified by its
    distribution version and a hash of the rule's own module file only, so another file of that package is
    not hashed. Rule plugins loaded through `[plugins] enabled` bypass the cache altogether.

  `CACHE_VERSION` is now 5 (4 on main stored the per-module versions, 4 on this branch the scan's
  version and the new key parts; 5 rebuilds either), so older cache files are rebuilt once.
- `override-missing-super` accepted any `super()` call in the body: `super().write(..)` inside `create` counted as
  the call chain, so the missing `create` super was never reported. The call must now be
  `super().<same method>` (`super().create(..)`, `super(Cls, self).create(..)`); a `super()` kept in a variable
  (`parent = super()`) is still trusted. The raise-only skip, the delegation `medium` and the `_auto = False`
  `medium` of 0.10.1 are unchanged. No finding of this rule changes on Odoo 19 community (3 medium), core 17
  scanned as 19 (2 medium) or the working repository: core uses `super().<same method>` everywhere.
- `search-in-loop`, `create-in-loop` and `write-in-loop` (one shared walker in `rules/_ast_helpers.py`,
  `orm_calls_in_loops`): they never looked inside a comprehension (`[self.env['x'].search(..) for r in recs]`,
  dict/set comprehensions and generator expressions: the element, the conditions and the iterables after the
  first run once per item; the first iterable runs once); they did not follow a local assigned from an ORM
  expression, so `recs = self.env['x'].search([]); for r in recs: r.write(..)` was missed (the iterable of a
  `for` over a search result, `for r in self.env['x'].search([]):`, was already correct and is not reported:
  it runs once); `search_read`, `search_fetch`, `read_group` and `_read_group` were not in the method set of
  `search-in-loop`; and any `self.<attr>` was treated as a recordset, so `self.client.search(..)` on a service
  object was a false `high`. An attribute that `__init__` sets (`self.client = client`) or that the class body
  assigns something other than a `fields.X(..)` declaration is now a plain object; a field, or an attribute
  inherited from a plain base class that is not scanned, is still taken for a recordset. New golden corpus
  case `loop_forms`. The new detections are `medium`, see Changed.
- `view-attrs-states-removed` never checked a kanban view outside its `<templates>`: any `t-*` attribute made the
  whole view QWeb, so `attrs` / `states` on the `<field>` and `<button>` elements of a kanban were not
  reported, although Odoo 17 and later reject them. Only the QWeb parts are skipped now (a `qweb` view, a
  `<templates>` block, an element with a `t-*` directive, and an xpath whose `expr` names `templates` or `@t-`
  into them), and an xpath into a template is no longer reported. No change on Odoo 19 community, core 17
  scanned as 19 or the working repository (none has the pattern). New golden corpus case `kanban_attrs`.
- `manual-cr-commit` exempted every `cr.commit()` on a name that the file bound to its own cursor or
  environment anywhere (`with self.pool.cursor() as cr:` in one method silenced `cr.commit()` and
  `env.cr.commit()` of every other function, including the request's own cursor passed as a parameter).
  The exemption now follows scope: the function that opens the cursor and the functions nested in it, and the
  module level; a parameter with the same name shadows an outer binding. `self.env.cr.commit()` was never
  exempt. No change on Odoo 19 community (23 medium), core 17 scanned as 19 (30 medium) or the working
  repository (1 medium). New golden corpus case `cr_commit_scope`.
- Keep distinct violations of one rule at the same location, including missing
  manifest fields and dependencies; only matching titles are deduplicated.
- Apply version/capability gates and category scope per module in mixed-version
  projects. Cache entries retain module versions so cached scores match fresh scans.
- Write portable v3 baselines using paths relative to the scan root (`--write-baseline` now writes
  `"version": 3`). Existing v1/v2
  baselines remain readable with their original identities; regenerate them to move
  between checkout paths. An older odoo-doctor reading a v3 baseline does not recognise its identities
  and treats every finding as new.
- Invalidate scan caches for Ruff configuration changes, including ancestor and
  recursive `extend` configs, linter availability/versions and configured Odoo source
  changes. Plugins with arbitrary input dependencies bypass the built-in cache.
- Tooling directories are not scanned: `.git`, `.ruff_cache`, `.mypy_cache`, `.pytest_cache` and
  `__pycache__` (anywhere below an addon). The scan-cache fingerprint already skipped them, while the scan
  still read Python and data files inside them, so a warm `--cache` run could report fewer findings than an
  uncached one. Both now share one list (`core/source.py::SKIP_DIRS`); it also applies to the line counts,
  the module graph, the orphan-view text search, the language server's file stamps, and Ruff/Pylint are
  handed explicit files when such a directory holds Python.
- The language server did not see a change to the Ruff configuration while it ran: after creating, editing
  or deleting `ruff.toml`, `.ruff.toml`, `pyproject.toml`, a file they `extend`, or a `.gitignore`, Ruff
  findings stayed stale until a restart. These files and the Ruff/Pylint executables are now stamped into
  the reuse key and the per-addon lint signature.
- Use the same default P0/P1 high-confidence CI failure policy with absent, empty
  and partial configurations.
- Collect context-rule generators once so plugin findings are retained in full and
  diff scans.
- Known limits, not audited yet (backlog): `csrf-disabled-authenticated-route` has the same inherited-auth
  gap as the route-auth bug fixed above (a bare override of a route with `csrf=False` is read as `user`);
  and the pre-existing `high` loop findings (core 19: `search-in-loop` 405, `create-in-loop` 185,
  `write-in-loop` 138) are against the confidence policy (Odoo's own addons write such loops) and have not
  been audited like `raw-sql-string-interpolation`.


## [0.11.0] — 2026-10-19

### Added

- `scan --upgrade-report` (with `--odoo-version <target>`): groups the Upgrade Safety findings by kind
  of change, counts findings and files, estimates effort, labels each finding mechanical (a pure
  rename, `high` confidence only; the fixer is planned) or needs review, and scores each module's
  upgrade readiness 0-100. Terminal: printed after the normal output. `--json`: new top-level key
  `upgrade_report` (`readiness_schema_version` 1), present only with the flag. SARIF/GitHub/HTML
  ignore it; without the flag nothing changes. Guide: `docs/upgrade-report.md` (formula, labels, rule to
  migration-topic table). Measured on the Odoo 17.0 addons scanned as 19.0: 578 modules, 2816 Upgrade
  Safety findings in 1066 files, 1752 labelled mechanical and 1064 needing review; on a 19.0 project
  (14 modules) 0 findings and every module at 100. With `--odoo-version X` every module is evaluated as
  targeting X regardless of its manifest version (the scan cache key includes this); a plain scan
  still gates each module on its own manifest version (the explicit version only applies when the
  manifest version is not a recognised `NN.0`), so without `--odoo-version` a module declaring `17.0.x`
  shows an empty report and a stderr warning says so.

### Security

- `raw-sql-string-interpolation` had four gaps. (1) `SQL(f"...{x}")`, `SQL("..." + x)`,
  `SQL("...".format(x))` and `SQL("..." % x)` were treated as safe; only `SQL("... %s", x)` with separate
  parameters (or a constant) is safe now. (2) Cursors from `request.env.cr`, `request.cr`,
  `registry.cursor()`, `self.pool.cursor()` (including `with ... as cur` and `cur = ...cursor()`) were not
  recognised, so controllers were missed. (3) `.format()` into `DROP`, `ALTER`, `TRUNCATE`, `WITH`,
  `GRANT`, `COPY` and other statements was ignored. (4) Taint was lost through tuple unpacking
  (`a, b = x, y`) and the walrus operator. New findings may appear, all `high`: on Odoo core 19 one more
  (`l10n_in`, 11 -> 12), on core 17 scanned as 19 four more (43 -> 47: `crm`, `web` domain controller,
  `website_sale`); the SKW project is unchanged. These are interpolations of ORM-built fragments or
  internal constants, the same shape as the 11 `high` findings core 19 already had.
  `SQL(query=f"...")` is now examined like the positional form. Known limits, also in the rule docs: an
  import alias of `SQL` (`from odoo.tools import SQL as S`) is not followed, and a statement that starts
  with a SQL comment defeats the statement-start check of the DDL/`WITH`/`COPY` heuristics.
- The Pylint-Odoo adapter no longer lets the scanned repo run code. Pylint executes the `init-hook` of
  a `.pylintrc`, `pylintrc` or `pyproject.toml` it finds from its working directory, so scanning an
  untrusted repo (CI, editor language server) could run its code. Pylint now runs with an empty
  `--rcfile`, from a temporary directory, with a minimal environment (no tokens, no `PYTHONPATH`).
  Repo-level pylint configuration is ignored; the adapter is still switched on or off with
  `[adapters] pylint_odoo` in `odoo-doctor.toml`.
  If you had disabled pylint messages in a repo `.pylintrc`, move them to `[ignore] rules` in
  `odoo-doctor.toml`.
- Python files whose name starts with `__` were never scanned: `__init__.py` (install hooks such as
  `post_init_hook` run with full access) and any file renamed `__foo.py` hid its findings. Only
  `__manifest__.py` is skipped now (in the scanner, the module graph and the Odoo-source index). New
  findings may appear: on Odoo core 19 the scan adds 11 (4 `high` loop rules in install hooks such as
  `l10n_ch`, 7 `low` `sudo-without-comment`); on core 17 scanned as 19, 23 (including 6 `medium`
  `missing-translation` in `UserError` messages of hooks); the SKW project is unchanged. The largest score drop seen is `project_timesheet_holidays` in Odoo core 19 (94.7 -> 89.9).

### Fixed

- Packaging: the `typer>=0.12` lower bound was wrong. Older Typer releases crash on current Click
  (`TypeError: Secondary flag is not valid for non-boolean flag`) or fail on `scan --help`; the
  bound is now `typer>=0.16`. A CI job (`lowest-versions`) installs the lowest allowed versions
  of every direct dependency on Python 3.10 and runs the test suite.
- Publishing: `publish.yml` uploaded to PyPI without checking anything. It now runs the tests and
  ruff, checks that the tag is `vX.Y.Z` and equals `pyproject.toml` and `odoo_doctor.__version__`
  (`scripts/check_release_version.py`), and installs the built wheel in a clean virtual
  environment to run `odoo-doctor --version` and a scan, before the upload. Run manually, the
  workflow must be started from a tag.
- The sdist no longer contains `editors/vscode/README.md` and `editors/vscode/LICENSE` (the
  `include` patterns are anchored), and the empty `wheel.shared-data` table with its wrong
  comment is gone. The wheel is unchanged.
- One bad input file no longer aborts a scan. A manifest with an unhashable key or a non-list
  `depends`/`data`, an XML file declared UTF-8 but holding other bytes, a Python file too deep for the
  parser (`RecursionError`/`MemoryError`), and an `ir.model.access.csv` that is not UTF-8 or has short
  rows are skipped (or read leniently) and the other files are still reported. Addon names, rule names
  and paths containing `[` or `]` are escaped in the terminal report instead of being mangled.
- A manifest `version` that is not a string, or `external_dependencies` of the wrong shape, no longer
  aborts the scan (the value is ignored).
- A skipped input is no longer silent: one `[WARN] skipped <file>: <reason>` line on stderr per file
  (stdout is untouched, at most 20 lines per scan then `... and N more skipped`, exit codes unchanged) for
  an unparseable manifest, XML that cannot be read, a non-UTF-8 `ir.model.access.csv`, and a Python file
  the parser cannot handle. A plain `SyntaxError` in a user file stays quiet. Nothing is parsed on a
  `--cache` hit, so the warnings appear once per change of the project; run without `--cache` to see
  them again.
- Python 3.10 crashed the interpreter (segmentation fault, nothing catchable) on a file holding one
  expression chained over ~136,000 links (`1 + 1 + ...`, `a.b.b...`, `a[0][0]...`, `f(1,2)(3)...`,
  `a[1:2][1:2]...`, the same inside brackets or in an f-string). The scanner now skips, with a warning, a
  file of at least 100,000 characters that chains more than 50,000 links in one expression (Python
  files, manifests, the Odoo-source index and the manifest fixers). This is a best-effort guard, not a
  proof: it models the chain shapes measured on 3.10 (about 20) and a shape it does not model could
  still crash 3.10; 3.12+ raises a catchable `RecursionError` instead. Non-regular files (FIFOs) are not
  covered.

## [0.10.2] — 2026-10-17

### Added

- HTML report: the header says `(uncommitted changes)` after the commit when the scanned working tree is
  dirty (new `dirty` key in the page's `meta`; computed with a read-only `git status`, never written to
  the scanned repo; absent outside git; untracked files count, the scan's `.odoo_doctor_cache`
  directory does not).
- Two secondary project numbers next to the main score, which keeps its formula and
  `score_schema_version`: `project_score.weighted` (module scores weighted by each module's Python line
  count, every `*.py` file under the module path, tests and vendored code included, so large
  modules dominate) and `project_score.with_medium` (plain mean with `medium` findings counted too).
  The terminal shows them on a dim line when they differ from the main score by 0.1 or more, and the HTML header
  shows them. `--min-score`, `--fail-on`, history and the badge still use the main score only.
  The scan cache now also stores the per-module line counts, so `CACHE_VERSION` is 3 and older caches
  are rebuilt once.

### Changed

- HTML report: finding paths in the page are relative to the scan root instead of absolute, so the file
  no longer reveals the scanning machine's directory layout (paths outside the root stay absolute); the
  `--baseline` file is shown relative to the root, or by file name only when outside it. `scan --json`
  and other outputs are unchanged.

### Fixed

- Baseline: findings of one rule at one location kept the same identity, so a baseline holding only a
  `medium` `manifest-missing-required-fields` (e.g. no `version`) also hid a later `high` one (e.g. no
  `license`), and the same for several `manifest-data-order-risk` findings in one manifest. The finding
  title is now part of the identity, and `--write-baseline` writes `"version": 2`. Existing version 1
  baselines keep working (matched by the old identity); rewrite them with `--write-baseline` to get the
  stricter identity. The `manifest-data-order-risk` title now names the security file.

## [0.10.1] — 2026-10-17

### Changed

Precision audit. A finding is `high` only if its pattern does not fire on Odoo core 19, unless it is a
true positive with evidence and a corpus case; patterns that core itself uses become `medium` (they are
still listed, but do not lower the score). Measured on Odoo 19.0 at `20f5882e` (`scripts/measure.py`;
Odoo 17.0 `02d3a1d8` scanned as 19.0 and the skw project for comparison); none of the 154 + 52 + 49 + 8
core 19 hits of the four convention rules was a true positive, so their `high` count there is 0.

Rule was wrong, fixed (the finding is no longer reported):

- `duplicate-xml-id`: a later declaration that only sets fields the earlier ones did not set (the usual
  way to patch a record) is not reported. Core 19: 41 of the 49 `high` hits.
- `override-missing-super`: a method that only blocks the operation (`raise` and no `return`) is not
  reported. Core 19: 5 of the 8 `high` hits.
- `dynamic-method-dispatch`: a name taken from a literal tuple, `fn.__name__`, a `__getattr__` hook, or
  a helper that refuses ORM methods is not reported. skw: 7 of 8; core 19 is unchanged (4 `medium`).
- `sudo-without-comment` (`low`): a `.sudo()` named by a comment within 5 lines above or by the function
  docstring, and `.sudo()` on a `self` after a bare `self = self.sudo()` (until `self` is rebound), are
  not reported. skw: 6 (80 -> 74); core 19: 72 (2735 -> 2663; a sample of 12 of them was read: all
  Odoo's own `# sudo: ...` comments).

Core does not follow the convention, now `medium` (still listed, no longer lowers the score):

- `manifest-missing-required-fields`: a missing `version` or `data` (Odoo defaults both: `1.0` and `[]`);
  `name`, `license` and `depends` stay `high`. Core 19: 154 `high` -> 0, 154 `medium`.
- `manifest-data-order-risk`: `high` only when a security XML creates a group that an earlier data file
  already resolves while loading (a menu or template `groups=`, a `ref` or `eval="ref(...)"` of the group;
  Odoo raises for these). Everything else is `medium`, including a CSV after views and a group referenced
  only from a view `arch` (Odoo only warns). Core 19: 52 `high` -> 0, 52 `medium`.
- `duplicate-xml-id`: a later declaration that sets a field again (Odoo allows it, the later value wins).
  Core 19: the other 8 hits, now `medium`.
- `override-missing-super`: calling its own name on records derived from `self` (1 hit) or `create`/`write`
  on a model with `_auto = False` (2 hits). Core 19: the other 3 hits, now `medium`.

True positive, kept:

- `high` stays where Odoo really fails or does the wrong thing, each with a positive corpus case and no
  hit on core 19: `manifest-missing-required-fields` for `name`/`license`/`depends`,
  `manifest-data-order-risk` for a group resolved before it is created, `duplicate-xml-id` for another
  `model` on the same id (Odoo raises), `override-missing-super` for an override without `super()` and
  without the exceptions above.
- `missing-ondelete` and `data-noupdate-risk` are unchanged. The judgement that they are true positives
  was made on the skw hits only (all 42 and all 11 read), not on the core 19 hits: core 19 has 1001 `low`
  `missing-ondelete` and 55 `high` / 32 `medium` `data-noupdate-risk`, unchanged.
- `dynamic-method-dispatch` keeps the admin-editable `related_action` name (`medium`, skw: 1).

Also:

- Exit codes: `duplicate-xml-id` and `override-missing-super` are P1, and the default `--fail-on` policy
  (`[surfaces.ci_failure]`: P0/P1 `high`) counts only `high` findings. A scan that failed the build only
  because of the patterns above now passes: the ones listed as `medium` still appear in `--format json`
  (at `medium`), the ones listed as no longer reported are gone from every format.
- Manifest fixers only act on `high` findings and edit the manifest text locally (comments, quoting,
  key order and the `medium` parts stay identical, line endings are normalised to LF by `fix`; a second
  run changes nothing); they return "not fixable" instead of guessing. `manifest-data-order-risk --fix`
  moves only the file that is reported `high`, in front of its first consumer, instead of moving every
  security file to the top.
- Scores: because findings moved from `high` to `medium` or are no longer reported, 208 modules of core 19
  score higher (project score 93.2 -> 93.9; the largest changes are `l10n_ar` 51.1 -> 94.7, `event`
  48.4 -> 75.9 and `l10n_fi` 85.8 -> 100.0), 184 modules of Odoo 17.0 scanned as 19.0 (88.2 -> 88.6), and
  none on skw (96.5, 170 -> 157 findings, all removed ones `low` or `medium`). No score goes down. The
  scoring formula and `score_schema_version` are unchanged.

### Fixed

- `compute-missing-depends` named a different undeclared field from one run to the next (the fields were
  visited in set order, which follows `PYTHONHASHSEED`, and only one finding per method survives
  deduplication). It now reports the alphabetically first one, so two scans of the same code agree.

## [0.10.0] — 2026-10-16

### Added

- `scan --show-low` and `[surfaces.terminal]`: choose which findings the terminal lists.
- `scripts/measure.py`: a maintainer tool (not shipped, not run in CI) that prints findings per rule and
  confidence for named targets, stores snapshots and compares them (`--compare` exits 1 when a rule outside
  the audit list gets noisier). See `CONTRIBUTING.md`.
- `scan --html <file>`: a self-contained HTML report (score, module × category table, fixes
  ranked by score gain, a filterable findings list with low-confidence findings hidden by
  default, suppression counts and, with `--history`, a score trend). No server, no network
  request; works with `--diff`, `--module`, `--cache` and `--baseline` (hidden findings stay hidden; a
  baseline that hides everything produces no report). Exit code 3 when the file
  cannot be written. See `docs/html-report.md`. Measured on oho-addons (271 modules): 2479
  findings → 2.2 MiB, loads in 0.06 s (headless Chrome on file://, DOMContentLoaded); on skw: 171 KiB.

### Changed

- `rules explain <unknown rule>` now exits 3 with `[ERROR] Unknown rule: <name>` on stderr (it
  exited 0 and printed to stdout).
- CI runs the tests on Python 3.13 as well; `docs/support.md` lists the version-gates of the
  Odoo 18/19 migration rules.
- Terminal output hides low-confidence findings by default and prints how many were hidden (JSON, SARIF,
  HTML, `--fail-on` and scores are unchanged); `--show-low` lists them all.
- `scan --score-delta` prints its `Score Delta:` line after the file artifacts (`--history`,
  `--badge`, `--html`) are written instead of before; the order relative to the report is the same.
- Documentation brought up to date: the README rule table lists all 55 rules, `docs/performance.md`
  is re-measured for 0.9.3 on Odoo 19.0 (55 rules; the old run used 40), the contributor guides
  (`AGENTS.md`, `CONTRIBUTING.md`) describe the golden corpus, the `EFFORT_BY_RULE` entry and the
  current layout, and `docs/lsp.md` no longer says there is no `--version` flag.

### Fixed

- The confidence marker (`[low]`/`[medium]`) after a finding title in the terminal report was swallowed by
  rich markup and never printed. Finding titles, messages, help text and URLs are now printed literally too
  (a message containing `[/x]` made the terminal report raise `MarkupError`).

---

## [0.9.3] — 2026-10-13

Theme: the Odoo 18 / 19 migration set. Six rules for view and data constructs that Odoo 18 or
19 rejects or silently ignores, taken from a real 17 → 19 migration log and checked against the
source of Odoo 17.0, 18.0 and 19.0. Native rules are now 55. Rule IDs, CLI flags and JSON keys of
existing rules are unchanged (see `docs/stability.md`); a project on Odoo 18 or 19 can see its
score drop where it still uses these constructs.

### Added

- New rule `view-tree-removed` (Upgrade Safety, P1, Odoo 18+): the `tree` view type, renamed
  `list` in Odoo 18 with no alias. Reports `<tree>` in a view (also nested in an x2many),
  `<field name="type">tree`, a `tree` XPath step, `tree` in the `view_mode` of an action or of
  an `ir.actions.act_window.view` (also inside an `eval`), and Python action dicts with
  `'view_mode': 'tree,form'` or a `(False, 'tree')` pair in `'views'`.
- New rule `removed-core-field-usage` (Upgrade Safety, P1, Odoo 18+): fields that core models
  lost: `groups_id` of `res.users`, `ir.ui.view`, `ir.ui.menu` and the actions (renamed
  `group_ids`), `category_id` and `users` of `res.groups`, `mobile` of `res.partner` and
  `crm.lead`, `deprecated` of `account.account`, `user_id` of `ir.filters` (Odoo 19) and
  `detailed_type` of the product models (Odoo 18). In data files and views the model is known,
  so the finding is high confidence; in Python only `groups_id` and `detailed_type` are looked
  for, at medium confidence, and a model the module creates itself or an
  `if 'groups_id' in rec._fields` branch is skipped.
- New rule `search-view-group-attributes` (Upgrade Safety, P1, Odoo 19+): `string` or `expand`
  on a `<group>` of a search view, which the Odoo 19 schema rejects.
- New rule `act-window-target-inline` (Upgrade Safety, P1, Odoo 19+): `target` `inline` on an
  `ir.actions.act_window`, a value Odoo 19 removed (record or Python action dict).
- New rule `chatter-div-removed` (Upgrade Safety, P1, Odoo 18+): `<div class="oe_chatter">`.
  Odoo 18 and 19 only compile the `<chatter/>` tag, so the form loads but shows no chatter.
- New rule `kanban-legacy-templates` (Upgrade Safety, P1, Odoo 19+): the `kanban-box` and
  `kanban-menu` templates (named `card` and `menu`) and XPaths that target them. Odoo 18 still
  read the old names; Odoo 19 fails with "Missing 'card' template".

### Changed

- `removed-model-still-referenced` also knows `ir.property` (18), `stock.valuation.layer`,
  `stock.quant.package` (now `stock.package`), `hr.employee.base` and `res.partner.title` (19).
- Shared helpers for rules that read a whole module (`data_files`, `python_files`, XML record
  and view helpers, `make_diag`) moved to `rules/_module_files.py`. No behaviour change.

On the community addons of Odoo 19.0 and 17.0 the new rules report nothing, and the Odoo 19 score
is unchanged; Odoo 18.0 gives 1 true finding (a `div.oe_chatter` left in `l10n_id_efaktur_coretax`).
Scanned as 19.0, Odoo 17.0 core now yields 1,392 `view-tree-removed`, 447
`removed-core-field-usage`, 169 `search-view-group-attributes`, 160 `kanban-legacy-templates`,
75 `chatter-div-removed` and 24 `act-window-target-inline` findings where the rules of 0.9.2
reported none of these; Odoo 18.0 core scanned as 19.0 gives the renamed fields, search groups and
`inline` targets. On a real Odoo 19 workspace of four repositories the migration had already
fixed most of this, and the rules still find: 94 `div.oe_chatter` in 43 modules (not in the
team's migration log), 9 `kanban-box`, and 3 `tree` references the mechanical rename missed (a
`views` pair in two Python action dicts and one action with `tree,form,search`). A false positive
found there, an `if 'groups_id' in user._fields:` branch, is now skipped and covered by a test; the
golden corpus case `tests/corpus/migration_19` freezes the rest.

---

## [0.9.2] — 2026-10-13

Theme: the rest of the backlog from scanning real Odoo 19 repositories: five rules for code that
is deprecated, unsafe or fragile rather than broken. Native rules are now 49. Rule IDs, CLI flags
and JSON keys of existing rules are unchanged (see `docs/stability.md`); a project can see its
score drop where it uses these patterns.

### Added

- New rule `deprecated-orm-api-usage` (Upgrade Safety, P2, Odoo 18+): calls of ORM methods the
  running version still defines but deprecates: `read_group`, `toggle_active` and
  `check_field_access_rights` (19), `check_access_rights`, `check_access_rule`,
  `_filter_access_rules` and `_check_recursion` (18). An override of `read_group` is reported too:
  on Odoo 19 the web client goes through `web_read_group` / `formatted_read_group` and `_read_group`,
  so the override is never called by grouped views. A call on `self`/`env` is high confidence, any
  other receiver medium.
- New rule `tls-verification-disabled` (Security, P1): `verify=False`, `session.verify = False`,
  `check_hostname = False`, `verify_mode = ssl.CERT_NONE` and `ssl._create_unverified_context()`.
- New rule `http-request-without-timeout` (Performance, P2): `requests.get/post/...`, calls on a
  `requests.Session`, and `urlopen()` without `timeout`. A call that passes `**options` is skipped.
- New rule `csrf-disabled-authenticated-route` (Security, P1): `csrf=False` on a `type='http'`
  route that authenticates by session (`auth='user'`) and accepts POST/PUT/PATCH/DELETE. Webhooks
  (`auth='public'`/`'none'`), JSON routes and GET-only routes are not reported, because Odoo does
  not check the token there.
- New rule `manual-cr-commit` (Data Integrity, P1): `cr.commit()` on the request's own
  transaction. High confidence inside ORM methods Odoo calls mid-operation (`create`, `write`,
  `unlink`, computes, constraints, onchanges); medium elsewhere, where a commit after an external
  call is often deliberate. Not reported: a cursor the code opened itself, crons, install hooks,
  commits under an `auto_commit` / `_can_commit()` / test-mode guard, and
  `# pylint: disable=invalid-commit`.

### Changed

- Shared helpers `odoo_major`, `receiver_kind` and `pylint_disabled_ranges` moved to
  `rules/_ast_helpers.py`; `raw-sql-string-interpolation` and `removed-orm-api-usage` use them.
  No behaviour change.

The deprecations were checked against the ORM source of Odoo 18.0 and 19.0 (`@api.deprecated`);
CSRF behaviour against `odoo/http.py` of 17.0 and 19.0. On the community addons of Odoo 19.0 the
new rules report 8 `http-request-without-timeout` (core really calls `requests` without a
timeout), 1 `deprecated-orm-api-usage` (`read_group` in `l10n_dk`) and 23 medium `manual-cr-commit`
(no score effect), nothing else; 17.0 and 18.0 are similar. On a real Odoo 19 workspace of four
repositories: `tls-verification-disabled` 3 (all `verify=False` in two addons),
`http-request-without-timeout` 81, `deprecated-orm-api-usage` 69 (7 `read_group` overrides that
never run, `check_access_rights` / `check_access_rule`, `toggle_active`, `_check_recursion`),
`manual-cr-commit` 7 (all medium, queue-job style commits) and `csrf-disabled-authenticated-route`
0: every webhook there is `auth='public'` or `'none'`. The rule is covered by tests and the golden
corpus case `tests/corpus/backlog_rules`.

Not added on purpose: bare `except:` and mutable default arguments (Ruff reports them with its
default rules), and `self._cr` / `self._uid` / `self._context`, deprecated in 19 but still used by
Odoo core and too frequent to be useful.

---

## [0.9.1] — 2026-10-12

Theme: four Upgrade Safety rules found by scanning real Odoo 19 repositories. Each one catches
code that Odoo 17, 18 or 19 refuses or silently ignores and that no existing rule noticed. Native
rules are now 44. Rule IDs, CLI flags and JSON keys of existing rules are unchanged (see
`docs/stability.md`); a project on Odoo 17 or later can see its score drop where it still uses
these APIs.

### Added

- New rule `sql-constraints-unsupported` (Upgrade Safety, P1, Odoo 19+): a model that sets
  `_sql_constraints`. Odoo 19 only logs a warning for the attribute and creates none of the
  constraints, so a UNIQUE or CHECK silently stops being enforced. Use `models.Constraint`. Plain
  mixins, empty lists, test files and `migrations/` scripts are ignored.
- New rule `removed-orm-api-usage` (Upgrade Safety, P1, Odoo 17+): overrides and calls of
  `fields_view_get` and `invalidate_cache` (removed in 17) and `name_get` (removed in 18). A call
  on `self`/`env` is high confidence; a call on an unrelated object is medium and does not score.
- New rule `cron-removed-fields` (Upgrade Safety, P1, Odoo 18+): `numbercall` or `doall` on an
  `ir.cron` record, fields the model no longer has. A job that used `numbercall` to run a limited
  number of times now repeats on every interval.
- New rule `view-attrs-states-removed` (Upgrade Safety, P1, Odoo 17+): `attrs` / `states` in the
  architecture of a view, which Odoo 17 and later refuse. An empty `<attribute name="states"/>`
  edit (it removes the attribute, the way a pre-17 view is ported) and QWeb templates are not
  reported.

Each version gate was checked against the ORM and view source of Odoo 17.0, 18.0 and 19.0. The
rules give 0 findings on the community addons of Odoo 17.0 (578 modules), 18.0 (624) and 19.0
(636). On a real Odoo 19 workspace of four repositories `sql-constraints-unsupported` reports 5
findings (for example `_sql_constraints` on a customs-declaration model) and
`removed-orm-api-usage` 5 (`name_get` / `fields_view_get` overrides and `invalidate_cache` calls in
third-party addons), all true. `cron-removed-fields` and `view-attrs-states-removed` find nothing
there: the one cron file that sets `numbercall` is not listed in its manifest, and the one view hit
was a false positive (an empty `states` edit, which removes the attribute), now fixed and frozen in
the golden corpus (`tests/corpus/removed_apis`) together with `migrations/` scripts.

---

## [0.9.0] — 2026-10-12

Theme: freeze and document what 1.0 will promise. No new rules and no change to rule IDs, JSON
keys or existing flags; findings and scores are the same as 0.8.2. Native rules stay at 40.

### Added

- `odoo-doctor --version` prints `odoo-doctor <version>` and exits 0.
- `docs/support.md`: the supported Python and Odoo versions, which of them CI covers, and the
  release support policy (latest release only, one-minor deprecation window).
- `docs/performance.md`: reference scan timings on Odoo 19 community (636 modules: 47.7 s cold,
  1.6 s with an unchanged `--cache`, 0.8 s for one module) and how to reproduce them.

### Changed

- `docs/stability.md` now lists every `rules` action (including `new`), the `--version` flag and
  the experimental status of `lsp`, and documents the exit code of every command, not only
  `scan`. Behaviour is unchanged: the table records what the commands already did, including
  that a usage error raised by the argument parser itself exits 2.
- `tests/test_stability_contract.py` freezes `--version` and those exit codes, so a script that
  relies on them cannot break silently.

### Not in this release

The Notion plan for 0.9.0 also listed `migrate-config`, a rule registry with signed packs, a docs
website and a public RC programme. `migrate-config` has nothing to migrate (no config key has
changed incompatibly); the others are not started and are not part of the stability contract.

---

## [0.8.2] — 2026-10-12

Theme: three new Security rules, and fixes for two silent failures found by reviewing the output on
a real Odoo 19 workspace and on Odoo 19 community (690 modules): native rules switched off when the
Odoo version is unknown, and the PR comment posted by the wrong output format. Native rules are now
40. Rule IDs, CLI flags and JSON keys of existing rules are unchanged (see `docs/stability.md`);
`--no-pr-comment` is new. Scores can move: the new rules can lower a score, and a project scanned
without a detectable Odoo version now runs the native rules it silently skipped before.

### Added

- New rule `access-write-without-group` (Security, P1): a row of `ir.model.access.csv` with an empty
  `group_id:id` that grants `perm_write` or `perm_unlink` applies to every user, portal and public
  users included. It is reported at high confidence; a row that only grants `create` is medium
  (public forms do that on purpose) and does not score. Rows for `TransientModel` wizards are
  skipped. Calibrated on Odoo 19 community (690 modules, 62 group-less rows, all read-only: 0
  findings) and on a real workspace, where it flags e.g. a model that manages access groups and is
  writable by everyone.
- New rule `dynamic-method-dispatch` (Security, P1): `getattr(obj, name)(...)` where the code does
  not fix `name`, so whoever controls it can run any method of the object (`unlink()`, `sudo()`...).
  High confidence when the name comes from the parameters of a public method (reachable by RPC or
  HTTP); medium, not scoring, for names read from records or in private helpers. Names built on a
  constant prefix, looked up in a module-level table, checked in the same function or taken from a
  logger are ignored. Calibrated on Odoo 19 community (690 modules: 0 high, 5 medium) and on a real
  workspace, where the one high finding is a controller that calls a method named by a request
  parameter.
- New rule `rpc-sudo-without-access-check` (Security, P1): a public model method or an authenticated
  route that calls `.sudo()` on records or values chosen by its parameters, with no access check in
  the method (an IDOR). High confidence, which scores, only when a parameter reaches a write,
  unlink or create on the elevated recordset and the method does not scope by the caller
  (`env.user`, `uid`). Reads, `search` results (already limited by the caller's record rules),
  parameters handed to another method (where a check may live), check-style calls and `raise`
  of `AccessError` / `Forbidden` are medium or ignored. Public routes stay with
  `public-controller-sudo-risk`. Calibrated on Odoo 19 community (690 modules: 1 high, 5 medium; a
  first draft gave 97 high) and on a real workspace.

### Changed

- The `No Odoo addon found` warning now says where the addons are. When the scan roots hold none,
  odoo-doctor looks up to four folders deeper (skipping hidden, `node_modules`, `venv` and similar
  folders) and prints the folders whose children are addons, e.g.
  `odoo-doctor scan extra-addons/my_repo   (14 addons)`, at most three plus a count of the rest.
  Discovery itself is unchanged, `scan PATH` still scans only the folders directly inside PATH, and
  the hint goes to stderr only.

### Fixed

- `scan --format github` now posts the sticky PR comment, and `--format sarif` no longer does. The
  posting block sat in the SARIF branch of `scan` since PR 7: a SARIF scan commented on the pull
  request of the current checkout through `gh` (the test suite did it on real PRs from a logged-in
  machine), while `--format github`, the one the Action runs, never posted anything.
- New `--no-pr-comment` turns the comment off for `--format github`; the Action's `pr-comment: false`
  input now passes it (it only controlled `--score-delta` before).
- The test suite puts a stub `gh` first on `PATH`, so no test can act as the developer's GitHub login.
- A scan whose Odoo version could not be detected no longer switches the native rules off. The
  version comes from `--odoo-version`, the config, then a manifest version shaped like `17.0.x.y.z`;
  a custom addon versioned `1.0` with no config gave `unknown`, and `unknown` failed every
  `min_version` gate. 36 of the 37 native rules declare one, so such a scan reported only Ruff
  results and a score of 100. `unknown` now keeps the rules enabled (a known version below the
  floor still gates them). Scores of projects scanned without a detectable version can drop.

---

## [0.8.1] — 2026-10-07

Theme: trust the findings of a real workspace. A 14-addon Odoo 19 workspace scan was reviewed rule
by rule against Odoo 19 community (and the published sources of two OCA addons it contains); each
rule below was calibrated on that evidence. Rule IDs, CLI flags and JSON keys are unchanged (see
`docs/stability.md`). Scores of existing projects can rise: `missing-ondelete` no longer scores,
and `public-controller-sudo-risk` scores only routes without an access check.

### Fixed

False positives found by scanning a real Odoo 19 workspace (14 addons: 45 `orphan-view` and 26
`removed-model-still-referenced` findings, all medium confidence, none affecting the score).

- `orphan-view` no longer flags a model's default views. Odoo serves a model's primary view of
  each type (lowest `priority`, then first defined) with no action or reference, so only the
  *extra* primary views of the same model and type can be dead. QWeb view records are skipped, and a
  view whose id is mentioned in the module's Python, JS, XML or CSV (`env.ref`, `form_view_ref`,
  `doAction`) counts as referenced. `ViewInfo` gains `view_type` (filled now) and `priority`.
- `removed-model-still-referenced` no longer reports every `_inherit` it cannot resolve. A model
  missing from the scanned set is normally an unscanned dependency (`stock.move.line`,
  `hr.employee`, enterprise models), not a removed one. The rule now reports a curated list of
  core models Odoo certainly removed or renamed (`account.invoice` -> `account.move`,
  `stock.production.lot` -> `stock.lot`, `mail.channel` -> `discuss.channel`, ...), from the
  version that removed them, and names the replacement. A model the project defines itself is
  never reported.
- Golden corpus: new `unscanned_dependencies` case keeps the true positives (an unused extra view,
  `_inherit = 'account.invoice'`) next to the cases that must stay silent.
- `sudo-without-comment` (75 findings in the same workspace): a comment now counts when it sits on any line of the statement that
  holds the `.sudo()` or directly above that statement, not only on the call's first line, so a
  chained `(self.env[...]\n.sudo()\n.get_param(...))` justified by a comment above no longer
  fires. A compound statement (`if`, `for`, `with`) counts only its header lines. `.sudo(False)`
  (drops privileges), test files and migration scripts are skipped. The convention itself is
  unchanged: it is a team policy, and Odoo 19's own addons leave about 80% of their `.sudo()`
  calls uncommented, so its confidence drops from medium to low. The score is unaffected (only
  high confidence scores); a surface with `min_confidence = "medium"` now hides it.
- `missing-ondelete` drops from high to low confidence. An optional stored `Many2one` without
  `ondelete` gets `set null`, a deliberate default: about 83% of Odoo 19 community's optional
  stored `Many2one` fields (`company_id`, `user_id`, `partner_id`...) rely on it, yet the finding
  was high confidence and cost score (P1, 10 points each). On a real 14-addon workspace it
  accounted for 42 findings and pulled `purchase_request` to 47.9 and `workflow_diagram` to 37.0;
  without them those modules score 75.3 and 44.5 (the other findings are unchanged). The finding
  stays visible, the message now states what `set null` does instead of predicting integrity
  problems, and the help names `cascade` / `restrict` for the cases that need them. Scores of
  existing projects rise; the history regression gate is not triggered by a rise.
- `eval-usage` no longer reports a bare `eval(...)` / `exec(...)` when the module binds that
  name itself, e.g. `from odoo.tools.safe_eval import safe_eval as eval` (an Odoo 8/9 idiom
  still found in ported addons) or `eval = safe_eval`: that call is the sandboxed function, not
  the builtin. Module-level bindings count (also inside `if` / `try`); a method named `eval`
  shadows nothing. New golden corpus case `eval_shadowed`.

False positives of the loop rules (`search-in-loop`, `create-in-loop`, `write-in-loop`) found by
reviewing a real workspace and Odoo 19 community:

- The loop's own iterable was treated as part of the loop, so the most common line in Odoo,
  `for rec in self.env['x'].search([...]):`, was reported as a search in a loop. The iterable and
  the `else` clause run once and are no longer in scope; the iterable of an *inner* loop still
  counts for the outer one (it runs once per outer iteration), and a `while` condition still counts.
  On Odoo 19 community 87 of 522 `search-in-loop` findings were this; 2 of the 9 loop findings of the
  two OCA addons in the reviewed workspace (`queue_job`, `purchase_request`) were too.
- Loops over chunks (`split_every(...)`, `range(start, stop, step)`) and over a literal tuple/list
  of constants no longer count: they run once per chunk or a fixed number of times.
- A `while` loop paged with `search(..., limit=N)` (N other than 0/1) no longer counts: the search is
  the batching. `limit=1` is still a lookup per iteration and is reported.
- The per-iteration walk now lives in `rules/_ast_helpers.py` (`per_iteration_nodes`,
  `is_bounded_loop`), shared by the three rules. New golden corpus case `loop_setup_not_flagged`.

Review of the last two high-confidence security findings of a real workspace, calibrated on
Odoo 19 community (221 of its 978 controller routes are public and use `sudo()`; 32 of its
`cr.execute` calls were reported as injections):

- `public-controller-sudo-risk` grades the finding. A route that also calls an access check
  (`consteq`, `_document_check_access`, `check_access*`, a `_verify_*` / `hmac` / `*_from_token`
  call) is reported at medium confidence (no score impact; 68 of Odoo's 219 routes), without one it
  stays high. Minting a token (`generate_access_token`) is not a check. `.sudo(False)` and
  `env['ir.config_parameter'].sudo().get_param('<constant>')` are no longer elevations. The message
  says which case applies. `ControllerInfo` gains `guarded`.
- `raw-sql-string-interpolation` treats `<anything>._table` as a trusted identifier (it was only
  `self._table` / `cls._table`) and skips `upgrades/` scripts like `migrations/` (renamed in
  Odoo 18). 32 -> 26 findings on Odoo 19 community. The taint analysis itself is unchanged.
- New golden corpus case `public_routes_and_sql`.

### Changed

- `n-plus-one-read` is redefined around the real N+1 of the ORM. It reported any chained attribute
  read on any `for` loop variable (`for line in order.line_ids: line.product_id.name`), i.e. nearly
  every record loop: 5748 findings on Odoo 19 community and 45 on the two OCA addons of a reviewed
  workspace, yet Odoo prefetches such reads per recordset, so they cost one query per field, not per
  record. It now reports a field read on a record built by `browse(<one id>)` on every iteration
  of a `for` loop or comprehension (the id depends on the loop variable, also through a name
  assigned from it): that singleton starts with an empty prefetch, so each read is a query.
  `with_prefetch(...)` (before or after `browse`), `browse` of a collection or of a loop-independent id,
  method calls and `id` / `env` are not reads. 235 findings on Odoo 19 community, none on the OCA
  addons. Still low confidence, never scored; the title, message and help changed accordingly.
  New golden corpus case `n_plus_one_prefetch`.
- `eval-usage` message now shows the evaluated expression and why it is flagged (not provably
  constant, or built from interpolated text), and the help names `ast.literal_eval` and
  `safe_eval`. Detection is otherwise unchanged: on Odoo 19 community the rule reports a single
  bare `exec` (the `shell` command), so its high confidence stands.
- `odoo-doctor scan` now prints a `[WARN] No Odoo addon found under: …` line on stderr when the
  scan roots hold no addon. `scan PATH` scans only the folders directly inside PATH, so
  `scan .` on a repository root used to produce a silent, empty report (0 modules, score 100).
  The message points to omitting PATH (use `addons_paths`) or targeting the addons folder.
  Exit code stays 0 and stdout (including `--json`) is unchanged; `--module` and `--diff` do
  not trigger it.

---

## [0.8.0] — 2026-10-06

Theme: let others extend Odoo Doctor, and trust what it reports. A scaffold and a stricter
version check for third-party rule packs, CI templates for GitLab and Bitbucket, hover and
Windows coverage for the language server, and a round of false-positive fixes found by
scanning Odoo 19.0 community (660 modules: 18,740 -> 16,061 findings, and 5,853 -> 3,330
high-confidence ones, the only ones that score). Rule IDs, CLI flags and JSON keys are
unchanged (see `docs/stability.md`); `rules new` is an added action.

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

### Roadmap decisions (explicit close-or-defer)

Closed in 0.8.0: contributor onboarding (`rules new`), plugin loader versioning and contract
tests, CI templates for GitLab CI and Bitbucket Pipelines, language server hover, CI for the
VS Code extension on Linux and Windows, and a finding-quality pass on a real Odoo tree. The
VS Code extension carries the same version and the new icon; it is published manually.

Deferred, with owner version:

| Item | Target | Reason |
|------|--------|--------|
| Listing `rules new`, `ci-templates/` and the language server in the stability contract; per-keystroke analysis | 0.9.0 (candidate) | newly shipped; needs real-world use first |
| Public rule registry / marketplace; signed or verified rule packs; revocation | not scheduled | needs a trust model (Sigstore or publisher keys) and a hosted index; nothing to verify until third-party packs exist |
| Community stub registry (verified vs community stubs, confidence degradation) | not scheduled | a wrong stub affects the whole graph engine, not one rule |
| Stubs and rules for Odoo 14-16 | not scheduled | stubs exist for 17-19 only |
| i18n of messages and docs | not scheduled | translation upkeep is a burden with one contributor |
| OCA rule mapping, RFC / open governance process | not scheduled | depends on OCA maintainers and on more contributors |
| Anonymised benchmark dataset, "State of Odoo code health" report | not scheduled | needs an opt-in data path and the remote service decision |
| Calibrating the confidence of convention rules (`manifest-data-order-risk`, `manifest-missing-required-fields`, the rest of `duplicate-xml-id`, `override-missing-super`) | needs a decision | Odoo 19 core, which loads fine, triggers them 53, 166, 51 and 11 times: they are conventions, not errors |
| Telling a view root from a subview in an inherited view's xpath (`//list/...` as the first step) | when first needed | needs the parent view's type through `inherit_id`; 5 `view-field-not-in-model` remain on Odoo 19.0 |

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
