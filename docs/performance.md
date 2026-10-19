# Performance

How long a scan takes on a large codebase, and how to reproduce the measurement.

## Reference run (0.9.3)

Scanned: the `addons/` directory of Odoo 19.0 community (`odoo/odoo` at commit `20f5882e`):
**636 modules**, 55 native rules, no external adapters.

Machine: Apple M5, 10 cores, Python 3.12, one process, results from a warm file system
cache.

| Scan | Wall time | Peak memory |
| --- | --- | --- |
| Whole tree, cold (no scan cache) | 72.9 s | 200 MB |
| Whole tree, `--cache`, first run | 71.1 s | |
| Whole tree, `--cache`, nothing changed | 2.0 s | |
| One module (`--module sale`) | 1.0 s | |

The timings above were measured at 0.9.3. At 0.10.1 the same tree reports 7339 findings across the 636 modules and
an overall score of 93.9 (0.9.3: 7457 findings, 93.2; the difference is the precision audit in the changelog).

The 0.9.0 reference run (47.7 s) used 40 rules on an older commit of the same tree, so the
two tables compare different work and say nothing about speed between releases.

Reading the numbers:

- Scanning is single-threaded and scales roughly with the amount of Python, XML and CSV
  parsed: about 115 ms per module on this tree.
- The scan cache is all-or-nothing: it is a fingerprint of every scanned file, the config,
  the Odoo version, the ruleset, each third-party rule plugin (installed version and a hash of
  its rule module), the `ruff` and `pylint` versions and the odoo-doctor version. Any change rescans everything, so the
  cache helps repeated runs on an unchanged tree (re-running CI, switching reports), not
  incremental edits.
- For a pull request, `--diff <ref>` scans only the changed files, and `--module` limits a
  scan to the modules you name.
- Timings depend on the machine and are a guide, not a guarantee; there is no performance
  SLA.

## Reproduce

```bash
git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git
cp -R odoo/addons odoo-addons-copy   # --cache writes .odoo_doctor_cache into the scanned tree
cd odoo-addons-copy
/usr/bin/time -l odoo-doctor scan . --json --odoo-version 19.0 > report.json   # macOS
/usr/bin/time -v odoo-doctor scan . --json --odoo-version 19.0 > report.json   # Linux
odoo-doctor scan . --json --odoo-version 19.0 --cache > /dev/null
```

Run the cached scan twice: the second run shows the unchanged-tree time.
