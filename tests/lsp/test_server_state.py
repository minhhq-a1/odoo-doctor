"""Server state: roots, URIs, scan coalescing and failure handling (no protocol)."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

pytest.importorskip("pygls")

from pygls.uris import from_fs_path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.lsp import server as srv


def _finding(path: Path, rule: str = "eval-usage", line: int = 1) -> Diagnostic:
    return Diagnostic(
        module="m",
        file_path=path.resolve().as_posix(),
        line=line,
        column=0,
        rule=rule,
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="h",
        odoo_version="17.0",
    )


@pytest.fixture
def server(monkeypatch):
    s = srv.OdooDoctorServer()
    s.published = []
    s.logged = []
    monkeypatch.setattr(
        s,
        "text_document_publish_diagnostics",
        lambda params: s.published.append(params),
    )
    monkeypatch.setattr(s, "window_log_message", lambda params: s.logged.append(params))
    yield s
    s._executor.shutdown(wait=False)


def _published(server) -> dict[str, list]:
    """Last diagnostics published per URI."""
    return {p.uri: p.diagnostics for p in server.published}


# --- roots -------------------------------------------------------------------


def test_nested_and_duplicate_folders_are_scanned_once(server, tmp_path: Path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "c").mkdir()
    server.set_roots(
        [tmp_path / "a", tmp_path / "a" / "b", tmp_path / "c", tmp_path / "a"]
    )
    assert server.roots == [(tmp_path / "a").resolve(), (tmp_path / "c").resolve()]


def test_root_of_accepts_the_clients_path_and_the_real_path(server, tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    server.set_roots([link])
    root = real.resolve()
    assert server.root_of(from_fs_path(str(link / "x.py"))) == root
    assert server.root_of(from_fs_path(str(real / "x.py"))) == root
    assert server.root_of(from_fs_path(str(tmp_path / "elsewhere" / "x.py"))) is None


def test_a_symlinked_in_addon_still_belongs_to_the_folder(server, tmp_path: Path):
    outside = tmp_path / "outside_addon"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / "linked_addon").symlink_to(outside, target_is_directory=True)
    server.set_roots([project])
    uri = from_fs_path(str(project / "linked_addon" / "m.py"))
    assert server.root_of(uri) == project.resolve()


# --- publishing ----------------------------------------------------------------


def test_diagnostics_go_to_the_path_the_editor_opened(
    server, tmp_path: Path, monkeypatch
):
    real = tmp_path / "real"
    real.mkdir()
    (real / "m.py").write_text("eval(x)\n")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    server.set_roots([link])
    root = real.resolve()
    monkeypatch.setattr(
        srv,
        "scan_project",
        lambda r: {(real / "m.py").resolve().as_posix(): [_finding(real / "m.py")]},
    )

    asyncio.run(server.request_scan(root))

    assert list(_published(server)) == [from_fs_path(str(link / "m.py"))]
    uri = from_fs_path(str(link / "m.py"))
    assert [f.rule for f in server.findings_for(uri)] == ["eval-usage"]


def test_files_that_are_clean_now_get_an_empty_publish(
    server, tmp_path: Path, monkeypatch
):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x\n")
    b.write_text("y\n")
    server.set_roots([tmp_path])
    results = iter(
        [
            {
                a.resolve().as_posix(): [_finding(a)],
                b.resolve().as_posix(): [_finding(b)],
            },
            {a.resolve().as_posix(): [_finding(a)]},
        ]
    )
    monkeypatch.setattr(srv, "scan_project", lambda r: next(results))

    asyncio.run(server.request_scan(tmp_path.resolve()))
    asyncio.run(server.request_scan(tmp_path.resolve()))

    last = _published(server)
    assert last[from_fs_path(str(b.resolve()))] == []
    assert len(last[from_fs_path(str(a.resolve()))]) == 1


def test_removing_a_folder_clears_its_diagnostics_and_adding_scans_it(
    server, tmp_path: Path, monkeypatch
):
    one, two = tmp_path / "one", tmp_path / "two"
    for folder in (one, two):
        folder.mkdir()
        (folder / "m.py").write_text("x\n")
    scanned = []

    def fake_scan(root):
        scanned.append(root)
        return {(root / "m.py").as_posix(): [_finding(root / "m.py")]}

    monkeypatch.setattr(srv, "scan_project", fake_scan)
    server.set_roots([one])
    asyncio.run(server.request_scan(one.resolve()))

    asyncio.run(server.change_roots(added=[two], removed=[one]))

    assert scanned == [one.resolve(), two.resolve()]
    last = _published(server)
    assert last[from_fs_path(str((one / "m.py").resolve()))] == []
    assert len(last[from_fs_path(str((two / "m.py").resolve()))]) == 1
    assert server.roots == [two.resolve()]


# --- scheduling ----------------------------------------------------------------


def test_requests_during_a_scan_are_coalesced_into_one_rerun(
    server, tmp_path: Path, monkeypatch
):
    server.set_roots([tmp_path])
    started, proceed, calls = threading.Event(), threading.Event(), []

    def fake_scan(root):
        calls.append(root)
        if len(calls) == 1:
            started.set()
            assert proceed.wait(30)
        return {}

    monkeypatch.setattr(srv, "scan_project", fake_scan)

    async def go():
        root = tmp_path.resolve()
        first = asyncio.create_task(server.request_scan(root))
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 30)
        await server.request_scan(root)  # returns at once: a scan is running
        await server.request_scan(root)
        proceed.set()
        await first

    asyncio.run(go())
    assert len(calls) == 2  # not 3: the two requests became one rerun


def test_a_failing_scan_is_logged_and_does_not_stop_later_scans(
    server, tmp_path: Path, monkeypatch
):
    server.set_roots([tmp_path])
    f = tmp_path / "m.py"
    f.write_text("x\n")
    calls = []

    def fake_scan(root):
        calls.append(root)
        if len(calls) == 1:
            raise RuntimeError("rule exploded")
        return {f.resolve().as_posix(): [_finding(f)]}

    monkeypatch.setattr(srv, "scan_project", fake_scan)
    root = tmp_path.resolve()

    asyncio.run(server.request_scan(root))
    assert server.published == []
    assert "rule exploded" in server.logged[0].message

    asyncio.run(server.request_scan(root))
    assert len(_published(server)[from_fs_path(str(f.resolve()))]) == 1


def test_a_request_that_arrives_during_a_failing_scan_is_not_lost(
    server, tmp_path: Path, monkeypatch
):
    server.set_roots([tmp_path])
    started, proceed, calls = threading.Event(), threading.Event(), []

    def fake_scan(root):
        calls.append(root)
        if len(calls) == 1:
            started.set()
            assert proceed.wait(30)
            raise RuntimeError("boom")
        return {}

    monkeypatch.setattr(srv, "scan_project", fake_scan)

    async def go():
        root = tmp_path.resolve()
        first = asyncio.create_task(server.request_scan(root))
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 30)
        await server.request_scan(root)
        proceed.set()
        await first

    asyncio.run(go())
    assert len(calls) == 2
