"""End to end: spawn `odoo-doctor lsp` and talk JSON-RPC over stdio like an editor."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

pytest.importorskip("pygls")

from tests.lsp.test_engine import RULE, _project  # noqa: E402

TIMEOUT = 60


class Client:
    """Just enough of an LSP client: framing, request/response, notifications."""

    def __init__(self, cwd: Path) -> None:
        # a file, not a pipe nobody reads: a chatty server must never block on stderr
        self._stderr = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from odoo_doctor.cli.app import app; app(['lsp'])",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            cwd=cwd,
        )
        self.inbox: queue.Queue = queue.Queue()
        self.seen: list[dict] = []
        self._next_id = 0
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        out = self.proc.stdout
        while True:
            length = None
            while True:
                line = out.readline()
                if not line:
                    return
                line = line.strip()
                if not line:
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":")[1])
            if length is None:
                return
            self.inbox.put(json.loads(out.read(length)))

    def _send(self, message: dict) -> None:
        body = json.dumps({"jsonrpc": "2.0", **message}).encode()
        self.proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict) -> None:
        self._send({"method": method, "params": params})

    def _take(self) -> dict:
        message = self.inbox.get(timeout=TIMEOUT)
        self.seen.append(message)
        if "method" in message and "id" in message:  # a request from the server
            self._send({"id": message["id"], "result": None})
        return message

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            message = self._take()
            if message.get("id") == request_id and "method" not in message:
                assert "error" not in message, message
                return message["result"]

    def wait_for(self, method: str, predicate) -> dict:
        for message in self.seen:  # something already received may satisfy it
            if message.get("method") == method and predicate(message["params"]):
                self.seen.remove(message)
                return message["params"]
        while True:
            message = self._take()
            if message.get("method") == method and predicate(message["params"]):
                self.seen.remove(message)
                return message["params"]

    def close(self) -> int:
        try:
            self.request("shutdown")
            self.notify("exit", {})
            return self.proc.wait(timeout=TIMEOUT)
        finally:
            if self.proc.poll() is None:
                self.proc.kill()


def _has(params: dict, uri: str, code: str | None, present: bool) -> bool:
    if params["uri"] != uri:
        return False
    found = any(d.get("code") == code for d in params["diagnostics"])
    return found == present


def test_diagnostics_actions_command_and_rescan(tmp_path: Path):
    root = _project(tmp_path)
    source = root / "mod" / "models" / "m.py"
    uri = source.resolve().as_uri()
    client = Client(root)
    try:
        init = client.request(
            "initialize",
            {
                "processId": None,
                "rootUri": root.resolve().as_uri(),
                "workspaceFolders": [
                    {"uri": root.resolve().as_uri(), "name": "project"}
                ],
                "capabilities": {},
            },
        )
        capabilities = init["capabilities"]
        assert capabilities["textDocumentSync"]["save"]  # didSave is advertised
        assert capabilities["codeActionProvider"]
        assert (
            "odooDoctor.disableRule"
            in (capabilities["executeCommandProvider"]["commands"])
        )
        client.notify("initialized", {})

        # 1. the initial scan publishes the finding, with docs link and rule code
        params = client.wait_for(
            "textDocument/publishDiagnostics", lambda p: _has(p, uri, RULE, True)
        )
        diagnostic = next(d for d in params["diagnostics"] if d["code"] == RULE)
        assert diagnostic["source"] == "odoo-doctor"
        assert diagnostic["codeDescription"]["href"]
        assert diagnostic["range"]["start"]["line"] == 7

        # 2. code actions offer the ways to switch it off
        actions = client.request(
            "textDocument/codeAction",
            {
                "textDocument": {"uri": uri},
                "range": diagnostic["range"],
                "context": {"diagnostics": [diagnostic]},
            },
        )
        titles = [a["title"] for a in actions]
        assert f"Odoo Doctor: disable {RULE} on this line" in titles
        assert f"Odoo Doctor: disable {RULE} in odoo-doctor.toml" in titles
        line_action = next(a for a in actions if a["title"].endswith("on this line"))
        edit = line_action["edit"]["changes"][uri][0]
        assert edit["newText"].strip() == f"# odoo-doctor: disable={RULE}"

        # 3. the config command edits odoo-doctor.toml and the server rescans
        client.request(
            "workspace/executeCommand",
            {"command": "odooDoctor.disableRule", "arguments": [RULE, uri]},
        )
        assert RULE in (root / "odoo-doctor.toml").read_text()
        client.wait_for(
            "textDocument/publishDiagnostics", lambda p: _has(p, uri, RULE, False)
        )

        # 4. editing the file and saving triggers a rescan too
        (root / "odoo-doctor.toml").write_text(
            '[odoo-doctor]\nodoo_version = "17.0"\n\n'
            "[adapters]\nruff = false\npylint_odoo = false\n"
        )
        client.request("workspace/executeCommand", {"command": "odooDoctor.rescan"})
        client.wait_for(
            "textDocument/publishDiagnostics", lambda p: _has(p, uri, RULE, True)
        )
        source.write_text(source.read_text().replace('f"SELECT', '"SELECT'))
        client.notify("textDocument/didSave", {"textDocument": {"uri": uri}})
        client.wait_for(
            "textDocument/publishDiagnostics", lambda p: _has(p, uri, RULE, False)
        )
    finally:
        assert client.close() == 0


def _start(client: Client, folder: Path) -> None:
    uri = folder.as_uri()
    client.request(
        "initialize",
        {
            "processId": None,
            "rootUri": uri,
            "workspaceFolders": [{"uri": uri, "name": "project"}],
            "capabilities": {},
        },
    )
    client.notify("initialized", {})


def _titles(client: Client, uri: str, diagnostic: dict) -> list[str]:
    actions = client.request(
        "textDocument/codeAction",
        {
            "textDocument": {"uri": uri},
            "range": diagnostic["range"],
            "context": {"diagnostics": [diagnostic]},
        },
    )
    return [a["title"] for a in actions]


def test_a_folder_opened_through_a_symlink_gets_its_diagnostics_there(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    _project(real)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    uri = (link / "mod" / "models" / "m.py").as_uri()  # the path the editor opened
    client = Client(real)
    try:
        _start(client, link)
        params = client.wait_for(
            "textDocument/publishDiagnostics", lambda p: _has(p, uri, RULE, True)
        )
        diagnostic = next(d for d in params["diagnostics"] if d["code"] == RULE)
        titles = _titles(client, uri, diagnostic)
        assert f"Odoo Doctor: disable {RULE} on this line" in titles
    finally:
        assert client.close() == 0


def test_actions_that_depend_on_the_line_are_withheld_for_a_stale_buffer(
    tmp_path: Path,
):
    root = _project(tmp_path)
    source = root / "mod" / "models" / "m.py"
    uri = source.resolve().as_uri()
    disk = source.read_text()
    client = Client(root)
    try:
        _start(client, root.resolve())
        params = client.wait_for(
            "textDocument/publishDiagnostics", lambda p: _has(p, uri, RULE, True)
        )
        diagnostic = next(d for d in params["diagnostics"] if d["code"] == RULE)

        in_sync = {"uri": uri, "languageId": "python", "version": 1, "text": disk}
        client.notify("textDocument/didOpen", {"textDocument": in_sync})
        assert f"Odoo Doctor: disable {RULE} on this line" in _titles(
            client, uri, diagnostic
        )

        # three lines were typed above the finding and not saved yet
        stale = {"uri": uri, "version": 2}
        client.notify(
            "textDocument/didChange",
            {
                "textDocument": stale,
                "contentChanges": [{"text": "# a\n# b\n# c\n" + disk}],
            },
        )
        titles = _titles(client, uri, diagnostic)
        assert f"Odoo Doctor: disable {RULE} on this line" not in titles
        assert f"Odoo Doctor: disable {RULE} in this file" in titles
        assert f"Odoo Doctor: disable {RULE} in odoo-doctor.toml" in titles
    finally:
        assert client.close() == 0
