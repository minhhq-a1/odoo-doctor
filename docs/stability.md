# Stability contract

What you can rely on when you upgrade Odoo Doctor, and what may change without
notice. The public surface below is fenced by `tests/test_stability_contract.py`:
removing or renaming any of it fails CI.

Odoo Doctor is still `0.x`, so semantic versioning would allow anything to change.
This document makes a stronger promise: from **0.7.0** the public surface follows the
policy below, and it is the contract intended for 1.0.

## Policy

- **Additions are free.** A new command, flag, JSON key, config key or rule can ship in
  any release.
- **Removals and renames are never silent.** Anything public is first marked
  *Deprecated* in the `CHANGELOG.md` for at least one minor release (and, where the
  surface can warn at run time, it warns on stderr), and only then removed. The one
  exception is a security fix.
- **Rule IDs are permanent.** A rule ID is never reused for a different check. If a rule
  must be renamed, the old ID keeps working (config, `disable=` comments, baselines) for
  at least one minor release.
- **Findings and scores may change.** Rules get more precise, so the findings, their
  messages and the numeric score of a given codebase can differ between releases. A
  change to the *scoring formula* bumps `score_schema_version`; scores of different
  schema versions are not comparable (history and regression checks already respect
  this).
- **Experimental features are marked.** The language server (`odoo-doctor lsp`) and the
  VS Code extension are experimental in 0.7.0 and are not covered by this contract
  until they are listed here.

## Public surface

### Command line

Commands: `scan`, `fix`, `rules`, `init`, `install`, `history` (`show`, `import`), and the
global flag `--version` (prints `odoo-doctor <version>` and exits 0). The `rules` actions
are `list`, `explain`, `disable`, `enable`, `docs`, `stats` and `new`. Their flags are
public; the exact set is frozen in `tests/test_stability_contract.py`. The text printed
for humans (terminal tables, colours, wording) is **not** public; use `--json` or
`--format` for anything a script reads.
`scan --html <file>` writes a self-contained HTML report next to the normal output. The flag,
and the exit code 3 below, are public; the content and layout of the file are not (like the
terminal text), and neither are the keys of the data embedded in it. Read `--json` for data.
`scan --show-low` lists the findings the terminal hides by default (`[surfaces.terminal]`) and
changes nothing else: JSON, SARIF, HTML, `--fail-on` and scores are the same with or without it.

`odoo-doctor lsp` (the language server) is experimental and not covered by this contract
until it is listed here; it exits 3 when the optional `lsp` extra is not installed.

**Exit codes.** `scan`: `0` clean, `1` findings at or above `--fail-on`, `2` score below
`--min-score` (or a history regression), `3` invalid arguments or a git failure. The
other commands follow the same convention where it applies:

| Command | Code | Meaning |
| --- | --- | --- |
| any | `0` | success |
| any | `2` | usage error raised by the argument parser itself (unknown flag, missing argument) |
| `fix` | `3` | neither or both of `--fix` and `--fix-dry-run` |
| `rules docs` | `3` | `--format` is neither `markdown` nor `html` |
| `rules docs --check` | `1` | the page on disk is out of date |
| `rules` | `3` | unknown action, an unknown rule name for `explain`/`disable`/`enable`, or `explain`/`disable`/`enable`/`new` without a rule name |
| `history show --max-drop N` | `2` | the newest score dropped by more than `N` points |
| `history import` | `3` | invalid `--timestamp`, or no report could be imported |
| `install` | `1` | the packaged skills are missing (reinstall the package) |
| `scan --html` | `3` | the report file cannot be written, or the packaged report assets are missing (reinstall the package) |

Do not rely on the exit code of anything not listed here.

### Machine-readable output

- `scan --json`: top-level keys `version`, `schema_version`, `score_schema_version`,
  `project_score` (`overall`, `label`, `module_count`; the optional, additive `weighted` and
  `with_medium` are secondary numbers and never gate anything), `top_findings`, `modules`; per module `score`, `fix_priorities`,
  `suppression_stats`, `diagnostics`; each diagnostic carries `module`, `file_path`,
  `line`, `column`, `rule`, `category`, `severity`, `tier`, `source`, `confidence`,
  `title`, `message`, `help`, `odoo_version`, `url`.
- `rules stats --json`: `thresholds` and `rules` (per rule `surfaced`, `inline`,
  `ignore_rule`, `severity_off`, `suppressed`, `total`, `ratio`, `noisy`, `suggestion`).
  The noise thresholds themselves may be tuned.
- Score history (`--history`, JSON Lines, `history_schema_version` 1) and the baseline
  file (`--write-baseline`, `"version": 2`; version 1 files are still read).
- SARIF output is valid SARIF 2.1.0 with the rule name as `ruleId`. GitHub annotations
  follow GitHub's own workflow-command format.

Unknown extra keys may appear in any of these; readers must ignore keys they do not know.

### Rule IDs and inline suppression

The rule names listed by `odoo-doctor rules list` are permanent (see the policy). The
comment syntax `# odoo-doctor: disable=<rule>[,<rule>]` and `disable-file=<rule>` (and
the XML equivalent) is public.

### Configuration

`odoo-doctor.toml` sections and keys: `[odoo-doctor]` (`odoo_version`, `addons_paths`,
`target_modules`, `odoo_source_path`, `min_score`, `capabilities`), `[plugins]`
(`enabled`, `allow`), `[adapters]`, `[severity]`, `[ignore]` (`rules`, `files`,
`modules`), `[category_weights]`, `[surfaces.pr_comment]`, `[surfaces.ci_failure]` and
`[surfaces.terminal]` (`min_confidence`, `categories`, `tiers`; the terminal hides
`low` findings by default). Keys the tool does not know are currently
ignored without a warning.

### Python

Only `odoo_doctor.plugin_api` is public, versioned by `PLUGIN_API_VERSION` (see
[custom-rules.md](custom-rules.md)). A plugin states the version it targets with the
integer `ODOO_DOCTOR_PLUGIN_API` in the module its entry point names; the loader
refuses a mismatch or a non-integer value and warns when it is missing. Names are only
added to `plugin_api` within a version; removing one bumps `PLUGIN_API_VERSION` after
the deprecation window above.

## Not public

Everything else may change in any release: modules other than `plugin_api`, the graph and
parsers, the pipeline functions, the scan cache file format, finding messages and help
text, the order of findings, and the wording of terminal output.

## Changing the public surface

Contributors: if a change touches anything above, update this document and the frozen
data in `tests/test_stability_contract.py` in the same pull request, and add a
`### Deprecated` (or `### Removed`, once the window has passed) entry to the changelog.
