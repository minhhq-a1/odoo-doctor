"""The `odoo-doctor lsp` command."""

from __future__ import annotations

from typer.testing import CliRunner

import odoo_doctor.cli.app as cli
from odoo_doctor.cli.app import app

runner = CliRunner()


def test_without_pygls_it_explains_how_to_install_it(monkeypatch):
    def missing():
        raise ImportError("No module named 'pygls'")

    monkeypatch.setattr(cli, "_load_lsp_runner", missing)
    result = runner.invoke(app, ["lsp"])
    assert result.exit_code == 3
    assert "odoo-doctor[lsp]" in result.output


def test_it_runs_the_server_when_pygls_is_available(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_load_lsp_runner", lambda: lambda: calls.append("run"))
    result = runner.invoke(app, ["lsp"])
    assert result.exit_code == 0
    assert calls == ["run"]
