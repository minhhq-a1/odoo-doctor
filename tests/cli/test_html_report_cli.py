"""scan --html: file written beside the normal output, errors, scope and ordering."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG = '[odoo-doctor]\nodoo_version = "17.0"\n[adapters]\nruff = false\npylint_odoo = false\n'


def _project(root: Path, *, bad: bool) -> Path:
    mod = root / "addons" / "m"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        "{'name': 'M', 'version': '17.0.1.0.0', 'depends': ['base'], 'data': [], "
        "'installable': True, 'license': 'LGPL-3'}"
    )
    (mod / "x.py").write_text(
        'def f(self, name):\n    self.env.cr.execute(f"SELECT {name}")\n'
        if bad
        else "def f(self):\n    return 1\n"
    )
    (root / "odoo-doctor.toml").write_text(CONFIG)
    return root / "addons"


def _scan(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """The real command in a real process, so stdout and stderr stay separate."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from odoo_doctor.cli.app import app; app()",
            "scan",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _envelope(path: Path) -> dict:
    html = path.read_text(encoding="utf-8")
    m = re.search(
        r'<script type="application/json" id="od-data">(.*?)</script>', html, re.DOTALL
    )
    assert m
    return json.loads(m.group(1))


def _git_init(repo: Path) -> None:
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "T"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "init"],
    ):
        subprocess.run(cmd, cwd=repo, check=True)


def test_html_is_written_and_stdout_is_unchanged(tmp_path: Path):
    addons = _project(tmp_path, bad=True)
    report = tmp_path / "out" / "report.html"

    plain = _scan(tmp_path, str(addons), "--json")
    with_html = _scan(tmp_path, str(addons), "--json", "--html", str(report))

    assert plain.returncode == with_html.returncode == 0
    assert with_html.stdout == plain.stdout
    assert f"Wrote HTML report to {report}" in with_html.stderr
    assert "Wrote HTML report" not in with_html.stdout
    env = _envelope(report)
    expected = json.loads(plain.stdout)
    # only paths differ: the page shows them relative to the scan root
    for mod in expected["modules"].values():
        for d in mod["diagnostics"]:
            d["file_path"] = (
                Path(d["file_path"]).relative_to(addons.resolve()).as_posix()
            )
        for d in mod["fix_priorities"]:
            d["file_path"] = (
                Path(d["file_path"]).relative_to(addons.resolve()).as_posix()
            )
    for d in expected["top_findings"]:
        d["file_path"] = Path(d["file_path"]).relative_to(addons.resolve()).as_posix()
    assert env["report"] == expected
    assert env["meta"]["project"] == addons.name  # the scanned folder
    assert env["meta"]["scope"] == {"partial": False, "diff": None, "modules": []}
    assert env["history"] is None


def test_module_scan_is_marked_partial(tmp_path: Path):
    addons = _project(tmp_path, bad=False)
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(addons), "--module", "m", "--html", str(report))
    assert done.returncode == 0
    assert _envelope(report)["meta"]["scope"] == {
        "partial": True,
        "diff": None,
        "modules": ["m"],
    }


def test_history_trend_includes_the_current_scan(tmp_path: Path):
    addons = _project(tmp_path, bad=False)
    hist = tmp_path / "h.jsonl"
    report = tmp_path / "r.html"
    first = _scan(tmp_path, str(addons), "--history", str(hist), "--html", str(report))
    assert first.returncode == 0
    assert len(_envelope(report)["history"]) == 1  # new file: this scan only
    _project(tmp_path, bad=True)
    _scan(tmp_path, str(addons), "--history", str(hist), "--html", str(report))
    env = _envelope(report)
    assert len(env["history"]) == 2
    assert env["history"][1]["project"] < env["history"][0]["project"]


def test_corrupt_history_lines_are_skipped_and_counted(tmp_path: Path):
    addons = _project(tmp_path, bad=False)
    hist = tmp_path / "h.jsonl"
    hist.write_text("not json\n{}\n")
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(addons), "--history", str(hist), "--html", str(report))
    assert done.returncode == 0
    env = _envelope(report)
    assert env["history_skipped"] == 2 and len(env["history"]) == 1


