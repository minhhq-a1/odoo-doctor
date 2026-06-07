# tests/parsers/test_csv_candidates.py
"""Underscore->dot is ambiguous; candidate_model_names enumerates the options (A6)."""

from __future__ import annotations

from odoo_doctor.parsers.security_csv import candidate_model_names


def test_candidates_include_correct_dotted_name():
    cands = list(candidate_model_names("model_ir_actions_act_window"))
    assert "ir.actions.act_window" in cands
    # naive all-dots candidate is also present (and yielded first)
    assert cands[0] == "ir.actions.act.window"


def test_candidates_simple_model():
    cands = list(candidate_model_names("model_res_partner"))
    assert "res.partner" in cands


def test_candidates_single_segment():
    assert list(candidate_model_names("model_foo")) == ["foo"]


def test_candidates_handles_unprefixed():
    cands = list(candidate_model_names("res_partner"))
    assert "res.partner" in cands
