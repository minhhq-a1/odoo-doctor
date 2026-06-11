# Contributing to Odoo Doctor

First off, thank you for considering contributing to Odoo Doctor! This project aims to bring fast, reliable, and confidence-aware static analysis to the Odoo ecosystem. We welcome all contributions, from bug reports to new rules and adapters.

## Development Setup

Odoo Doctor is a standard Python package. We recommend developing in a virtual environment.

```bash
git clone https://github.com/minhhq-a1/odoo-doctor
cd odoo-doctor
pip install -e ".[dev]"
```

## Running Tests

We use `pytest` for testing. Ensure your changes don't break existing behavior.

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=odoo_doctor
```

Our testing philosophy emphasizes Test-Driven Development (TDD) for new rules. Always write tests that cover both positive and negative cases. See the `tests/rules/` directory for examples of how we use `ModuleContext` fixtures to simulate Odoo addons.

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
5. Add your new rule to `docs/rules.md`. Our completeness guard test (`tests/test_rule_docs_complete.py`) will fail if you forget!

## Commit and PR Workflow

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(rules): add no-print-statements rule`
- `fix(core): resolve crash on malformed XML`
- `docs: update readme with sarif usage`

Open a PR against the `main` branch. GitHub Actions will run the test suite and lints automatically.

## Good First Issues

Looking for a place to start? Try one of these:

- **Add a fixture for rule Y**: Find a rule in `tests/rules/` that has minimal coverage and add more complex test cases.
- **Implement `unsafe-template-render`**: A rule to detect unsafe rendering in QWeb templates (deferred from v0.3.0).
- **Expand stub generation**: Add support for scraping more complex model relationships in `odoo_doctor.graph.stubs`.