def test_undecodable_and_non_finite_history_never_break_the_report(tmp_path: Path):
    addons = _project(tmp_path, bad=False)
    hist = tmp_path / "h.jsonl"
    hist.write_bytes(
        b"\xff\n"
        b'{"history_schema_version":1,"timestamp":"2026-02-01T00:00:00+00:00",'
        b'"project":{"overall":1e309}}\n'
        b'{"history_schema_version":1,"timestamp":"2026-03-01T00:00:00+00:00",'
        b'"project":{"overall":1' + b"0" * 309 + b"}}\n"
    )
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(addons), "--history", str(hist), "--html", str(report))
    assert done.returncode == 0, done.stderr
    env = _envelope(report)  # json.loads would also accept Infinity, so check the text
    assert env["history_skipped"] == 3 and len(env["history"]) == 1
    assert "Infinity" not in report.read_text(encoding="utf-8")


def test_baseline_is_named_in_meta_and_hides_known_findings(tmp_path: Path):
    addons = _project(tmp_path, bad=True)
    base = tmp_path / "baseline.json"
    _scan(tmp_path, str(addons), "--write-baseline", str(base))
    # a new finding that the baseline does not know
    (addons / "m" / "y.py").write_text(
        'def g(self, name):\n    self.env.cr.execute(f"SELECT {name}")\n'
    )
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(addons), "--baseline", str(base), "--html", str(report))
    assert done.returncode == 0
    env = _envelope(report)
    assert env["meta"]["baseline"] == str(base)
    assert env["truncated"]["findings_total"] == 1
    only = env["report"]["modules"]["m"]["diagnostics"]
    assert len(only) == 1 and only[0]["file_path"].endswith("y.py")


def test_baseline_that_hides_everything_writes_no_report(tmp_path: Path):
    # Existing behaviour: with no finding left, scoring returns no module and scan
    # takes its "no addons" exit, so there is no report to write.
    addons = _project(tmp_path, bad=True)
    base = tmp_path / "baseline.json"
    _scan(tmp_path, str(addons), "--write-baseline", str(base))
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(addons), "--baseline", str(base), "--html", str(report))
    assert done.returncode == 0
    assert not report.exists()
    assert "HTML report not written" in done.stderr


def test_write_baseline_exits_early_without_a_report(tmp_path: Path):
    addons = _project(tmp_path, bad=True)
    report = tmp_path / "r.html"
    done = _scan(
        tmp_path,
        str(addons),
        "--write-baseline",
        str(tmp_path / "b.json"),
        "--html",
        str(report),
    )
    assert done.returncode == 0 and not report.exists()


def test_no_addons_writes_no_report_and_says_so(tmp_path: Path):
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(tmp_path), "--html", str(report))
    assert done.returncode == 0
    assert not report.exists()
    assert "HTML report not written" in done.stderr


def test_unwritable_target_exits_3_with_empty_stdout(tmp_path: Path):
    addons = _project(tmp_path, bad=True)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    for target in (tmp_path, blocker / "r.html"):  # a directory; a path under a file
        done = _scan(tmp_path, str(addons), "--html", str(target))
        assert done.returncode == 3, target
        assert done.stdout == ""
        assert "cannot write HTML report" in done.stderr


def test_exit_codes_of_scan_are_not_changed_by_html(tmp_path: Path):
    addons = _project(tmp_path, bad=True)  # one P0 high finding (raw SQL)
    report = tmp_path / "r.html"
    assert _scan(tmp_path, str(addons)).returncode == 0
    assert _scan(tmp_path, str(addons), "--html", str(report)).returncode == 0
    gated = _scan(tmp_path, str(addons), "--fail-on", "warning", "--html", str(report))
    assert gated.returncode == 1
    scored = _scan(tmp_path, str(addons), "--min-score", "100", "--html", str(report))
    assert scored.returncode == 2


def test_oversize_report_warns_and_keeps_every_exit_code(tmp_path: Path, monkeypatch):
    # In-process run so the threshold can be lowered.
    from typer.testing import CliRunner

    from odoo_doctor.cli.app import app
    from odoo_doctor.reporters import html_report

    addons = _project(tmp_path, bad=True)  # only a high finding: nothing to drop
    monkeypatch.setattr(html_report, "MAX_HTML_BYTES", 10)
    report = tmp_path / "r.html"
    runner = CliRunner()

    plain = runner.invoke(app, ["scan", str(addons), "--html", str(report)])
    assert plain.exit_code == 0
    assert "above 10" in plain.output
    assert "all high/medium findings are kept" in plain.output
    assert _envelope(report)["truncated"]["low_findings"] == 0

    gated = runner.invoke(
        app, ["scan", str(addons), "--html", str(report), "--fail-on", "warning"]
    )
    assert gated.exit_code == 1
    scored = runner.invoke(
        app, ["scan", str(addons), "--html", str(report), "--min-score", "100"]
    )
    assert scored.exit_code == 2


