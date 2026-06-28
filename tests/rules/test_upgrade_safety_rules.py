# tests/rules/test_upgrade_safety_rules.py
"""Tests for Upgrade Safety rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.upgrade_safety.deprecated_api_usage import (
    check_deprecated_api_usage,
)
from odoo_doctor.rules.upgrade_safety.removed_model_still_referenced import (
    check_removed_model_still_referenced,
)


# ---------------------------------------------------------------------------
# deprecated-api-usage
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, src: str) -> Path:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return f


def test_deprecated_openerp_import(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        from openerp import models
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "deprecated-api-usage"
    assert "openerp" in diags[0].title.lower()


def test_deprecated_openerp_submodule_import(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        from openerp.osv import osv
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) >= 1
    assert any(d.rule == "deprecated-api-usage" for d in diags)


def test_deprecated_columns(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class OldModel:
            _columns = {
                'name': fields.char('Name'),
            }
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "deprecated-api-usage"
    assert "_columns" in diags[0].title


def test_deprecated_osv_osv(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class OldModel(osv.osv):
            _name = 'old.model'
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "deprecated-api-usage"
    assert "osv" in diags[0].title.lower()


def test_deprecated_osv_osv_memory(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class OldWizard(osv.osv_memory):
            _name = 'old.wizard'
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "deprecated-api-usage"


def test_deprecated_pool_bracket(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def m(self, cr, uid, context=None):
                partner = self.pool['res.partner']
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "deprecated-api-usage"
    assert "pool" in diags[0].title.lower()


def test_deprecated_pool_get(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def m(self, cr, uid, context=None):
                partner = self.pool.get('res.partner')
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert len(diags) == 1
    assert diags[0].rule == "deprecated-api-usage"


def test_clean_code_no_deprecated(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        from odoo import models, fields

        class CleanModel(models.Model):
            _name = 'clean.model'
            name = fields.Char(string='Name')

            def action_do(self):
                partner = self.env['res.partner'].browse(1)
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert diags == []


def test_deprecated_multiple_patterns_same_file(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        from openerp import osv

        class OldModel(osv.osv):
            _name = 'old.model'
            _columns = {
                'name': fields.char('Name'),
            }

            def m(self, cr, uid, context=None):
                partner = self.pool['res.partner']
        """,
    )
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    # Should detect: openerp import, osv.osv base class, _columns, .pool access
    assert len(diags) == 4
    assert all(d.rule == "deprecated-api-usage" for d in diags)
    assert all(d.category == "Upgrade Safety" for d in diags)
    assert all(d.tier == "P1" for d in diags)


def test_deprecated_unreadable_file(tmp_path: Path):
    f = tmp_path / "missing.py"
    diags = check_deprecated_api_usage(f, "mod", "17.0")
    assert diags == []


# ---------------------------------------------------------------------------
# removed-model-still-referenced
# ---------------------------------------------------------------------------


def test_removed_model_inherits_unknown(tmp_path: Path):
    """Inheriting a model that doesn't exist anywhere should be flagged."""
    addon = tmp_path / "test_addon"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{'name': 'Test Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': [], 'license': 'LGPL-3'}\n"
    )
    (addon / "models" / "m.py").write_text(
        dedent(
            """\
            from odoo import models

            class MyModel(models.Model):
                _name = 'my.model'
                _inherit = 'completely.nonexistent.model'
            """
        )
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_addon"]
    diags = check_removed_model_still_referenced(ctx)
    assert len(diags) == 1
    assert diags[0].rule == "removed-model-still-referenced"
    assert "completely.nonexistent.model" in diags[0].message
    assert diags[0].confidence == "medium"


def test_removed_model_inherits_known_model(tmp_path: Path):
    """Inheriting a model that exists in stubs should NOT be flagged."""
    addon = tmp_path / "test_addon"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{'name': 'Test Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': [], 'license': 'LGPL-3'}\n"
    )
    (addon / "models" / "m.py").write_text(
        dedent(
            """\
            from odoo import models

            class MyModel(models.Model):
                _name = 'my.model'
                _inherit = 'res.partner'
            """
        )
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_addon"]
    diags = check_removed_model_still_referenced(ctx)
    assert diags == []


def test_removed_model_inherits_local_model(tmp_path: Path):
    """Inheriting a model defined in the same project should NOT be flagged."""
    addon = tmp_path / "test_addon"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{'name': 'Test Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': [], 'license': 'LGPL-3'}\n"
    )
    (addon / "models" / "m.py").write_text(
        dedent(
            """\
            from odoo import models

            class BaseModel(models.Model):
                _name = 'my.base.model'

            class ChildModel(models.Model):
                _name = 'my.child.model'
                _inherit = 'my.base.model'
            """
        )
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_addon"]
    diags = check_removed_model_still_referenced(ctx)
    assert diags == []


def test_removed_model_self_inherit_not_flagged(tmp_path: Path):
    """Self-inheritance (extending own model) should NOT be flagged."""
    addon = tmp_path / "test_addon"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{'name': 'Test Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': [], 'license': 'LGPL-3'}\n"
    )
    (addon / "models" / "m.py").write_text(
        dedent(
            """\
            from odoo import models

            class MyModel(models.Model):
                _name = 'my.model'
                _inherit = 'my.model'
            """
        )
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_addon"]
    diags = check_removed_model_still_referenced(ctx)
    assert diags == []


def test_removed_model_no_inherit_no_diags(tmp_path: Path):
    """Model with _name only and no _inherit should produce no diagnostics."""
    addon = tmp_path / "test_addon"
    (addon / "models").mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{'name': 'Test Addon', 'version': '17.0.1.0.0', "
        "'depends': ['base'], 'data': [], 'license': 'LGPL-3'}\n"
    )
    (addon / "models" / "m.py").write_text(
        dedent(
            """\
            from odoo import models

            class MyModel(models.Model):
                _name = 'my.model'
            """
        )
    )

    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_addon"]
    diags = check_removed_model_still_referenced(ctx)
    assert diags == []
