"""Tests for smart_questioner.py's rephrasing safety.

Covers the bug where a raw meta-prompt ("Rephrase this question...
Original question: ... Rephrased:") was handed to the LLM as if it were the
message to rephrase, and a small local model sometimes echoed it back
verbatim to the customer instead of returning an actual rephrased question.
"""
from unittest.mock import patch

from smart_questioner import SmartQuestioner, _looks_like_a_question


class LiteConversation:
    def __init__(self, answers):
        self.answers = answers


def test_looks_like_a_question_accepts_normal_text():
    assert _looks_like_a_question("Are you working on a new build or retrofit?")
    assert _looks_like_a_question("Is this for a new place, or updating what's already there?")


def test_looks_like_a_question_rejects_none_and_empty():
    assert not _looks_like_a_question(None)
    assert not _looks_like_a_question("")


def test_looks_like_a_question_rejects_multiline_output():
    leaked = "Rephrase this question to sound natural...\n\nOriginal question: Are you working on a new build or retrofit?\n\nRephrased (natural, 1-2 sentences, Australian construction language):"
    assert not _looks_like_a_question(leaked)


def test_looks_like_a_question_rejects_prompt_scaffolding_even_single_line():
    assert not _looks_like_a_question("Original question: Are you working on a new build or retrofit?")
    assert not _looks_like_a_question("Here is how I would rephrase this question naturally.")


def test_looks_like_a_question_rejects_overly_long_text():
    assert not _looks_like_a_question("Are you " + "very " * 60 + "sure about this build?")


def test_rephrase_naturally_falls_back_when_llm_leaks_prompt_scaffolding():
    """The exact bug: llm_client.phrase() returns the meta-prompt verbatim -
    the caller must fall back to the plain deterministic question, not show
    the leaked text to the customer."""
    sq = SmartQuestioner(use_llm=True)
    leaked_response = (
        "Rephrase this question to sound natural and conversational, as if asked by an "
        "experienced insulation adviser who understands: \"on the ceiling\"\n\n"
        "Original question: Are you working on a new build or retrofit?\n\n"
        "Rephrased (natural, 1-2 sentences, Australian construction language):"
    )
    with patch("smart_questioner.llm_client.phrase", return_value=leaked_response):
        result = sq._rephrase_naturally("Are you working on a new build or retrofit?", "on the ceiling")
    assert result == "Are you working on a new build or retrofit?"


def test_rephrase_naturally_uses_llm_output_when_it_looks_valid():
    sq = SmartQuestioner(use_llm=True)
    with patch("smart_questioner.llm_client.phrase", return_value="New build, or renovating an existing place?"):
        result = sq._rephrase_naturally("Are you working on a new build or retrofit?", "on the ceiling")
    assert result == "New build, or renovating an existing place?"


def test_rephrase_naturally_passes_literal_question_not_a_meta_prompt():
    """llm_client.phrase() must receive the literal question as fallback_text,
    not a hand-built instruction wrapping it - that double-prompting is what
    caused the leak in the first place."""
    sq = SmartQuestioner(use_llm=True)
    with patch("smart_questioner.llm_client.phrase", return_value="ok") as mock_phrase:
        sq._rephrase_naturally("Are you working on a new build or retrofit?", "on the ceiling")
    args, kwargs = mock_phrase.call_args
    fallback_text = args[0] if args else kwargs.get("fallback_text")
    assert fallback_text == "Are you working on a new build or retrofit?"
    assert "Rephrase" not in fallback_text
    assert "Original question" not in fallback_text


def test_rephrase_naturally_swallows_llm_client_exceptions():
    sq = SmartQuestioner(use_llm=True)
    with patch("smart_questioner.llm_client.phrase", side_effect=RuntimeError("boom")):
        result = sq._rephrase_naturally("Are you working on a new build or retrofit?", "on the ceiling")
    assert result == "Are you working on a new build or retrofit?"


def test_next_question_never_leaks_prompt_text_to_a_short_customer_answer():
    """End-to-end: a short customer answer ("on the ceiling") must still
    produce a clean single-line question, never raw prompt scaffolding."""
    sq = SmartQuestioner(use_llm=True)
    conv = LiteConversation({"problem": "ceiling is cold in winter", "application": "on the ceiling"})
    leaked_response = (
        "Rephrase this question to sound natural and conversational, as if asked by an "
        "experienced insulation adviser who understands: \"on the ceiling\"\n\n"
        "Original question: Are you working on a new build or retrofit?\n\n"
        "Rephrased (natural, 1-2 sentences, Australian construction language):"
    )
    with patch("smart_questioner.llm_client.phrase", return_value=leaked_response):
        result = sq.next_question(conv)
    assert "Rephrase" not in result
    assert "Original question" not in result
    assert result == "Are you working on a new build or retrofit?"
