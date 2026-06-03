---
name: odoo-doctor
description: Use after editing Odoo addon code or when asked to scan, fix, or check module health.
---

# Odoo Doctor Scan & Fix

## When to use
- After making changes to Odoo addon code
- When the user asks to "scan", "check", "fix diagnostics", or "check module health"
- Before committing Odoo code changes

## Workflow

1. Run scan on changed files:
   ```bash
   odoo-doctor scan . --diff main --json
   ```

2. Parse the JSON output and prioritize findings:
   - Fix P0 (critical) issues first — these are security or install-blocking
   - Then P1 (serious) — broken views, missing access, ORM misuse
   - P2 and P3 can be noted but are lower priority

3. For each finding, read the `help` field for fix guidance.

4. After fixing, re-run the scan to verify:
   ```bash
   odoo-doctor scan . --diff main --json
   ```

5. Repeat until no P0/P1 findings remain.

## Important
- Only fix findings with `confidence: "high"`. Low-confidence findings may be false positives.
- Do not suppress rules without asking the user first.
- If a finding seems wrong, run `odoo-doctor rules explain <rule-name>` before suppressing.
