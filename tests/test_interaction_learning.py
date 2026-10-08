"""Interaction learning store + headless agent flow."""
from __future__ import annotations

from datetime import datetime, timezone

import agent_core
import interaction_store


def finish_qualification(conversation):
    agent_core.reply(conversation, "finish now")
    answers = {
        "name": "Casey",
        "application": "external wall",
        "priority": "thermal comfort",
        "conditions": "no space constraints",
        "project": "residential retrofit",
        "locality": "Sydney 2000",
        "requirements": "no special requirement",
        "contact_details": "no thanks",
        "callback_time": "any time",
    }
    replies = []
    for _ in range(16):
        if conversation.done:
            return replies
        key = conversation.pending_field or (agent_core.QUESTIONS[conversation.step][0] if conversation.step < len(agent_core.QUESTIONS) else agent_core.LEAD_QUESTIONS[conversation.lead_step][0])
        replies.append(agent_core.reply(conversation, answers[key]))
    raise AssertionError("Qualification did not finish")


def test_conversation_logs_and_learns(tmp_path, monkeypatch):
    db = tmp_path / "interactions.sqlite3"
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", db)
    # agent_core captured DEFAULT_DB at import; patch its reference too
    monkeypatch.setattr(agent_core.interaction_store, "DEFAULT_DB", db)

    conversation = agent_core.Conversation()
    opening = conversation.next_prompt()
    assert opening == agent_core.OPENING

    # free-text opening carries application+priority+project+locality; the bot
    # should only ask the remaining qualifying questions
    replies = [agent_core.reply(conversation, "My external walls are freezing in winter in my Parramatta NSW 2150 house")]
    replies.extend(finish_qualification(conversation))

    assert conversation.done is True
    assert conversation.recommendation is None
    assert conversation.candidates
    assert not any("best fit" in r or "closest match" in r for r in replies)

    pending = interaction_store.pending_review(db)
    assert any(row["conversation_id"] == conversation.conversation_id for row in pending)

    interaction_store.record_outcome(conversation.conversation_id, "approved", "tester", db_path=db)
    stats = interaction_store.family_stats(db)
    assert stats == []  # An enquiry outcome does not approve any candidate.
    assert interaction_store.leads(db)[0]["sales_brief"]["approval"] is None


def test_rejection_report_lists_corrected(tmp_path, monkeypatch):
    db = tmp_path / "interactions.sqlite2.sqlite3"
    monkeypatch.setattr(agent_core.interaction_store, "DEFAULT_DB", db)

    conversation = agent_core.Conversation()
    agent_core.reply(conversation, "noise through the wall between floors in my house in Sydney 2000")
    finish_qualification(conversation)
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


def test_housekeeping_uses_30_day_conversation_and_12_month_lead_cutoffs(tmp_path):
    db = tmp_path / "interactions.sqlite3"
    now = datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc)
    interaction_store.initialise(db)
    with interaction_store.connect(db) as connection:
        connection.execute("INSERT INTO sites (site_id, synced_at) VALUES ('local', ?)", (now.isoformat(),))
        for conversation_id, occurred_at in (
            ("old", "2026-09-06T19:59:59+00:00"),
            ("boundary", "2026-09-06T20:00:00+00:00"),
        ):
            connection.execute(
                """INSERT INTO conversations
                   (conversation_id, site_id, occurred_at, answers_json, candidates_json)
                   VALUES (?, 'local', ?, '{}', '[]')""",
                (conversation_id, occurred_at),
            )
            connection.execute(
                """INSERT INTO outcomes
                   (conversation_id, site_id, decided_at, reviewer, outcome)
                   VALUES (?, 'local', ?, 'reviewer', 'approved')""",
                (conversation_id, occurred_at),
            )
        for conversation_id, created_at in (
            ("old-lead", "2025-10-06T19:59:59+00:00"),
            ("boundary-lead", "2025-10-06T20:00:00+00:00"),
        ):
            connection.execute(
                """INSERT INTO leads (conversation_id, site_id, created_at)
                   VALUES (?, 'local', ?)""",
                (conversation_id, created_at),
            )

    deleted = interaction_store.purge_expired(now=now, db_path=db)

    assert deleted == {"turns": 0, "conversations": 1, "outcomes": 1, "leads": 1}
    with interaction_store.connect(db) as connection:
        assert connection.execute(
            "SELECT conversation_id FROM conversations"
        ).fetchall() == [("boundary",)]
        assert connection.execute(
            "SELECT conversation_id FROM outcomes"
        ).fetchall() == [("boundary",)]
        assert connection.execute(
            "SELECT conversation_id FROM leads"
        ).fetchall() == [("boundary-lead",)]
