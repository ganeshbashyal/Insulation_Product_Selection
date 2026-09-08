"""Tests for agent_core.answer_size_query, including SKU attachment."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent_core


def _family(family_id, name, manufacturer, widths, thicknesses, rvalues):
    return {
        "family_id": family_id, "name": name, "manufacturer": manufacturer,
        "widths": widths, "thicknesses": thicknesses, "rvalues": rvalues,
    }


def test_no_size_language_returns_none():
    assert agent_core.answer_size_query("What is your delivery time?") is None


def test_size_query_without_a_catalogue_match_flags_for_the_team(monkeypatch):
    monkeypatch.setattr(agent_core.size_index, "query", lambda **kw: [])
    reply = agent_core.answer_size_query("Do you have R6.0 in a 430mm width?")
    assert "flag it for the team" in reply


def test_size_query_lists_matching_families(monkeypatch):
    matches = [_family("FAM_A", "Family A", "Acme", [430], [90], [2.0])]
    monkeypatch.setattr(agent_core.size_index, "query", lambda **kw: matches)
    monkeypatch.setattr(agent_core.sku_catalogue, "available", lambda: False)
    reply = agent_core.answer_size_query("Do you have R2.0 in a 430mm width?")
    assert "Family A" in reply
    assert "Acme" in reply


def test_size_query_attaches_orderable_skus_when_catalogue_available(monkeypatch):
    """The SKU table augments the availability answer with real codes for the
    top match only, and must not be quoted when the table is unavailable."""
    matches = [_family("FAM_A", "Family A", "Acme", [430], [90], [2.0])]
    monkeypatch.setattr(agent_core.size_index, "query", lambda **kw: matches)
    monkeypatch.setattr(agent_core.sku_catalogue, "available", lambda: True)
    monkeypatch.setattr(
        agent_core.sku_catalogue,
        "skus_matching",
        lambda family_id, **kw: [{"sku": "acme-sku-1", "our_sku": "ACME1"}] if family_id == "FAM_A" else [],
    )
    reply = agent_core.answer_size_query("Do you have R2.0 in a 430mm width?")
    assert "acme-sku-1" in reply
    assert "Orderable SKU" in reply


def test_size_query_falls_back_to_internal_code_when_no_myob_sku(monkeypatch):
    matches = [_family("FAM_A", "Family A", "Acme", [430], [90], [2.0])]
    monkeypatch.setattr(agent_core.size_index, "query", lambda **kw: matches)
    monkeypatch.setattr(agent_core.sku_catalogue, "available", lambda: True)
    monkeypatch.setattr(
        agent_core.sku_catalogue,
        "skus_matching",
        lambda family_id, **kw: [{"sku": None, "our_sku": "ACME1"}],
    )
    reply = agent_core.answer_size_query("Do you have R2.0 in a 430mm width?")
    assert "ACME1" in reply


def test_size_query_omits_sku_line_when_none_match(monkeypatch):
    matches = [_family("FAM_A", "Family A", "Acme", [430], [90], [2.0])]
    monkeypatch.setattr(agent_core.size_index, "query", lambda **kw: matches)
    monkeypatch.setattr(agent_core.sku_catalogue, "available", lambda: True)
    monkeypatch.setattr(agent_core.sku_catalogue, "skus_matching", lambda family_id, **kw: [])
    reply = agent_core.answer_size_query("Do you have R2.0 in a 430mm width?")
    assert "Orderable SKU" not in reply
