# Odoo Doctor v0.3.0 PR Summary

This release brings monumental improvements to Odoo Doctor across performance, integrations, and automated remediations. The work was divided into 6 strategic plans:

- **Plan 01: Preflight & Foundation**
  - Resolved path resolution bugs (`_matches_any_glob`).
  - Added `Frontend` to `CATEGORIES` and fixed the README scoring formula to align with implementation.
  - Made testing fixtures branch-independent for robust CI runs.

- **Plan 02: Auto-Fix Engine**
  - Introduced `FixResult` for deterministic, non-destructive file modifications.
  - Wired the `--fix` and `--fix-dry-run` CLI flags to safely apply automated fixes (e.g., filling missing manifest fields, fixing data loading order).
  - Aligned path resolution to ensure diffs render uniformly as posix paths relative to the scan root.

- **Plan 03: 9 New Rules & AST Upgrades**
  - Added 9 new native rules (all v0.3.0): `create-in-loop`, `write-in-loop`, `eval-usage`, `orphan-view`, `record-rule-without-domain`, `field-no-string-on-required`, `missing-translation`, `n-plus-one-read`, `sudo-without-comment`. (Note: `manifest-data-order-risk` is v0.2.0 and unchanged.)
  - Upgraded AST heuristics (`receiver_is_orm`) to track loop variables originating from ORM recordsets, fixing false negatives in `write-in-loop` and related rules.

- **Plan 04: Scanner Extraction & Caching**
  - Refactored core orchestration logic out of the CLI layer and into a reusable `core/scanner.py`.
  - Built `ScanCache` and wired the `--cache` flag, utilizing content-hash fingerprinting to skip unmodified files and dramatically speed up subsequent scans.

- **Plan 05: SARIF Reporter & Baseline Filtering**
  - Built the `SARIF 2.1.0` formatter (`--format sarif`) to seamlessly hook into GitHub Code Scanning and advanced IDE workflows.
  - Implemented Baseline mode (`--baseline` and `--write-baseline`) using line-independent identity hashes to grandfather in pre-existing technical debt and strictly fail CI only on net-new issues.

- **Plan 06: Ecosystem & Custom Plugins**
  - Shipped a plugin discovery skeleton utilizing Python's entry points (`odoo_doctor.rules` group) to allow third-party packages to inject custom rules.
  - Gated the plugin loader behind an explicit `[plugins].enabled = true` configuration for security.
  - Wrote a robust `CONTRIBUTING.md` and a custom-rules authoring guide for community adoption.
  - Added strict completeness guards (`test_rule_docs_complete.py`) to ensure all native rules are properly documented.