def test_diff_scan_is_marked_partial(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    addons = _project(repo, bad=True)
    _git_init(repo)
    report = tmp_path / "r.html"
    done = _scan(repo, str(addons), "--diff", "main", "--html", str(report))
    assert done.returncode == 0
    scope = _envelope(report)["meta"]["scope"]
    assert scope == {"partial": True, "diff": "main", "modules": []}


def test_target_modules_from_config_are_marked_partial(tmp_path: Path):
    addons = _project(tmp_path, bad=False)
    (tmp_path / "odoo-doctor.toml").write_text(
        CONFIG.replace(
            'odoo_version = "17.0"\n', 'odoo_version = "17.0"\ntarget_modules = ["m"]\n'
        )
    )
    report = tmp_path / "r.html"
    done = _scan(tmp_path, str(addons), "--html", str(report))
    assert done.returncode == 0
    scope = _envelope(report)["meta"]["scope"]
    assert scope == {"partial": True, "diff": None, "modules": ["m"]}


def test_cached_second_run_gives_the_same_report(tmp_path: Path):
    addons = _project(tmp_path, bad=True)
    first, second = tmp_path / "a.html", tmp_path / "b.html"
    assert _scan(tmp_path, str(addons), "--cache", "--html", str(first)).returncode == 0
    assert (
        _scan(tmp_path, str(addons), "--cache", "--html", str(second)).returncode == 0
    )
    assert _envelope(second)["report"] == _envelope(first)["report"]


def test_missing_assets_exit_3_with_a_reinstall_hint(tmp_path: Path, monkeypatch):
    from typer.testing import CliRunner

    from odoo_doctor.cli.app import app
    from odoo_doctor.reporters import html_report

    def boom(_package):
        raise ModuleNotFoundError("odoo_doctor.reporters.html")

    monkeypatch.setattr(html_report.resources, "files", boom)
    addons = _project(tmp_path, bad=False)
    target = tmp_path / "r.html"
    result = CliRunner().invoke(app, ["scan", str(addons), "--html", str(target)])
    assert result.exit_code == 3
    assert "reinstall odoo-doctor" in result.output
    assert "cannot write" not in result.output
    assert not target.exists()


def test_failed_html_beats_the_delta_line_on_stdout(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    addons = _project(repo, bad=True)
    _git_init(repo)
    blocker = tmp_path / "blocker"
    blocker.write_text("x")

    ok = _scan(repo, str(addons), "--score-delta", "main")
    assert ok.returncode == 0 and "Score Delta:" in ok.stdout

    failed = _scan(
        repo, str(addons), "--score-delta", "main", "--html", str(blocker / "r.html")
    )
    assert failed.returncode == 3
    assert failed.stdout == ""

    good = tmp_path / "good.html"
    both = _scan(repo, str(addons), "--score-delta", "main", "--html", str(good))
    assert both.returncode == 0 and "Score Delta:" in both.stdout


def test_report_paths_are_relative_to_the_scan_root(tmp_path: Path):
    addons = _project(tmp_path, bad=True)
    report = tmp_path / "r.html"
    _scan(tmp_path, str(addons), "--html", str(report))
    html = report.read_text(encoding="utf-8")
    assert str(tmp_path.resolve()) not in html
    env = _envelope(report)
    diags = [d for m in env["report"]["modules"].values() for d in m["diagnostics"]]
    assert diags and all(not d["file_path"].startswith("/") for d in diags)
    assert any(d["file_path"] == "m/x.py" for d in diags)
    # --json keeps the absolute path
    out = _scan(tmp_path, str(addons), "--json").stdout
    assert str(tmp_path.resolve()) in out


def test_header_marks_a_dirty_tree_only_when_dirty(tmp_path: Path):
    repo = tmp_path / "repo"
    addons = _project(repo, bad=True)
    _git_init(repo)
    clean, dirty = tmp_path / "c.html", tmp_path / "d.html"
    _scan(repo, str(addons), "--html", str(clean))
    (repo / "addons" / "m" / "x.py").write_text("# edited\n")
    _scan(repo, str(addons), "--html", str(dirty))
    assert _envelope(clean)["meta"]["dirty"] is False
    assert _envelope(dirty)["meta"]["dirty"] is True
