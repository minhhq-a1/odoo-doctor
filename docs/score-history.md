# Score history, trend and badge

Everything here is serverless: files you keep in the repo, a CI cache/artifact or
a `gh-pages` branch. No hosted service is required.

## Record every scan

```bash
odoo-doctor scan . --history .odoo-doctor/history.jsonl
```

Appends one JSON line per scan (`history_schema_version`, `score_schema_version`,
`tool_version`, UTC `timestamp`, `commit`, `branch`, project score and per-module
scores). Commit and branch come from `GITHUB_SHA` / `GITHUB_HEAD_REF` /
`GITHUB_REF_NAME` in CI, else from `git`. `--history` and `--badge` need a full
scan and are rejected together with `--diff` or `--module` / `target_modules`.

## Trend and regression alerts

```bash
odoo-doctor history show .odoo-doctor/history.jsonl --last 10
odoo-doctor history show .odoo-doctor/history.jsonl --max-drop 2   # exit 2 on regression
```

The newest scan is compared with the previous **comparable** one: same
`score_schema_version` and same branch. A drop larger than `--max-drop` points
(project or any module) is reported as `[REGRESSION]` and exits with code 2.
Without `--max-drop` drops are listed but never fail.

## Importing older data (<= 0.3.0)

Reports from odoo-doctor 0.3.0 and earlier have no `score_schema_version`:

```bash
odoo-doctor history import .odoo-doctor/history.jsonl old-report.json \
    --branch main --timestamp 2026-05-01T00:00:00Z
```

Migration strategy:

| Missing in the old report | Normalized as |
|---------------------------|---------------|
| `score_schema_version`    | `1`, with `score_schema_inferred: true` |
| `project_score`           | mean of the module scores |
| timestamp                 | `--timestamp`, else the report file's mtime |
| commit / branch           | `--commit` / `--branch`, else `null` |

Schema 1 (all category weights 1.0) and schema 2 (0.4.0+ default weights) are not
comparable: `history show` marks them (`v1*`) and regression detection never
compares across schemas.

## Score badge

```bash
odoo-doctor scan . --badge badge.svg     # self-contained SVG
odoo-doctor scan . --badge badge.json    # shields.io endpoint JSON
```

Publish the SVG anywhere (committed file, release asset, `gh-pages`), or serve the
JSON and reference it as
`https://img.shields.io/endpoint?url=<raw-url-of-badge.json>`.

Example CI step that keeps history and badge on a `gh-pages` branch:

```yaml
- run: |
    git fetch origin gh-pages:gh-pages || true
    git show gh-pages:history.jsonl > .odoo-doctor-history.jsonl 2>/dev/null || true
    odoo-doctor scan . --history .odoo-doctor-history.jsonl --badge badge.svg
    odoo-doctor history show .odoo-doctor-history.jsonl --max-drop 3
```
