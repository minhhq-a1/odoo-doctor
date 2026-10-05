"""The VS Code extension metadata must stay in step with the Python package."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from odoo_doctor import __version__

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "editors" / "vscode"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((EXTENSION / "package.json").read_text(encoding="utf-8"))


def test_extension_version_matches_the_package(manifest: dict):
    # Bump editors/vscode/package.json (and package-lock.json) with every release.
    assert manifest["version"] == __version__


def test_lock_file_has_the_same_version(manifest: dict):
    lock = json.loads((EXTENSION / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == manifest["version"]
    assert lock["packages"][""]["version"] == manifest["version"]


def test_extension_starts_the_command_the_package_installs(manifest: dict):
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    executable = re.search(
        r"^\[project\.scripts\]\s*\n([\w-]+)\s*=", pyproject, re.MULTILINE
    ).group(1)
    default = manifest["contributes"]["configuration"]["properties"]["odooDoctor.path"][
        "default"
    ]
    assert default == executable
    source = (EXTENSION / "src" / "extension.ts").read_text(encoding="utf-8")
    assert re.search(r"args:\s*\['lsp'\]", source)


def test_contributed_commands_cover_the_server_commands(manifest: dict):
    pytest.importorskip("pygls")
    from odoo_doctor.lsp.actions import DISABLE_RULE_COMMAND
    from odoo_doctor.lsp.server import RESCAN_COMMAND

    contributed = {c["command"] for c in manifest["contributes"]["commands"]}
    assert RESCAN_COMMAND in contributed
    # the disable command is only invoked from code actions, never from the palette
    assert DISABLE_RULE_COMMAND not in contributed
