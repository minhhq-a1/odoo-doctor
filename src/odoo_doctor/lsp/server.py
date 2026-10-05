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
)
from odoo_doctor.lsp.convert import SOURCE, file_diagnostics
from odoo_doctor.lsp.engine import scan_project

RESCAN_COMMAND = "odooDoctor.rescan"

log = logging.getLogger("odoo-doctor.lsp")


class OdooDoctorServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("odoo-doctor", __version__)
        self.roots: list[Path] = []
        self.findings: dict[Path, dict[str, list[Diagnostic]]] = {}
        self._published: dict[Path, set[str]] = {}
        self._running: set[Path] = set()
        self._dirty: set[Path] = set()
        # One worker: scans share process-wide parse caches and must not overlap.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan")

    # -- helpers --------------------------------------------------------------

    def root_of(self, uri: str) -> Path | None:
        """The workspace folder containing *uri* (the deepest one wins)."""
        path = to_fs_path(uri)
        if path is None:
            return None
        resolved = Path(path).resolve()
        owners = [r for r in self.roots if resolved == r or r in resolved.parents]
        return max(owners, key=lambda r: len(r.parts), default=None)

    def findings_for(self, uri: str) -> list[Diagnostic]:
        root = self.root_of(uri)
        path = to_fs_path(uri)
        if root is None or path is None:
            return []
        return self.findings.get(root, {}).get(str(Path(path).resolve()), [])

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
                    break
                self._publish(root, result)
        finally:
            self._running.discard(root)

    def _publish(self, root: Path, result: dict[str, list[Diagnostic]]) -> None:
        self.findings[root] = result
        uris: set[str] = set()
        for path, findings in result.items():
            uri = from_fs_path(path)
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


def _workspace_roots(params: lsp.InitializeParams) -> list[Path]:
    uris = [f.uri for f in params.workspace_folders or []]
    if not uris and params.root_uri:
        uris = [params.root_uri]
    roots = []
    for uri in uris:
        path = to_fs_path(uri)
        if path:
            roots.append(Path(path).resolve())
    if not roots and params.root_path:
        roots.append(Path(params.root_path).resolve())
    return roots


def create_server() -> OdooDoctorServer:
    server = OdooDoctorServer()

    @server.feature(lsp.INITIALIZE)
    def initialize(params: lsp.InitializeParams) -> None:
        server.roots = _workspace_roots(params)

    @server.feature(lsp.INITIALIZED)
    async def initialized(params: lsp.InitializedParams) -> None:
        await asyncio.gather(*(server.request_scan(root) for root in server.roots))

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
        actions: list[lsp.CodeAction] = []
        for diagnostic in params.context.diagnostics:
            if diagnostic.source != SOURCE:
                continue
            finding = find_finding(findings, diagnostic)
            if finding is not None:
                actions.extend(code_actions_for(finding, text, uri, diagnostic))
        return actions

    @server.command(RESCAN_COMMAND)
    async def rescan() -> None:
        await asyncio.gather(*(server.request_scan(root) for root in server.roots))

    @server.command(DISABLE_RULE_COMMAND)
    async def disable_rule(rule: str, uri: str) -> None:
        root = server.root_of(uri)
        if root is None:
            return
        set_rule_ignored(root / "odoo-doctor.toml", rule, True)
        await server.request_scan(root)

    return server


def run() -> None:
    """Serve over stdio until the client exits (stdout carries the protocol)."""
    create_server().start_io()
