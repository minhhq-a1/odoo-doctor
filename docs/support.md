# Support policy and compatibility matrix

What Odoo Doctor runs on, what it analyses, and how long a release is looked after.
The public surface that is kept stable is described in [stability.md](stability.md).

## Runs on

| | Supported | Tested in CI |
| --- | --- | --- |
| Python | 3.10, 3.11, 3.12, 3.13 | 3.10, 3.11, 3.12 (3.13 is declared, not yet in the CI matrix) |
| Linux | yes | full test suite |
| macOS | yes | not in CI; used by the maintainer |
| Windows | yes | language server and VS Code extension tests only |

Odoo Doctor never imports Odoo, so no Odoo installation is needed to scan.

## Analyses

| Odoo version | Native rules | Bundled model stubs |
| --- | --- | --- |
| 17.0, 18.0, 19.0 | all, version-gated where a rule needs it | yes (core models) |
| 14.0 to 16.0 | the rules gated at `14.0` or `15.0` and above | no; generate them (see [stubs.md](stubs.md)) or point `odoo_source_path` at a checkout |
| older than 14.0 | not supported | no |

Without stubs for the scanned version the symbol resolver reports fewer provable "does not
exist" findings and lowers the confidence of the ones it keeps; point `odoo_source_path`
at a source checkout for full accuracy.

The Odoo version is read from the addons or set with `odoo_version` in `odoo-doctor.toml`
or `--odoo-version`. A new Odoo major version is added by generating its stubs
(`python -m odoo_doctor.graph.stubs.build_stubs`).

## Release support (LTS policy)

Odoo Doctor has one maintainer, so the policy is deliberately small:

- **Only the latest release is supported.** Fixes ship as a new patch or minor release of
  that line; there are no long-term-support branches and no back-ports.
- **What does not break inside `0.x` and `1.x`:** the public surface in
  [stability.md](stability.md). Findings and scores may change between releases because
  rules get more precise; a scoring-formula change bumps `score_schema_version`.
- **Deprecation window:** a public name is marked *Deprecated* in `CHANGELOG.md` for at
  least one minor release before it is removed (security fixes excepted).
- **Python versions** are dropped only in a minor release and announced in the changelog.
- **Experimental features** (`odoo-doctor lsp`, the VS Code extension) are outside this
  policy until stability.md lists them.

## Reporting a problem

Open an issue on GitHub with the output of `odoo-doctor --version`, the Python version and
the command you ran. For a false positive, a minimal addon that reproduces it becomes a
case in the golden corpus (`tests/corpus/`) before the rule is changed.
