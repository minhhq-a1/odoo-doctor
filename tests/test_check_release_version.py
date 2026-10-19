"""scripts/check_release_version.py: the tag, pyproject and __version__ must agree."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_release_version", ROOT / "scripts" / "check_release_version.py"
)
check = importlib.util.module_from_spec(_SPEC)
sys.modules["check_release_version"] = check
_SPEC.loader.exec_module(check)


def _repo(tmp_path: Path, pyproject: str = "1.2.3", package: str = "1.2.3") -> Path:
    (tmp_path / "src" / "odoo_doctor").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{pyproject}"\n')
    (tmp_path / "src" / "odoo_doctor" / "__init__.py").write_text(
        f'__version__ = "{package}"\n'
    )
    return tmp_path


def test_matching_tag_passes(tmp_path: Path):
    assert check.problems("v1.2.3", _repo(tmp_path)) == []


def test_tag_without_v_prefix_is_rejected(tmp_path: Path):
    assert check.problems("1.2.3", _repo(tmp_path))


def test_tag_that_differs_from_pyproject_fails(tmp_path: Path):
    assert any("pyproject" in p for p in check.problems("v1.2.4", _repo(tmp_path)))


def test_package_version_that_differs_fails(tmp_path: Path):
    repo = _repo(tmp_path, package="1.2.2")
    assert any("__version__" in p for p in check.problems("v1.2.3", repo))


def test_a_branch_name_is_not_a_release_tag(tmp_path: Path):
    assert check.problems("main", _repo(tmp_path))


def test_main_exit_codes(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    assert check.main(["v1.2.3", "--root", str(repo)]) == 0
    assert check.main(["v9.9.9", "--root", str(repo)]) == 1
    assert "pyproject" in capsys.readouterr().err


def test_the_real_repository_is_consistent_with_its_own_version():
    from odoo_doctor import __version__

    assert check.problems(f"v{__version__}", ROOT) == []
