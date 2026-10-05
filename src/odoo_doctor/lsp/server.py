# src/odoo_doctor/lsp/server.py
"""Language server (pygls): project-wide diagnostics and code actions over stdio.

Static analysis reads files from disk, so diagnostics refresh on startup, on save and on
the ``odooDoctor.rescan`` command, not per keystroke. A scan covers a whole workspace
folder, runs one at a time on a worker thread, and requests that arrive meanwhile are
coalesced into a single rerun.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer
from pygls.uris import from_fs_path, to_fs_path

from odoo_doctor import __version__
from odoo_doctor.core.config_edit import set_rule_ignored
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.lsp.actions import (
    DISABLE_RULE_COMMAND,
    code_actions_for,
    find_finding,
    line_in_sync,
)
from odoo_doctor.lsp.convert import SOURCE, file_diagnostics
from odoo_doctor.lsp.engine import scan_project
from odoo_doctor.rules.registry import default_registry

RESCAN_COMMAND = "odooDoctor.rescan"

log = logging.getLogger("odoo-doctor.lsp")


def _absolute(path: str | Path) -> Path:
    """Absolute but NOT symlink-resolved: the path the editor knows the folder by."""
    return Path(os.path.abspath(path))


class OdooDoctorServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("odoo-doctor", __version__)
        # Folders as reported by the client (absolute, unresolved), and the scan roots
        # derived from them: resolved, without duplicates or nested folders.
        self._requested: list[Path] = []
        self.roots: list[Path] = []
        self._origin: dict[Path, Path] = {}  # resolved root -> the client's path
        self.findings: dict[Path, dict[str, list[Diagnostic]]] = {}
        self._published: dict[Path, set[str]] = {}
        self._running: set[Path] = set()
        self._dirty: set[Path] = set()
        # One worker: scans share process-wide parse caches and must not overlap.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan")

    # -- folders --------------------------------------------------------------

    def set_roots(self, folders: list[Path]) -> None:
        """Replace the workspace folders. A folder inside another one is already covered
        by the scan of the outer folder, so it is not scanned (or published) twice."""
        self._requested = [_absolute(f) for f in folders]
        roots: list[Path] = []
        origin: dict[Path, Path] = {}
        for requested in sorted(self._requested, key=lambda p: len(p.resolve().parts)):
            resolved = requested.resolve()
            if resolved in origin or any(r in resolved.parents for r in roots):
                continue
            roots.append(resolved)
            origin[resolved] = requested
        self.roots = roots
        self._origin = origin

    async def change_roots(self, added: list[Path], removed: list[Path]) -> None:
        """Apply a workspace/didChangeWorkspaceFolders event."""
        before = set(self.roots)
        gone = {_absolute(p) for p in removed}
        self.set_roots([f for f in self._requested if f not in gone] + added)
        for root in before - set(self.roots):
            self._clear(root)
        await asyncio.gather(
            *(self.request_scan(r) for r in self.roots if r not in before)
        )

    def _clear(self, root: Path) -> None:
        self.findings.pop(root, None)
        for uri in self._published.pop(root, set()):
            self.text_document_publish_diagnostics(
                lsp.PublishDiagnosticsParams(uri=uri, diagnostics=[])
            )

    # -- lookups --------------------------------------------------------------

    def root_of(self, uri: str) -> Path | None:
        """The scan root containing *uri*, whether the editor reached the file through the
        folder path it knows or through the real path (the deepest folder wins)."""
        path = to_fs_path(uri)
        if path is None:
            return None
        candidates = {_absolute(path), Path(path).resolve()}
        owners = []
        for root in self.roots:
            bases = {root, self._origin.get(root, root)}
            if any(c == b or b in c.parents for c in candidates for b in bases):
                owners.append(root)
        return max(owners, key=lambda r: len(r.parts), default=None)

    def findings_for(self, uri: str) -> list[Diagnostic]:
        root = self.root_of(uri)
        path = to_fs_path(uri)
        if root is None or path is None:
            return []
        return self.findings.get(root, {}).get(Path(path).resolve().as_posix(), [])

    def _uri_for(self, root: Path, file_path: str) -> str:
        """URI of a finding's file under the path the client opened the folder with."""
        try:
            relative = Path(file_path).relative_to(root)
        except ValueError:
            return from_fs_path(file_path)
        return from_fs_path(str(self._origin.get(root, root) / relative))

    # -- scanning -------------------------------------------------------------

    async def request_scan(self, root: Path) -> None:
        """Scan *root* now, or after the scan that is already running for it."""
        self._dirty.add(root)
        if root in self._running:
            return
        self._running.add(root)
        loop = asyncio.get_running_loop()
        try:
            while root in self._dirty:
                self._dirty.discard(root)
                try:
                    result = await loop.run_in_executor(
                        self._executor, scan_project, root
                    )
                except Exception as exc:  # a crashing rule must not kill the server
                    log.exception("scan of %s failed", root)
                    self.window_log_message(
                        lsp.LogMessageParams(
                            type=lsp.MessageType.Error,
                            message=f"odoo-doctor: scan of {root} failed: {exc}",
                        )
                    )
                    continue  # a request that arrived meanwhile still gets its rerun
                self._publish(root, result)
        finally:
            self._running.discard(root)

    def _publish(self, root: Path, result: dict[str, list[Diagnostic]]) -> None:
        self.findings[root] = result
        uris: set[str] = set()
        for path, findings in result.items():
            uri = self._uri_for(root, path)
            uris.add(uri)
            self.text_document_publish_diagnostics(
                lsp.PublishDiagnosticsParams(
                    uri=uri, diagnostics=file_diagnostics(path, findings)
                )
            )
        for stale in self._published.get(root, set()) - uris:
            self.text_document_publish_diagnostics(
                lsp.PublishDiagnosticsParams(uri=stale, diagnostics=[])
            )
        self._published[root] = uris


