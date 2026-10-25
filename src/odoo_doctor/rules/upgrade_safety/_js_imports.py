# src/odoo_doctor/rules/upgrade_safety/_js_imports.py
"""Find the ES module specifiers a JS file imports, without a JS parser.

Comments and template literals are blanked first (one regex pass finds them, so a
``from "@web/x"`` inside either is ignored). Static ``import``/``export ... from`` are only
recognised at the start of a line, which is how Odoo formats its modules; ``import("lit")``
is recognised anywhere. Known limits: a regex literal holding a quote can desynchronise the
string scan until the end of its line, and a ``${`` ... backtick ... ``}`` nested template
ends the outer one early. Both only ever lose or add an import of that line.
"""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from odoo_doctor.core.source import SKIP_DIRS, is_scannable

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_SPANS = re.compile(
    r"""//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`""",
    re.DOTALL,
)
_NOT_NEWLINE = re.compile(r"[^\n]")
_STATIC = re.compile(
    r"""^[ \t\ufeff]*(?:
        import\s*["'](?P<side>[^"'\n]+)["']
      | import\b[^;"'()]*?\bfrom\s*["'](?P<imp>[^"'\n]+)["']
      | export\s*[*{][^;"'()]*?\bfrom\s*["'](?P<exp>[^"'\n]+)["']
    )""",
    re.MULTILINE | re.VERBOSE,
)
_DYNAMIC = re.compile(r"""(?<![\w$.])import\s*\(\s*["'](?P<spec>[^"'\n]+)["']\s*\)""")


@dataclass(frozen=True)
class JsImport:
    specifier: str
    line: int
    dynamic: bool = False


def _mask(match: re.Match[str]) -> str:
    text = match.group()
    return text if text[0] in "\"'" else _NOT_NEWLINE.sub(" ", text)


def js_imports(text: str) -> list[JsImport]:
    """Every literal import specifier of ``text``, in file order."""
    if "import" not in text and "export" not in text:
        return []
    code = _SPANS.sub(_mask, text)
    found: list[tuple[int, JsImport]] = []
    for m in _STATIC.finditer(code):
        group = next(g for g in ("side", "imp", "exp") if m.group(g))
        start = m.start(group)
        found.append((start, JsImport(m.group(group), code.count("\n", 0, start) + 1)))
    for m in _DYNAMIC.finditer(code):
        start = m.start("spec")
        found.append(
            (start, JsImport(m.group("spec"), code.count("\n", 0, start) + 1, True))
        )
    return [imp for _, imp in sorted(found, key=lambda f: f[0])]


def specifier_target(spec: str) -> tuple[str, str] | None:
    """``(module, path relative to the module)`` an ``@module/path`` specifier names, else None.

    ``@web/core/x`` is ``web/static/src/core/x.js``; ``@web/../tests/h`` is
    ``web/static/tests/h.js``. ``@odoo/*`` (owl, hoot) is not a module alias.
    """
    if not spec.startswith("@") or spec.startswith("@odoo/"):
        return None
    module, _, rest = spec[1:].partition("/")
    if not module or not rest:
        return None
    path = posixpath.normpath(f"static/src/{rest}")
    if not path.startswith("static/"):
        return None
    return module, path if path.endswith(".js") else f"{path}.js"


def module_js_files(ctx: ModuleContext) -> Iterator[Path]:
    """``*.js`` under ``static/src`` and ``static/tests`` of the module (no minified files)."""
    for sub in ("static/src", "static/tests"):
        for dirpath, dirs, names in os.walk(ctx.path / sub):
            dirs[:] = sorted(
                d for d in dirs if d != "node_modules" and d not in SKIP_DIRS
            )
            for name in sorted(names):
                path = Path(dirpath, name)
                if (
                    name.endswith(".js")
                    and not name.endswith(".min.js")
                    and is_scannable(path, ctx.path)
                ):
                    yield path
