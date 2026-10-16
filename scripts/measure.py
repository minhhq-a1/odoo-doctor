#!/usr/bin/env python3
"""Repeatable precision measurement for odoo-doctor (a maintainer tool, not shipped).

Runs ``odoo-doctor scan --json`` on named targets and prints findings per
``source/rule`` x confidence. ``--snapshot`` stores every rule; ``--compare``
checks a new run against a stored one.

    .venv/bin/python scripts/measure.py \
        core19=~/Workspaces/odoo-core/19.0/addons@19.0 \
        core17as19=~/Workspaces/odoo-core/17.0/addons@19.0 \
        skw=/path/to/skw@19.0 --snapshot before.json

Targets can also come from ODOO_DOCTOR_MEASURE_TARGETS (space separated). The
scanned directories are only read. Not run in CI: the data lives on the
maintainer's machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONFIDENCES = ("high", "medium", "low")
TARGETS_ENV = "ODOO_DOCTOR_MEASURE_TARGETS"

# Rules the audit is allowed to change (spec A4). Everything else must not get
# noisier: neither more findings in total nor more `high` ones.
AUDIT_RULES = frozenset(
    {
        "manifest-missing-required-fields",
        "manifest-data-order-risk",
        "duplicate-xml-id",
        "override-missing-super",
        "sudo-without-comment",
        "missing-ondelete",
        "data-noupdate-risk",
        "dynamic-method-dispatch",
    }
)

_VERSION_SUFFIX = re.compile(r"(.*)@(\d+\.\d+)")


def parse_target(spec: str) -> tuple[str, str, str | None]:
    """``LABEL=PATH[@ODOO_VERSION]`` -> (label, path, version or None)."""
    label, sep, rest = spec.partition("=")
    if not sep or not label or not rest:
        raise ValueError(f"target must look like LABEL=PATH[@ODOO_VERSION]: {spec!r}")
    match = _VERSION_SUFFIX.fullmatch(rest)
    if match:
        return label, match.group(1), match.group(2)
    return label, rest, None


def summarize(payload: dict) -> dict:
    """Group a ``scan --json`` payload by ``source/rule`` and confidence."""
    rules: dict[str, dict[str, int]] = {}
    findings = 0
    module_scores: dict[str, float] = {}
    for name, module in payload["modules"].items():
        module_scores[name] = module["score"]["overall"]
        for d in module["diagnostics"]:
            key = f"{d['source']}/{d['rule']}"
            rules.setdefault(key, dict.fromkeys(CONFIDENCES, 0))[d["confidence"]] += 1
            findings += 1
    return {
        "modules": len(payload["modules"]),
        "findings": findings,
        "project_score": payload["project_score"]["overall"],
        "module_scores": module_scores,
        "rules": rules,
    }


def config_sha256(path: str) -> str:
    """Hash of the odoo-doctor.toml chain above *path* (outermost first); '' if none."""
    chain: list[Path] = []
    current = Path(path).expanduser().resolve()
    for _ in range(20):
        candidate = current / "odoo-doctor.toml"
        if candidate.is_file():
            chain.append(candidate)
        if current.parent == current:
            break
        current = current.parent
    if not chain:
        return ""
    digest = hashlib.sha256()
    for toml in reversed(chain):
        digest.update(toml.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_commit(path: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", path, "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _executable() -> str:
    beside = Path(sys.executable).with_name("odoo-doctor")
    if beside.exists():
        return str(beside)
    found = shutil.which("odoo-doctor")
    if not found:
        raise SystemExit("odoo-doctor is not installed in this environment")
    return found


def run_scan(path: str, odoo_version: str | None) -> tuple[dict, float]:
    cmd = [_executable(), "scan", path, "--json"]
    if odoo_version:
        cmd += ["--odoo-version", odoo_version]
    started = time.monotonic()
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    seconds = round(time.monotonic() - started, 1)
    # 1 = findings at --fail-on, 2 = score gate: neither means the scan broke.
    if done.returncode not in (0, 1, 2):
        raise SystemExit(
            f"scan failed ({done.returncode}): {done.stderr.strip()[:500]}"
        )
    return json.loads(done.stdout), seconds


def measure_target(path: str, odoo_version: str | None) -> dict:
    expanded = str(Path(path).expanduser())
    payload, seconds = run_scan(expanded, odoo_version)
    info = summarize(payload)
    info.update(
        path=expanded,
        commit=git_commit(expanded),
        odoo_version=odoo_version,
        config_sha256=config_sha256(expanded),
        seconds=seconds,
    )
    return info


def compare(
    before: dict, after: dict, audit_rules: frozenset[str] = AUDIT_RULES
) -> tuple[list[str], list[str], list[str], list[str]]:
    """(diff lines, regressions, incomparable notes, module score changes)."""
    lines: list[str] = []
    regressions: list[str] = []
    incomparable: list[str] = []
    score_changes: list[str] = []
    if before.get("tool_version") != after.get("tool_version"):
        incomparable.append(
            f"tool_version {before.get('tool_version')!r} -> {after.get('tool_version')!r}"
        )
    b_targets, a_targets = before["targets"], after["targets"]
    zero = dict.fromkeys(CONFIDENCES, 0)
    for label in sorted(set(b_targets) | set(a_targets)):
        b, a = b_targets.get(label), a_targets.get(label)
        if b is None or a is None:
            incomparable.append(
                f"{label}: only in {'after' if b is None else 'before'}"
            )
            continue
        for key in ("commit", "odoo_version", "config_sha256"):
            if b.get(key) != a.get(key):
                incomparable.append(f"{label}: {key} {b.get(key)!r} -> {a.get(key)!r}")
        for key in sorted(set(b["rules"]) | set(a["rules"])):
            rb, ra = b["rules"].get(key, zero), a["rules"].get(key, zero)
            deltas = [f"{c} {rb[c]}->{ra[c]}" for c in CONFIDENCES if rb[c] != ra[c]]
            if not deltas:
                continue
            lines.append(f"{label} {key}: " + ", ".join(deltas))
            if key.split("/", 1)[1] in audit_rules:
                continue
            total_b, total_a = sum(rb.values()), sum(ra.values())
            if total_a > total_b:
                regressions.append(f"{label} {key}: total {total_b} -> {total_a}")
            if ra["high"] > rb["high"]:
                regressions.append(f"{label} {key}: high {rb['high']} -> {ra['high']}")
        sb, sa = b.get("module_scores", {}), a.get("module_scores", {})
        for module in sorted(set(sb) | set(sa)):
            if sb.get(module) != sa.get(module):
                old = sb.get(module, "absent")
                new = sa.get(module, "absent")
                score_changes.append(f"{label} {module}: {old} -> {new}")
    return lines, regressions, incomparable, score_changes


def format_table(label: str, info: dict, only: set[str] | None, top: int = 20) -> str:
    rules = info["rules"]
    keys = sorted(rules, key=lambda k: (-sum(rules[k].values()), k))
    if only:
        keys = [k for k in keys if k.split("/", 1)[1] in only]
    else:
        keys = keys[:top]
    head = (
        f"== {label}: {info['modules']} modules, {info['findings']} findings, "
        f"score {info['project_score']}, {info['seconds']} s, commit {info['commit']}, "
        f"odoo {info['odoo_version']}"
    )
    out = [head, f"{'rule':52s}{'high':>7s}{'medium':>8s}{'low':>7s}"]
    for key in keys:
        r = rules[key]
        out.append(f"{key:52s}{r['high']:7d}{r['medium']:8d}{r['low']:7d}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("targets", nargs="*", help="LABEL=PATH[@ODOO_VERSION]")
    parser.add_argument("--rules", help="comma separated rules to print (display only)")
    parser.add_argument("--snapshot", help="write the result (every rule) to this file")
    parser.add_argument("--compare", help="compare with this earlier snapshot")
    args = parser.parse_args(argv)

    specs = args.targets or os.environ.get(TARGETS_ENV, "").split()
    if not specs:
        parser.error(f"give at least one target or set {TARGETS_ENV}")
    try:
        parsed = [parse_target(s) for s in specs]
    except ValueError as exc:
        parser.error(str(exc))

    from odoo_doctor import __version__

    result = {"tool_version": __version__, "targets": {}}
    only = set(args.rules.split(",")) if args.rules else None
    for label, path, version in parsed:
        info = measure_target(path, version)
        result["targets"][label] = info
        print(format_table(label, info, only))
        print()

    if args.snapshot:
        Path(args.snapshot).write_text(json.dumps(result, indent=2) + "\n")
        print(f"snapshot written to {args.snapshot}")

    status = 0
    if args.compare:
        before = json.loads(Path(args.compare).read_text())
        lines, regressions, incomparable, score_changes = compare(before, result)
        for note in incomparable:
            print(f"INCOMPARABLE {note}")
        for line in lines:
            print(f"DIFF {line}")
        for line in score_changes:
            print(f"SCORE {line}")
        for line in regressions:
            print(f"REGRESSION {line}")
        if regressions:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
