# Contributing to Odoo Doctor

First off, thank you for considering contributing to Odoo Doctor! This project aims to bring fast, reliable, and confidence-aware static analysis to the Odoo ecosystem. We welcome all contributions, from bug reports to new rules and adapters.

## Development Setup

Odoo Doctor is a standard Python package. We recommend developing in a virtual environment.

```bash
git clone https://github.com/minhhq-a1/odoo-doctor
cd odoo-doctor
pip install -e ".[dev]"
pip install "ruff>=0.16,<0.17"   # not in the dev extra, but CI runs it
```

Python 3.10 to 3.13 is supported.

## Running Tests

We use `pytest` for testing. Ensure your changes don't break existing behavior.

```bash
# Run all tests (what CI runs)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest

# Run tests with coverage
pytest --cov=odoo_doctor
```

Our testing philosophy emphasizes Test-Driven Development (TDD) for new rules. Always write tests that cover both positive and negative cases. See the `tests/rules/` directory for examples of how we use `ModuleContext` fixtures to simulate Odoo addons.

### Golden corpus

`tests/corpus/` holds tiny sample addons that `tests/test_golden_corpus.py` scans end to end and compares with an `expected.json` (`[rule, file, confidence]` per finding). It guards true positives and known false positives. When a real scan shows a false positive, reduce it to a corpus case first, then change the rule. After an intentional rule change, review the diff and refresh with `UPDATE_GOLDEN=1 pytest tests/test_golden_corpus.py`.

## Linting and Formatting

We use `ruff` to enforce code quality and formatting.

```bash
# Check for linting errors
ruff check src tests

# Auto-format code
ruff format src tests
```

Please ensure your code passes both `ruff format --check src tests` and `ruff check src tests` before opening a Pull Request.

## Adding a New Rule

1. Check `docs/custom-rules.md` for the `@rule` decorator contract.
2. Write a failing test in `tests/rules/`.
3. Implement the rule in `src/odoo_doctor/rules/`.
4. Ensure the test passes.
5. Document the rule: add an entry to `RULE_DOCS` in `src/odoo_doctor/rules/rule_docs.py`, then run `odoo-doctor rules docs --out docs/rules.md`. Never edit `docs/rules.md` by hand; `tests/test_rule_docs_complete.py` fails if an entry is missing or the page is stale.
6. Add an effort (1 mechanical, 2 local code change, 3 restructuring) for the rule to `EFFORT_BY_RULE` in `src/odoo_doctor/core/roi.py`; a test fails otherwise.
7. Import the rule module in `src/odoo_doctor/cli/app.py`; rules register by import, so a file that is not imported never runs.

## Changing the Public Surface

CLI flags, exit codes, JSON keys, rule IDs, config keys and `odoo_doctor.plugin_api` are
covered by [`docs/stability.md`](docs/stability.md). Removing or renaming any of them fails
`tests/test_stability_contract.py`. If a change is intentional, follow the deprecation
policy in that document, update it and the frozen data in the test in the same PR, and add
a `### Deprecated` entry to `CHANGELOG.md`. Adding new names never needs this.

## Commit and PR Workflow

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(rules): add no-print-statements rule`
- `fix(core): resolve crash on malformed XML`
- `docs: update readme with sarif usage`

Open a PR against the `main` branch. GitHub Actions will run the test suite and lints automatically.

## Good First Issues

Looking for a place to start? Try one of these:

- **Add a fixture for rule Y**: Find a rule in `tests/rules/` that has minimal coverage and add more complex test cases.
- **Reduce a false positive to a corpus case**: Scan a real addon, find a finding that is wrong, and add the smallest sample that reproduces it to `tests/corpus/`.
- **Expand stub generation**: Add support for scraping more complex model relationships in `odoo_doctor.graph.stubs`.
