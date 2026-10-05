"""Supply-chain rules (0.6.0): license compatibility, external dependencies, vendoring."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.manifest.external_dependencies import (
    check_missing_external_dependency,
)
from odoo_doctor.rules.manifest.license_compatibility import (
    check_license_incompatible,
)
from odoo_doctor.rules.manifest.vendored_python_code import (
    check_vendored_python_code,
)


def _addon(
    root: Path,
    name: str,
    *,
    license: str | None = "LGPL-3",
    depends: list[str] | None = None,
    external: dict | None = None,
    files: dict[str, str] | None = None,
) -> Path:
    mod = root / name
    mod.mkdir(parents=True)
    manifest: dict = {
        "name": name,
        "version": "17.0.1.0.0",
        "depends": ["base"] if depends is None else depends,
        "data": [],
    }
    if license is not None:
        manifest["license"] = license
    if external is not None:
        manifest["external_dependencies"] = external
    (mod / "__manifest__.py").write_text(repr(manifest))
    (mod / "__init__.py").write_text("")
    for rel, content in (files or {}).items():
        target = mod / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(content))
    return mod


def _ctx(root: Path, name: str):
    return build_project_graph([root], odoo_version="17.0").modules[name]


# --- manifest-license-incompatible --------------------------------------------


def _licenses(tmp_path: Path, mine: str | None, dep: str | None):
    _addon(tmp_path, "dep", license=dep)
    _addon(tmp_path, "mine", license=mine, depends=["dep"])
    return check_license_incompatible(_ctx(tmp_path, "mine"))


def test_proprietary_module_depending_on_agpl_is_flagged_medium(tmp_path: Path):
    diags = _licenses(tmp_path, "OPL-1", "AGPL-3")
    assert len(diags) == 1
    assert diags[0].rule == "manifest-license-incompatible"
    assert diags[0].confidence == "medium"
    assert "OPL-1" in diags[0].message and "AGPL-3" in diags[0].message


def test_gpl2_only_with_lgpl3_dependency_is_a_hard_conflict(tmp_path: Path):
    diags = _licenses(tmp_path, "GPL-2", "LGPL-3")
    assert [d.confidence for d in diags] == ["high"]


def test_lgpl3_depending_on_gpl2_only_is_a_hard_conflict(tmp_path: Path):
    diags = _licenses(tmp_path, "LGPL-3", "GPL-2")
    assert [d.confidence for d in diags] == ["high"]


def test_compatible_pairs_are_not_flagged(tmp_path: Path):
    for i, (mine, dep) in enumerate(
        [
            ("AGPL-3", "LGPL-3"),
            ("LGPL-3", "AGPL-3"),
            ("OPL-1", "LGPL-3"),
            ("GPL-2 or any later version", "GPL-3"),
            ("GPL-3", "GPL-3 or any later version"),
            ("OPL-1", "OPL-1"),
        ]
    ):
        root = tmp_path / f"case{i}"
        root.mkdir()
        assert _licenses(root, mine, dep) == [], (mine, dep)


def test_unknown_or_missing_licenses_are_not_flagged(tmp_path: Path):
    for i, (mine, dep) in enumerate(
        [("Some Custom Licence", "AGPL-3"), (None, "GPL-2"), ("GPL-2", None)]
    ):
        root = tmp_path / f"case{i}"
        root.mkdir()
        assert _licenses(root, mine, dep) == [], (mine, dep)


def test_license_names_are_matched_case_insensitively(tmp_path: Path):
    assert len(_licenses(tmp_path, "opl-1", "agpl-3")) == 1


def test_dependency_outside_the_scanned_repo_is_ignored(tmp_path: Path):
    _addon(tmp_path, "mine", license="GPL-2", depends=["base", "sale"])
    assert check_license_incompatible(_ctx(tmp_path, "mine")) == []


# --- missing-external-dependency ----------------------------------------------


def _external(
    tmp_path: Path,
    code: str,
    *,
    external: dict | None = None,
    rel: str = "models/m.py",
    depends: list[str] | None = None,
):
    _addon(tmp_path, "mine", external=external, depends=depends, files={rel: code})
    return check_missing_external_dependency(_ctx(tmp_path, "mine"))


def test_undeclared_third_party_import_is_flagged(tmp_path: Path):
    diags = _external(tmp_path, "import paramiko\n")
    assert len(diags) == 1
    assert diags[0].rule == "missing-external-dependency"
    assert diags[0].confidence == "high"
    assert "paramiko" in diags[0].message
    assert diags[0].file_path.endswith("models/m.py")
    assert diags[0].line == 1


def test_declared_dependency_is_fine(tmp_path: Path):
    assert (
        _external(
            tmp_path,
            "import paramiko\n",
            external={"python": ["paramiko"]},
        )
        == []
    )


def test_stdlib_odoo_relative_and_core_requirements_are_fine(tmp_path: Path):
    code = """\
    import os, json, logging
    import requests
    from dateutil import parser
    from PIL import Image
    from lxml import etree
    import odoo
    from odoo import models
    from odoo.addons.base import x
    from . import sibling
    from .sibling import y
    """
    assert _external(tmp_path, code) == []


def test_guarded_optional_import_is_fine(tmp_path: Path):
    code = """\
    try:
        import paramiko
    except ImportError:
        paramiko = None

    try:
        import yaml
    except (ImportError, ValueError):
        yaml = None
    """
    assert _external(tmp_path, code) == []


def test_unguarded_import_next_to_a_try_is_still_flagged(tmp_path: Path):
    code = """\
    try:
        import yaml
    except ImportError:
        yaml = None
    import paramiko
    """
    diags = _external(tmp_path, code)
    assert [("paramiko" in d.message) for d in diags] == [True]


def test_type_checking_import_is_fine(tmp_path: Path):
    code = """\
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        import paramiko
    """
    assert _external(tmp_path, code) == []


def test_tests_and_migrations_are_not_checked(tmp_path: Path):
    assert _external(tmp_path, "import paramiko\n", rel="tests/test_x.py") == []


def test_one_finding_per_package_at_the_first_import(tmp_path: Path):
    _addon(
        tmp_path,
        "mine",
        files={
            "models/a.py": "import paramiko\n",
            "models/b.py": "from paramiko import SSHClient\nimport paramiko.rsakey\n",
        },
    )
    diags = check_missing_external_dependency(_ctx(tmp_path, "mine"))
    assert len(diags) == 1
    assert "3" in diags[0].message  # imported in 3 places


def test_dependency_module_declaring_the_package_covers_it(tmp_path: Path):
    _addon(tmp_path, "base_ext", external={"python": ["paramiko"]})
    _addon(
        tmp_path,
        "mine",
        depends=["base_ext"],
        files={"models/m.py": "import paramiko\n"},
    )
    assert check_missing_external_dependency(_ctx(tmp_path, "mine")) == []


def test_unknown_dependency_chain_downgrades_confidence(tmp_path: Path):
    diags = _external(tmp_path, "import paramiko\n", depends=["l10n_unknown"])
    assert [d.confidence for d in diags] == ["medium"]


def test_local_packages_are_not_third_party(tmp_path: Path):
    _addon(
        tmp_path,
        "mine",
        files={"helpers/util.py": "X = 1\n", "models/m.py": "import helpers\n"},
    )
    assert check_missing_external_dependency(_ctx(tmp_path, "mine")) == []


def test_dotted_declaration_covers_the_top_level_package(tmp_path: Path):
    assert (
        _external(
            tmp_path,
            "from google.cloud import storage\n",
            external={"python": ["google.cloud"]},
        )
        == []
    )


# --- vendored-python-code -----------------------------------------------------


def _vendored(tmp_path: Path, files: dict[str, str]):
    _addon(tmp_path, "mine", files=files)
    return check_vendored_python_code(_ctx(tmp_path, "mine"))


def test_vendor_directory_with_python_is_flagged(tmp_path: Path):
    diags = _vendored(tmp_path, {"vendor/foo.py": "X = 1\n"})
    assert len(diags) == 1
    assert diags[0].rule == "vendored-python-code"
    assert diags[0].confidence == "medium"
    assert "vendor" in diags[0].message


def test_lib_directory_with_python_is_flagged(tmp_path: Path):
    assert len(_vendored(tmp_path, {"lib/requests/__init__.py": ""})) == 1


def test_well_known_package_copied_at_the_top_level_is_flagged(tmp_path: Path):
    diags = _vendored(tmp_path, {"six/__init__.py": "", "six/moves.py": ""})
    assert len(diags) == 1
    assert "six" in diags[0].message


def test_dist_info_directory_is_flagged(tmp_path: Path):
    assert len(_vendored(tmp_path, {"foo-1.0.dist-info/METADATA": "x"})) == 1


def test_javascript_libs_and_normal_code_are_fine(tmp_path: Path):
    files = {
        "static/lib/jquery/jquery.js": "//",
        "static/src/js/a.js": "//",
        "models/m.py": "X = 1\n",
        "lib/README.md": "no python here",
        "tests/vendor/helper.py": "X = 1\n",
    }
    assert _vendored(tmp_path, files) == []


def test_each_vendored_root_is_reported_once(tmp_path: Path):
    diags = _vendored(
        tmp_path,
        {"vendor/a.py": "", "vendor/sub/b.py": "", "vendor/sub/c.py": ""},
    )
    assert len(diags) == 1
