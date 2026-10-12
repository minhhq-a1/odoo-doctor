"""dynamic-method-dispatch: getattr(obj, <name>)() with a name the code does not fix."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from odoo_doctor.rules.security.dynamic_method_dispatch import (
    check_dynamic_method_dispatch,
)


def _diags(tmp_path: Path, src: str, name: str = "m.py"):
    f = tmp_path / name
    f.write_text(dedent(src))
    return check_dynamic_method_dispatch(f, "m", "17.0")


def test_a_public_method_calling_its_own_parameter_by_name_is_high(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self, method_name):
                return getattr(self, method_name)()
        """,
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "dynamic-method-dispatch",
        "P1",
        "Security",
        "high",
    )
    assert d.line == 3


def test_a_name_derived_from_a_parameter_is_still_high(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self, payload):
                name = payload['callback'].strip()
                method = getattr(self, name)
                return method()
        """,
    )
    assert [d.confidence for d in diags] == ["high"]
    assert diags[0].line == 4


def test_a_name_read_from_a_record_is_medium(tmp_path: Path):
    # the admin-configured callback: not a parameter, but editable data
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self):
                for button in self.button_ids:
                    getattr(self, button.method)()
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]


def test_a_private_method_with_a_parameter_name_is_medium(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def _run(self, name):
                return getattr(self, name)()
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]


@pytest.mark.parametrize(
    "body",
    [
        "getattr(self, 'known')()",  # a literal name
        "getattr(self, '_get_%s' % kind)()",  # confined to a constant prefix
        "getattr(self, f'_get_{kind}')()",
        "getattr(self, 'action_' + kind)()",
        "getattr(self, kind)",  # fetched, not called
        "hasattr(self, kind)",
    ],
)
def test_names_the_code_fixes_or_attributes_never_called_are_fine(tmp_path, body):
    src = f"class M:\n    def run(self, kind):\n        return {body}\n"
    assert _diags(tmp_path, src) == []


@pytest.mark.parametrize(
    "guard",
    [
        "if name not in ALLOWED:\n            raise ValueError(name)",
        "if name.startswith('_'):\n            raise ValueError(name)",
        "if name != 'confirm':\n            raise ValueError(name)",
    ],
)
def test_a_guard_on_the_name_in_the_same_function_silences_it(tmp_path, guard):
    src = (
        "ALLOWED = {'confirm'}\n\n\nclass M:\n    def run(self, name):\n"
        f"        {guard}\n        return getattr(self, name)()\n"
    )
    assert _diags(tmp_path, src) == []


def test_comparing_with_dir_is_not_a_guard(tmp_path: Path):
    # `name in dir(obj)` only says the attribute exists, which is the problem
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self, name):
                if name in dir(self):
                    return getattr(self, name)()
        """,
    )
    assert [d.confidence for d in diags] == ["high"]


def test_tests_are_skipped(tmp_path: Path):
    (tmp_path / "m" / "tests").mkdir(parents=True)
    f = tmp_path / "m" / "tests" / "test_x.py"
    f.write_text("class T:\n    def t(self, n):\n        return getattr(self, n)()\n")
    assert check_dynamic_method_dispatch(f, "m", "17.0") == []


def test_a_nested_function_is_judged_on_its_own_parameters(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self):
                def call(name):
                    return getattr(self, name)()
                return call
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]  # `call` is not an entry point


def test_a_name_read_from_an_attribute_of_a_parameter_is_medium(tmp_path: Path):
    # `entity` comes from the caller, but `entity.method_name` is a stored field value
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self, entities):
                for entity in entities:
                    getattr(self, entity.method_name)()
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]


def test_a_dict_key_of_a_parameter_stays_high(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self, payload):
                return getattr(self, payload.get('callback', 'x'))()
        """,
    )
    assert [d.confidence for d in diags] == ["high"]


def test_a_name_looked_up_in_a_module_table_is_fixed_by_the_code(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        HANDLERS = {'a': 'handle_a', 'b': 'handle_b'}


        class M:
            def run(self, kind):
                return getattr(self, HANDLERS[kind])()

            def run2(self, kind):
                return getattr(self, HANDLERS.get(kind, 'handle_a'))()
        """,
    )
    assert diags == []


@pytest.mark.parametrize("receiver", ["_logger", "logger", "self._logger", "log"])
def test_picking_a_logger_level_by_name_is_harmless(tmp_path: Path, receiver):
    src = (
        "class M:\n    def write_log(self, level):\n"
        f"        return getattr({receiver}, level)('x')\n"
    )
    assert _diags(tmp_path, src) == []


def test_a_prefixed_name_kept_in_a_variable_is_still_confined(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def send(self, vals):
                method_name = f'_send_sub_status_{vals["status"]}'
                if hasattr(self, method_name):
                    return getattr(self, method_name)(vals)
        """,
    )
    assert diags == []


def test_a_parameter_glued_to_stored_data_is_only_partly_the_callers(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run_step(self, prefix):
                return getattr(self, prefix + self.state)()
        """,
    )
    assert [d.confidence for d in diags] == ["medium"]


def test_two_parameters_glued_together_are_all_the_callers(tmp_path: Path):
    diags = _diags(
        tmp_path,
        """\
        class M:
            def run(self, head, tail):
                return getattr(self, head + tail)()
        """,
    )
    assert [d.confidence for d in diags] == ["high"]
