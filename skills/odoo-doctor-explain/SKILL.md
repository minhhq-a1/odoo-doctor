---
name: odoo-doctor-explain
description: Use when the user asks why a rule fired, wants to understand a finding, or wants to tune config.
---

# Odoo Doctor Explain & Configure

## When to use
- User asks "why did this rule fire?" or "what does this error mean?"
- User wants to disable or change severity of a rule
- User wants to understand how scoring works

## Workflow

1. Explain the rule:
   ```bash
   odoo-doctor rules explain <rule-name>
   ```

2. If the user wants to change behavior, apply the **narrowest** config change:
   - To disable for one file: use inline suppression `# odoo-doctor: disable=<rule>`
   - To change severity: add to `[severity]` in `odoo-doctor.toml`
   - To disable entirely: add to `[ignore] rules` in `odoo-doctor.toml`

3. Never disable a rule globally without discussing with the user first.

## Config location
The config file is `odoo-doctor.toml` at the repository root.
