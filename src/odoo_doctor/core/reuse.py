# src/odoo_doctor/core/reuse.py
"""What a long-lived process (the language server) carries from one scan of a project to the next.

A scan from scratch is the reference; everything here must give the same findings and scores
(``tests/test_scan_reuse.py`` compares both after a sequence of edits). It is conservative: a
result is reused only when every input it can depend on is unchanged.

- **The whole scan** when no file of any addon, the Odoo source index, the config, the ruleset,
  the plugins or the linters changed.
- **Native file rules per file** (they see only the file, the module name and the version).
- **Ruff / Pylint-Odoo per addon**, keyed on every file of the addon *and* of the addons it
  depends on (transitively), because a linter may follow an import into a sibling addon.
- **The Odoo source index** (``odoo_source_path``), the one expensive piece of the graph.

Cross-module rules and the graph are rebuilt on every changed scan: a model, field or XML ID
of one addon can change the findings of any other. Files are told apart by size and mtime, checked
by content when the file changed in the last ``RACY_SECONDS`` (see ``Stamper``).
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_bytes

RACY_SECONDS = 2.0
_SKIPPED_DIRS = frozenset({".git", "__pycache__"})


class Stamper:
    """Fingerprints files for one scan: size and mtime, which stay the same while a file does.

    A file written within ``RACY_SECONDS`` of the scan could be written again with the same
    size and mtime (a coarse clock), so its content hash is recorded (``racy``). The next scan
    gets those hashes as *previous* and reports a file whose content differs from its recorded
    hash as changed, whatever its size and mtime say.
    """

    def __init__(self, previous: dict[str, tuple], now: float | None = None) -> None:
        self.previous = previous
        self.now = time.time() if now is None else now
        self.racy: dict[str, tuple] = {}  # path -> (size, mtime_ns, content hash)

    def _hash(self, path: str) -> str:
        data = read_bytes(path)
        return hashlib.sha1(data).hexdigest() if data is not None else "unreadable"

    def file(self, path: Path | str) -> tuple:
        path = str(path)
        try:
            st = os.stat(path)
        except OSError:
            return ("missing",)
        if not stat.S_ISREG(st.st_mode):
            return ("irregular", st.st_mode)
        sig: tuple = (st.st_size, st.st_mtime_ns)
        digest = None
        if self.now - st.st_mtime < RACY_SECONDS:
            digest = self._hash(path)
            self.racy[path] = (*sig, digest)
        # a file that was racy last time and still has the same size and mtime: same content?
        before = self.previous.get(path)
        if before is not None and before[:2] == sig:
            digest = digest or self._hash(path)
            if digest != before[2]:
                sig += ("rewritten", digest)
        return sig

    def tree(self, root: Path | str, suffixes: tuple[str, ...] | None = None) -> str:
        """One digest of every file under *root* (or those ending in *suffixes*). Symlinked
        directories are not followed (neither do the linters)."""
        h = hashlib.sha1()
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS)
            for name in sorted(names):
                if suffixes and not name.endswith(suffixes):
                    continue
                path = os.path.join(dirpath, name)
                h.update(f"{os.path.relpath(path, root)}\0{self.file(path)}\0".encode())
        return h.hexdigest()


class ScanReuse:
    """Per-project state for ``collect_scores(reuse=...)``. Not thread-safe: one scan at a time."""

    def __init__(self) -> None:
        self.env_key: str | None = None
        self.last: tuple[str, list[Diagnostic], dict] | None = None
        # (file, module, version, rules) -> (file signature, {rule name: findings})
        self.files: dict[tuple, tuple[tuple, dict[str, tuple[Diagnostic, ...]]]] = {}
        # (adapter, module path, version, signature) -> findings
        self.adapters: dict[tuple, tuple[Diagnostic, ...]] = {}
        self.source_index: tuple[str, object] | None = None
        self.racy: dict[
            str, tuple
        ] = {}  # files that were racy in the last scan (see Stamper)

    def begin(self, env_key: str) -> None:
        """Forget everything when an input that is not a file (config, ruleset, ...) changed."""
        if env_key != self.env_key:
            self.env_key = env_key
            self.racy = {}
            self.last = None
            self.files = {}
            self.adapters = {}
            self.source_index = None
