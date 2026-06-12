# Odoo Doctor v0.3.0 Product Review & Announcement Guide

As part of wrapping up v0.3.0, here is a strategic breakdown of what features to spotlight in your release announcement and which ones to clearly mark as experimental or opt-in.

## 🚀 Key Highlights (What to Announce Loudly)

These features provide immediate, tangible value to users and should be the core focus of the v0.3.0 release notes:

1. **Auto-Fix Engine (`--fix`)**:
   - **Why it matters:** Odoo Doctor isn't just pointing out problems anymore; it's actively fixing them. Mention that this engine is strictly *non-destructive* and *deterministic*, safely handling boilerplate issues like missing manifest fields or incorrect data loading order.

2. **Incremental Caching (`--cache`)**:
   - **Why it matters:** Drastically cuts down scan times in CI and local workflows. Odoo Doctor is now smart enough to skip unmodified files by relying on a robust content-hashing fingerprint system.

3. **Baseline Filtering (`--baseline`)**:
   - **Why it matters:** This is the killer feature for adopting Odoo Doctor in massive, legacy codebases. Teams can now "freeze" their existing technical debt and ensure their CI pipeline only fails on *net-new* violations. Highlight the "line-independent" stability of the baseline.

4. **SARIF Output for GitHub Code Scanning (`--format sarif`)**:
   - **Why it matters:** First-class integration with GitHub Security and advanced IDEs. Security findings will now show up directly in PR diffs and Security tabs seamlessly.

5. **Smarter AST Heuristics & 9 New Rules**:
   - **Why it matters:** False negatives have been slashed. Emphasize that the analyzer is now smart enough to track loop variables (`for rec in self: rec.write()`) and properly identify performance bottlenecks. Mention the new rule coverage across Security, Performance, and Correctness.

---

## 🧪 Experimental & Opt-In (What to Caveat)

These features are powerful but intentionally restricted or in early stages. They should be documented clearly as "Opt-In" or "Experimental" to set correct expectations:

1. **Custom Rule Plugins (Opt-In / Experimental)**:
   - **How to frame it:** We are opening the ecosystem to third-party developers via the `odoo_doctor.rules` entry point. 
   - **The Caveat:** Emphasize that this is **OFF by default**. Because plugins execute Python code within the scanner's memory space (not sandboxed), users must explicitly opt-in via `[plugins].enabled = true` in their config. The rule authoring contract (`docs/custom-rules.md`) is also considered *experimental* and may change in v0.4.0.

2. **Auto-Fix Engine (`--fix-dry-run`)**:
   - **How to frame it:** While `--fix` is stable for the currently implemented rules (like manifest fixes), the framework itself is new. Users are highly encouraged to use `--fix-dry-run` to preview the diffs or run `--fix` on a clean git branch so they can review the automated changes before committing.

3. **Baseline Identity Hashes**:
   - **How to frame it:** Mention that while baseline hashes are line-independent and resilient to nearby changes, heavily refactoring the *target line itself* might cause the finding to be treated as "new". This is standard behavior for static analysis baselines, but good to clarify.
