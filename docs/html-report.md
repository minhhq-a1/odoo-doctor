# HTML report

`odoo-doctor scan --html report.html` writes one self-contained file you can open in a browser
or keep as a CI artifact. It needs no server and makes no network request.

```bash
odoo-doctor scan . --html report.html                 # report only
odoo-doctor scan . --format sarif --html report.html  # SARIF on stdout, report in a file
odoo-doctor scan . --history history.jsonl --html report.html   # adds the score trend
```

The file holds the score, a module × category table, the fixes ranked by score gain, a
filterable list of findings (low-confidence findings are hidden until you switch them on),
suppression counts and, with `--history`, a score trend. A partial scan (`--diff`, `--module`)
or a baseline is announced at the top of the page. The page does not read `[surfaces.terminal]`;
that setting only affects the terminal output.

Notes:

- The data embedded in the page is the `scan --json` payload. If the file would exceed
  10 MiB, the low-confidence findings are left out of the page (the scores do not change)
  and the page says how many; use `--json` for the full list. If the file is still over
  10 MiB after that, all high- and medium-confidence findings are kept, the file is written
  anyway, a warning goes to stderr and the exit code is unchanged. Only a very large
  codebase is expected to reach this size: a scan of 271 modules and 2479 findings wrote a
  2.2 MiB file.
- Low-confidence findings are hidden by default and a checkbox on the page shows them.
- The page text is in English, whatever the language of your repository.
- The page is protected by a Content-Security-Policy that allows only its own inline script
  and style (pinned by sha256 hash), and it renders every value from your repository as text.
- Writing the file fails with exit code 3 when the path is not writable, or when the packaged
  report assets are missing from the installation (reinstall odoo-doctor). The scan's other
  exit codes (`--fail-on`, `--min-score`) are not affected by `--html`.
- If no addon is found, no file is written (a note goes to stderr). A `--baseline` that hides
  every finding of the project currently also ends in "No addons found" (the scoring step
  returns no module), so no report is written in that case either.
- Finding paths are always embedded as resolved absolute paths, exactly as in `scan --json`,
  whatever form the scan target has, and the `--baseline` argument is embedded as you typed
  it. A report shared outside your team therefore reveals the directory layout of the machine
  that scanned (a home directory or a CI runner path). Generate it in CI, where that layout is
  not sensitive, when the report will be shared.

## CI recipes

**GitHub Actions**

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: pip install odoo-doctor
- run: odoo-doctor scan . --html odoo-doctor-report.html
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: odoo-doctor-report
    path: odoo-doctor-report.html
```

**GitLab CI**

```yaml
odoo-doctor:
  image: python:3.12
  script:
    - pip install odoo-doctor
    - odoo-doctor scan . --html odoo-doctor-report.html
  artifacts:
    when: always
    expose_as: "Odoo Doctor report"
    paths:
      - odoo-doctor-report.html
```

**Bitbucket Pipelines**

```yaml
- step:
    image: python:3.12
    script:
      - pip install odoo-doctor
      - odoo-doctor scan . --html odoo-doctor-report.html
    artifacts:
      - odoo-doctor-report.html
```
