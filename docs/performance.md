# Performance

How long a scan takes on a large codebase, and how to reproduce the measurement.

## Reference run (0.9.0)

Scanned: the `addons/` directory of Odoo 19.0 community (`odoo/odoo` at commit `bcb203f3`):
**636 modules**, 40 native rules, no external adapters.

Machine: Apple M5, 10 cores, Python 3.12, one process, results from a warm file system
cache.

| Scan | Wall time | Peak memory |
| --- | --- | --- |
| Whole tree, cold (no scan cache) | 47.7 s | 180 MB |
| Whole tree, `--cache`, first run | 48.4 s | |
| Whole tree, `--cache`, nothing changed | 1.6 s | |
| One module (`--module sale`) | 0.8 s | |

The run reported 7424 findings across the 636 modules and an overall score of 93.3.

Reading the numbers:

- Scanning is single-threaded and scales roughly with the amount of Python, XML and CSV
  parsed: about 75 ms per module on this tree.
- The scan cache is all-or-nothing: it is a fingerprint of every scanned file, the config,
  the Odoo version, the ruleset and the tool version. Any change rescans everything, so the
  cache helps repeated runs on an unchanged tree (re-running CI, switching reports), not
  incremental edits.
- For a pull request, `--diff <ref>` scans only the changed files, and `--module` limits a
  scan to the modules you name.
- Timings depend on the machine and are a guide, not a guarantee; there is no performance
  SLA.

## Reproduce

```bash
git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git
cd odoo/addons
/usr/bin/time -l odoo-doctor scan . --json --odoo-version 19.0 > report.json   # macOS
/usr/bin/time -v odoo-doctor scan . --json --odoo-version 19.0 > report.json   # Linux
odoo-doctor scan . --json --odoo-version 19.0 --cache > /dev/null
```

Run the cached scan twice: the second run shows the unchanged-tree time.
