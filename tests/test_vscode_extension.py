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


def test_contributed_commands_do_not_clash_with_the_server_commands(manifest: dict):
    pytest.importorskip("pygls")
    from odoo_doctor.lsp.actions import DISABLE_RULE_COMMAND
    from odoo_doctor.lsp.server import RESCAN_COMMAND

    contributed = {c["command"] for c in manifest["contributes"]["commands"]}
    # The language client registers the server's commands itself, so contributing the
    # same ids would clash; the extension has its own palette commands instead.
    assert RESCAN_COMMAND not in contributed
    assert DISABLE_RULE_COMMAND not in contributed
    assert {"odooDoctor.rescanWorkspace", "odooDoctor.restart"} <= contributed
    source = (EXTENSION / "src" / "extension.ts").read_text(encoding="utf-8")
    assert f"'{RESCAN_COMMAND}'" in source  # forwarded to the server command


def test_extension_is_off_in_untrusted_workspaces(manifest: dict):
    # It runs `odoo-doctor lsp` on the workspace, which loads workspace configuration
    # and plugins (and `odooDoctor.path` can be set by the workspace itself).
    assert manifest["capabilities"]["untrustedWorkspaces"]["supported"] is False


def test_marketplace_identity_is_stable(manifest: dict):
    # `<publisher>.<name>` is the extension's identity on the Marketplace: changing either
    # publishes a different extension and orphans existing installs.
    assert manifest["publisher"] == "MinhHong"
    assert manifest["name"] == "odoo-doctor"


def test_marketplace_icon_is_a_square_png_of_at_least_128px(manifest: dict):
    # The Marketplace shows `icon` in the gallery and on the extension page; it must be
    # a PNG (not SVG) of at least 128x128 pixels.
    assert manifest.get("icon") == "images/icon.png"
    data = (EXTENSION / manifest["icon"]).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    assert width == height >= 128


def test_icon_source_is_not_shipped_in_the_vsix():
    ignored = (EXTENSION / ".vscodeignore").read_text(encoding="utf-8").split()
    assert "images/icon.svg" in ignored
