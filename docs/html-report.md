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
or a baseline is announced at the top of the page.

Notes:

- The data embedded in the page is the `scan --json` payload. If the file would exceed
  10 MiB, the low-confidence findings are left out of the page (the scores do not change)
  and the page says how many; use `--json` for the full list. If the file is still over
  10 MiB after that, all high- and medium-confidence findings are kept, the file is written
  anyway, a warning goes to stderr and the exit code is unchanged. A scan of a very large
  codebase (for example Odoo core) can reach this size.
- Low-confidence findings are hidden by default and a checkbox on the page shows them. The
  page does not read `[surfaces.terminal]`; that setting only affects the terminal output.
- The page text is in English, whatever the language of your repository.
- The page is protected by a Content-Security-Policy that allows only its own inline script
  and style (pinned by sha256 hash), and it renders every value from your repository as text.
- Writing the file fails with exit code 3 when the path is not writable, or when the packaged
  report assets are missing from the installation (reinstall odoo-doctor). The scan's other
  exit codes (`--fail-on`, `--min-score`) are not affected by `--html`.
- If no addon is found, no file is written (a note goes to stderr).

## CI recipes

**GitHub Actions**

```yaml
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
  script:
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
    script:
      - pip install odoo-doctor
      - odoo-doctor scan . --html odoo-doctor-report.html
    artifacts:
      - odoo-doctor-report.html
```
