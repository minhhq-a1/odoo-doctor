"""The JS import scanner and the `@module/path` -> file mapping."""

from __future__ import annotations

import time

from odoo_doctor.rules.upgrade_safety._js_imports import js_imports, specifier_target


def _specs(text: str) -> list[tuple[str, int, bool]]:
    return [(i.specifier, i.line, i.dynamic) for i in js_imports(text)]


def test_static_forms():
    text = (
        "/** @odoo-module **/\n"
        'import { x,\n  y } from "@web/core/hooks";\n'
        'import "@web/side";\n'
        "import def, * as ns from '@web/ns';\n"
        'export * from "@web/exp";\n'
        'export { k } from "@web/k";\n'
        "export * as q from '@web/q';\n"
    )
    assert _specs(text) == [
        ("@web/core/hooks", 3, False),
        ("@web/side", 4, False),
        ("@web/ns", 5, False),
        ("@web/exp", 6, False),
        ("@web/k", 7, False),
        ("@web/q", 8, False),
    ]


def test_dynamic_import_literal_only():
    text = 'const a = await import("@web/dyn");\nconst b = import(name);\nimport.meta.url;\n'
    assert _specs(text) == [("@web/dyn", 1, True)]


def test_comments_templates_and_strings_are_ignored():
    text = (
        '// import { a } from "@web/line";\n'
        '/* import b from "@web/block";\n import c from "@web/block2"; */\n'
        'const t = `\nimport d from "@web/tpl";\n`;\n'
        'const s = "x";import_ = 1;\n'
        "export const f = 1;\n"
        'import { real } from "@web/real";\n'
    )
    assert _specs(text) == [("@web/real", 9, False)]


def test_declarations_are_not_reexports():
    assert _specs('export const a = "from x";\nexport function f() {}\n') == []


def test_crlf_bom_empty_and_quick_exit():
    assert _specs("﻿import a from '@web/a';\r\nimport b from '@web/b';\r\n") == [
        ("@web/a", 1, False),
        ("@web/b", 2, False),
    ]
    assert _specs("") == [] and _specs("const x = 1;") == []


def test_long_line_does_not_backtrack():
    start = time.perf_counter()
    js_imports("import " + "a, " * 50_000 + " from x\n" + '"' * 10_000)
    assert time.perf_counter() - start < 2


def test_specifier_target():
    assert specifier_target("@web/core/hooks") == ("web", "static/src/core/hooks.js")
    assert specifier_target("@web/core/x.js") == ("web", "static/src/core/x.js")
    assert specifier_target("@web/../tests/h") == ("web", "static/tests/h.js")
    for spec in ("@odoo/owl", "./rel", "../up", "web/core/x", "@web", "@web/../../x"):
        assert specifier_target(spec) is None
