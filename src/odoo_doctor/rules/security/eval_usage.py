# src/odoo_doctor/rules/security/eval_usage.py
"""Rule: eval-usage [Security, P0]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import parse_python
from odoo_doctor.rules._taint import Taint, TaintVisitor
from odoo_doctor.rules.registry import rule

_DANGEROUS = {"eval", "exec"}


def _rebound_builtins(tree: ast.Module) -> set[str]:
    """Names in ``_DANGEROUS`` that the module binds itself.

    ``from odoo.tools.safe_eval import safe_eval as eval`` (an Odoo 8/9 idiom still
    found in ported addons) makes a bare ``eval(...)`` the sandboxed function, not the
    builtin. Only module-level bindings count (also inside ``if`` / ``try`` / ``with``);
    a method named ``eval`` is reached through ``self`` and shadows nothing.
    """
    bound: set[str] = set()
    pending: list[ast.stmt] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update(
                (alias.asname or alias.name).split(".")[0] for alias in node.names
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            continue  # its body is another scope
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            bound.update(t.id for t in targets if isinstance(t, ast.Name))
        for field in ("body", "orelse", "finalbody"):
            pending.extend(getattr(node, field, None) or [])
        for handler in getattr(node, "handlers", None) or []:
            pending.extend(handler.body)
    return bound & _DANGEROUS


@rule(
    name="eval-usage",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_eval_usage(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    tree = parse_python(file_path)
    if tree is None:
        return []

    visitor = _EvalVisitor(file_path, module_name, odoo_version)
    visitor.rebound = _rebound_builtins(tree)
    visitor.visit(tree)
    return visitor.diagnostics


class _EvalVisitor(TaintVisitor):
    def __init__(self, file_path: Path, module_name: str, odoo_version: str) -> None:
        super().__init__()
        self.file_path = file_path
        self.module_name = module_name
        self.odoo_version = odoo_version
        self.diagnostics: list[Diagnostic] = []
        self.rebound: set[str] = set()

    def check_call(self, node: ast.Call) -> None:
        # Only the bare builtin names eval / exec (not attribute calls like
        # tools.safe_eval, which is a separate, sandboxed function).
        if not (isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS):
            return
        if node.func.id in self.rebound:
            return  # the module defines its own eval/exec: not the builtin
        # An argument provably built from constants only (a literal, or a variable
        # bound to one) is far less risky; flag everything else.
        state = self.taint(node.args[0]) if node.args else Taint.UNKNOWN
        if state == Taint.SAFE:
            return
        evaluated = ""
        if node.args:
            shown = ast.unparse(node.args[0])
            shown = shown if len(shown) <= 60 else shown[:57] + "..."
            reason = (
                "built from interpolated or concatenated text"
                if state == Taint.UNSAFE
                else "not provably constant"
            )
            evaluated = f": `{shown}` is {reason}"
        self.diagnostics.append(
            Diagnostic(
                module=self.module_name,
                file_path=str(self.file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="eval-usage",
                category="Security",
                severity="error",
                tier="P0",
                source="native",
                confidence="high",
                title=f"Use of builtin {node.func.id}() on dynamic input",
                message=(
                    f"'{node.func.id}()' at line {node.lineno} executes arbitrary "
                    f"code and is a remote-code-execution risk{evaluated}."
                ),
                help=(
                    "Avoid eval/exec: ast.literal_eval for a stored literal such as "
                    "a domain or a list, odoo.tools.safe_eval.safe_eval for an "
                    "expression that needs variables, explicit logic otherwise. "
                    "Never evaluate text a user or an admin can edit with the "
                    "builtin."
                ),
                odoo_version=self.odoo_version,
            )
        )
