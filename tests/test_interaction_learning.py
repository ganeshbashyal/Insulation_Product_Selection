"""Interaction learning store + headless agent flow."""
from __future__ import annotations

import agent_core
import interaction_store


def test_conversation_logs_and_learns(tmp_path, monkeypatch):
    db = tmp_path / "interactions.sqlite3"
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", db)
    # agent_core captured DEFAULT_DB at import; patch its reference too
    monkeypatch.setattr(agent_core.interaction_store, "DEFAULT_DB", db)

    conversation = agent_core.Conversation()
    opening = conversation.next_prompt()
    assert "own words" in opening

    # free-text opening carries application+priority+project+locality; the bot
    # should only ask the remaining qualifying questions
    replies = [agent_core.reply(conversation, "My external walls are freezing in winter in my Parramatta NSW 2150 house")]
    while not conversation.done:
        replies.append(agent_core.reply(conversation, "no special requirement, callback please"))

    assert conversation.done is True
    assert conversation.recommendation is not None
    assert conversation.recommendation["family_id"]
    assert any("best fit" in r or "closest match" in r for r in replies)

    pending = interaction_store.pending_review(db)
    assert any(row["conversation_id"] == conversation.conversation_id for row in pending)

    interaction_store.record_outcome(conversation.conversation_id, "approved", "tester", db_path=db)
    stats = interaction_store.family_stats(db)
    row = next(r for r in stats if r["family_id"] == conversation.recommendation["family_id"])
    assert row["approved"] == 1


def test_rejection_report_lists_corrected(tmp_path, monkeypatch):
    db = tmp_path / "interactions.sqlite2.sqlite3"
    monkeypatch.setattr(agent_core.interaction_store, "DEFAULT_DB", db)

    conversation = agent_core.Conversation()
    agent_core.reply(conversation, "noise through the wall between floors in my house in Sydney 2000")
    while not conversation.done:
        agent_core.reply(conversation, "no special requirement, just call me")
    assert conversation.done

    interaction_store.record_outcome(
        conversation.conversation_id, "edited", "tester",
        corrected_family_id="FLETCHER_SOUNDBREAK", note="wrong element", db_path=db,
    )
    report = interaction_store.rejection_report(db)
    assert report and report[0]["corrected_family_id"] == "FLETCHER_SOUNDBREAK"


def test_outcome_validation_rejects_unknown(tmp_path):
    with __import__("pytest").raises(ValueError):
        interaction_store.record_outcome("x", "maybe", "tester", db_path=tmp_path / "db.sqlite3")