def _folder_paths(uris: list[str]) -> list[Path]:
    return [Path(p) for p in (to_fs_path(u) for u in uris) if p]


def _workspace_folders(params: lsp.InitializeParams) -> list[Path]:
    uris = [f.uri for f in params.workspace_folders or []]
    if not uris and params.root_uri:
        uris = [params.root_uri]
    folders = _folder_paths(uris)
    if not folders and params.root_path:
        folders = [Path(params.root_path)]
    return folders


def _read_disk(uri: str) -> str | None:
    path = to_fs_path(uri)
    if path is None:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def create_server() -> OdooDoctorServer:
    server = OdooDoctorServer()

    @server.feature(lsp.INITIALIZE)
    def initialize(params: lsp.InitializeParams) -> None:
        server.set_roots(_workspace_folders(params))

    @server.feature(lsp.INITIALIZED)
    async def initialized(params: lsp.InitializedParams) -> None:
        await asyncio.gather(*(server.request_scan(root) for root in server.roots))

    @server.feature(lsp.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS)
    async def folders_changed(params: lsp.DidChangeWorkspaceFoldersParams) -> None:
        event = params.event
        await server.change_roots(
            added=_folder_paths([f.uri for f in event.added]),
            removed=_folder_paths([f.uri for f in event.removed]),
        )

    @server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
    async def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
        root = server.root_of(params.text_document.uri)
        if root is not None:
            await server.request_scan(root)

    @server.feature(
        lsp.TEXT_DOCUMENT_CODE_ACTION,
        lsp.CodeActionOptions(code_action_kinds=[lsp.CodeActionKind.QuickFix]),
    )
    def code_action(params: lsp.CodeActionParams) -> list[lsp.CodeAction]:
        uri = params.text_document.uri
        findings = server.findings_for(uri)
        if not findings:
            return []
        text = server.workspace.get_text_document(uri).source
        disk_text = _read_disk(uri)
        actions: list[lsp.CodeAction] = []
        for diagnostic in params.context.diagnostics:
            if diagnostic.source != SOURCE:
                continue
            finding = find_finding(findings, diagnostic)
            if finding is not None:
                actions.extend(
                    code_actions_for(
                        finding,
                        text,
                        uri,
                        diagnostic,
                        in_sync=line_in_sync(finding.line, text, disk_text),
                    )
                )
        return actions

    @server.command(RESCAN_COMMAND)
    async def rescan() -> None:
        await asyncio.gather(*(server.request_scan(root) for root in server.roots))

    @server.command(DISABLE_RULE_COMMAND)
    async def disable_rule(rule: str, uri: str) -> None:
        root = server.root_of(uri)
        if root is None or rule not in default_registry:
            return
        set_rule_ignored(root / "odoo-doctor.toml", rule, True)
        await server.request_scan(root)

    return server


def run() -> None:
    """Serve over stdio until the client exits (stdout carries the protocol)."""
    create_server().start_io()
