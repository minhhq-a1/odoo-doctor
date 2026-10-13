---
name: release
description: Use when cutting an odoo-doctor release - bumping the version, updating the changelog, tagging, publishing to PyPI and the VS Code Marketplace.
---

# Releasing odoo-doctor

1. Bump the version in `pyproject.toml`, `src/odoo_doctor/__init__.py` (read by the JSON report), `README.md` (including the `minhhq-a1/odoo-doctor@vX.Y.Z` action example), `CLAUDE.md` (the `Current version` line) and `AGENTS.md`, plus both `version` fields of `editors/vscode/package.json` and `package-lock.json`. `tests/test_version.py` enforces pyproject == `__version__` and that `CHANGELOG.md` has a `## [X.Y.Z]` entry; `tests/test_vscode_extension.py` enforces the extension version; the README/CLAUDE/AGENTS bumps are not tested.
2. Update `CHANGELOG.md`; regenerate `docs/rules.md` if rules changed.
3. Merge to `main`, then `git tag vX.Y.Z && git push origin vX.Y.Z` and create a GitHub Release — `.github/workflows/publish.yml` publishes to PyPI via Trusted Publishing.
4. VS Code extension (not automated, needs the publisher's token): after the PyPI release, publish the same version from `main` with `cd editors/vscode && npm ci && npx vsce publish`, or upload the `.vsix` that `npm run package` builds at https://marketplace.visualstudio.com/manage/publishers/MinhHong. Never put the token in the repo or in chat.
