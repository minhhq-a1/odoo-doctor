# src/odoo_doctor/core/history.py
"""Score history: an append-only JSONL file, trend and regression detection.

Serverless by design: the file can live in the repo, a CI cache/artifact or a
gh-pages branch. Each line is one scan of the whole project.

Backward compatibility (ingestion strategy)
-------------------------------------------
Reports written by odoo-doctor <= 0.3.0 carry no ``score_schema_version``. They
are normalized, never rejected:

* missing ``score_schema_version``  -> 1 (``score_schema_inferred: true``);
* missing ``project_score``         -> mean of the module scores;
* missing timestamp/commit/branch   -> supplied by the caller, else ``None``.

Scores of different schema versions are not comparable (0.4.0 introduced default
category weights), so the trend shows them but regression detection only ever
compares records that share a ``score_schema_version``.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from odoo_doctor.core.scoring import (
    SCORE_SCHEMA_VERSION,
    ScoreResult,
    project_score,
    score_label,
)

HISTORY_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_utc_iso(value: str) -> str:
    """Parse an ISO-8601 timestamp (naive = UTC) into canonical UTC form."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def git_info(cwd: Path) -> dict[str, str | None]:
    """Best-effort commit/branch; CI environment variables win over git."""

    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return out.stdout.strip() or None if out.returncode == 0 else None

    commit = os.environ.get("GITHUB_SHA") or run("rev-parse", "HEAD")
    branch = (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or run("rev-parse", "--abbrev-ref", "HEAD")
    )
    if branch == "HEAD":  # detached
        branch = None
    return {"commit": commit, "branch": branch}


def build_record(
    scores: dict[str, ScoreResult],
    *,
    tool_version: str,
    commit: str | None = None,
    branch: str | None = None,
    timestamp: str | None = None,
) -> dict:
    return {
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "score_schema_version": SCORE_SCHEMA_VERSION,
        "tool_version": tool_version,
        "timestamp": timestamp or utc_now_iso(),
        "commit": commit,
        "branch": branch,
        "project": project_score(scores),
        "modules": {
            name: {"overall": s.overall, "label": s.label}
            for name, s in sorted(scores.items())
        },
    }


def _num(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_report(
    report: dict,
    *,
    commit: str | None = None,
    branch: str | None = None,
    timestamp: str | None = None,
) -> dict | None:
    """Turn a ``scan --json`` report of ANY odoo-doctor version into a record.

    Returns None when the report holds no scored module.
    """
    modules_raw = report.get("modules")
    if not isinstance(modules_raw, dict):
        return None
    modules: dict[str, dict] = {}
    for name, entry in modules_raw.items():
        score = entry.get("score") if isinstance(entry, dict) else None
        overall = score.get("overall") if isinstance(score, dict) else None
        if _num(overall):
            modules[str(name)] = {
                "overall": float(overall),
                "label": score.get("label") or score_label(float(overall)),
            }
    if not modules:
        return None

    ps = report.get("project_score")
    if isinstance(ps, dict) and _num(ps.get("overall")):
        overall = round(float(ps["overall"]), 1)
    else:
        overall = round(sum(m["overall"] for m in modules.values()) / len(modules), 1)

    declared = report.get("score_schema_version")
    inferred = not isinstance(declared, int) or isinstance(declared, bool)
    record = {
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "score_schema_version": 1 if inferred else declared,
        "tool_version": report.get("version")
        if isinstance(report.get("version"), str)
        else None,
        "timestamp": timestamp or utc_now_iso(),
        "commit": commit,
        "branch": branch,
        "project": {
            "overall": overall,
            "label": score_label(overall),
            "module_count": len(modules),
        },
        "modules": dict(sorted(modules.items())),
        "normalized_from": "report",
    }
    if inferred:
        record["score_schema_inferred"] = True
    return record


def normalize_record(raw: object) -> dict | None:
    """Accept a history record or a raw scan report; None if unusable."""
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("history_schema_version"), int):
        project = raw.get("project")
        if (
            isinstance(project, dict)
            and _num(project.get("overall"))
            and isinstance(raw.get("timestamp"), str)
        ):
            record = dict(raw)
            record.setdefault("modules", {})
            if not isinstance(record.get("score_schema_version"), int):
                record["score_schema_version"] = 1
                record["score_schema_inferred"] = True
            return record
        return None
    return normalize_report(raw)


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _sort_key(record: dict) -> str:
    try:
        return to_utc_iso(record["timestamp"])
    except (KeyError, ValueError, TypeError):
        return ""


def load_history(path: Path) -> tuple[list[dict], int]:
    """Read a JSONL history. Returns (records sorted by time, skipped_lines).

    Corrupt or unusable lines are skipped and counted, never fatal.
    """
    records: list[dict] = []
    skipped = 0
    if not path.exists():
        return records, skipped
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = normalize_record(json.loads(line))
        except ValueError:
            record = None
        if record is None:
            skipped += 1
        else:
            records.append(record)
    records.sort(key=_sort_key)  # stable: ties keep file order
    return records, skipped


def detect_regressions(records: list[dict], max_drop: float = 0.0) -> list[dict]:
    """Compare the newest record with the previous *comparable* one.

    Comparable = same ``score_schema_version`` and same branch. Returns one entry
    per scope ("project" or a module name) whose score dropped by more than
    ``max_drop`` points: ``{scope, previous, latest, drop}``.
    """
    if len(records) < 2:
        return []
    latest = records[-1]
    previous = next(
        (
            r
            for r in reversed(records[:-1])
            if r.get("score_schema_version") == latest.get("score_schema_version")
            and r.get("branch") == latest.get("branch")
        ),
        None,
    )
    if previous is None:
        return []

    pairs: list[tuple[str, float, float]] = [
        ("project", previous["project"]["overall"], latest["project"]["overall"])
    ]
    previous_modules = previous.get("modules", {})
    for name, mod in latest.get("modules", {}).items():
        old = previous_modules.get(name)
        old_val = old.get("overall") if isinstance(old, dict) else None
        new_val = mod.get("overall") if isinstance(mod, dict) else None
        if _num(old_val) and _num(new_val):
            pairs.append((name, old_val, new_val))

    found = []
    for scope, old, new in pairs:
        drop = round(old - new, 1)
        if drop > max_drop:
            found.append({"scope": scope, "previous": old, "latest": new, "drop": drop})
    return found


def tail(records: Iterable[dict], last: int) -> list[dict]:
    items = list(records)
    return items[-last:] if last > 0 else items
