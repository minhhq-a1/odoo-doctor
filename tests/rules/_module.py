"""Build a one-module project on disk and return its ModuleContext (for context rules)."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import ModuleContext, build_project_graph


def module_ctx(
    tmp_path: Path,
    files: dict[str, str],
    version: str = "19.0",
    data: list[str] | None = None,
) -> ModuleContext:
    """Write ``files`` (path below the addon -> text) and load the addon ``mod``.

    ``data`` defaults to every ``.xml`` file, in the order given.
    """
    addon = tmp_path / "mod"
    addon.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        target = addon / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (addon / "__manifest__.py").write_text(
        repr(
            {
                "name": "mod",
                "version": f"{version}.1.0.0",
                "depends": [],
                "license": "LGPL-3",
                "data": data
                if data is not None
                else [n for n in files if n.endswith(".xml")],
            }
        )
    )
    (addon / "__init__.py").write_text("")
    return build_project_graph([tmp_path], odoo_version=version).modules["mod"]


def view(arch: str, rec_id: str = "v", model: str = "x.model", extra: str = "") -> str:
    """An ``ir.ui.view`` record around ``arch``."""
    return (
        f'<odoo><record id="{rec_id}" model="ir.ui.view">\n'
        f'<field name="name">{rec_id}</field>\n'
        f'<field name="model">{model}</field>\n{extra}'
        f'<field name="arch" type="xml">\n{arch}\n</field>\n</record></odoo>'
    )
