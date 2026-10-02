"""Post-recommendation lead capture: name, contact, callback, brief, families."""
from __future__ import annotations

import pytest

import agent_core
import interaction_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "interactions.sqlite3"
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", path)
    monkeypatch.setattr(agent_core.interaction_store, "DEFAULT_DB", path)
    return path


def _drive(conversation, scripted, site_id="local", limit=16):
    """Answer whichever question the conversation is actually asking."""
    replies = []
    for _ in range(limit):
        if conversation.done:
            break
        if conversation.step < len(agent_core.QUESTIONS):
            key = agent_core.QUESTIONS[conversation.step][0]
        else:
            key = agent_core.LEAD_QUESTIONS[conversation.lead_step][0]
        replies.append(agent_core.reply(conversation, scripted[key], site_id=site_id))
    return replies


SCRIPT = {
    "problem": "traffic noise through the front wall of my townhouse in Parramatta 2150",
    "name": "Hi, I'm John Smith",
    "application": "external wall, timber frame",
    "priority": "noise reduction",
    "conditions": "limited cavity space",
    "project": "residential retrofit",
    "locality": "Parramatta 2150",
    "requirements": "no NCC requirement",
    "contact_details": "0412 345 678 or john.smith@example.com",
    "callback_time": "Tuesday afternoon",
}


def test_lead_is_captured_after_the_recommendation(db):
    conversation = agent_core.Conversation()
    replies = _drive(conversation, SCRIPT)

    assert conversation.done is True
    # the recommendation must reach the customer before contact details are asked
    recommendation_turn = next(r for r in replies if "best fit" in r or "closest match" in r)
    assert "best number or email" in recommendation_turn

    lead = interaction_store.leads(db)[0]
    assert lead["customer_name"] == "John Smith"
    assert lead["phone"] == "0412345678"
    assert lead["email"] == "john.smith@example.com"
    assert lead["callback_time"] == "Tuesday afternoon"
    assert lead["problem_statement"].startswith("traffic noise through the front wall")
    assert lead["recommended_families"]
    assert lead["consent_at"]
    assert lead["consent_text"] == agent_core.LEAD_CONSENT_TEXT
    with interaction_store.connect(db) as connection:
        answers_json = connection.execute(
            "SELECT answers_json FROM conversations WHERE conversation_id = ?",
            (conversation.conversation_id,),
        ).fetchone()[0]
    assert "John Smith" not in answers_json


def test_lead_is_scoped_to_its_site(db):
    agent_core.reply(agent_core.Conversation(), "noise", site_id="local")
    interaction_store.save_lead("abc", site_id="site-a", customer_name="A", db_path=db)
    interaction_store.save_lead("def", site_id="site-b", customer_name="B", db_path=db)

    assert [row["customer_name"] for row in interaction_store.leads(db, site_id="site-a")] == ["A"]
    assert len(interaction_store.leads(db)) == 2


def test_customer_can_decline_to_leave_details(db):
    conversation = agent_core.Conversation()
    script = {**SCRIPT, "contact_details": "no thanks, I'd rather not"}
    _drive(conversation, script)

    assert conversation.done is True
    lead = interaction_store.leads(db)[0]
    assert lead["phone"] == ""
    assert lead["email"] == ""
    assert lead["customer_name"] == ""
    # declining must not lose the qualifying work already done
    assert lead["problem_statement"]
    assert lead["recommended_families"]
    # consent is only recorded when details were actually handed over
    assert lead["consent_at"] is None


def test_customer_can_decline_callback_time_without_losing_contact_details(db):
    conversation = agent_core.Conversation()
    _drive(conversation, {**SCRIPT, "callback_time": "No thanks, any time is fine"})

    lead = interaction_store.leads(db)[0]
    assert conversation.done
    assert lead["customer_name"] == "John Smith"
    assert lead["phone"] == "0412345678"
    assert lead["callback_time"] == "No thanks, any time is fine"
    assert lead["consent_at"]


def test_unparseable_contact_is_asked_once_more_then_accepted(db):
    conversation = agent_core.Conversation()
    for key in ("problem", "name", "conditions", "requirements", "application", "priority", "project", "locality"):
        if conversation.capturing_lead or conversation.done:
            break
        _drive(conversation, SCRIPT, limit=1)

    assert conversation.capturing_lead
    first = agent_core.reply(conversation, "just email me", site_id="local")
    assert "didn't catch" in first
    # a second unusable answer must not trap the customer in a loop
    second = agent_core.reply(conversation, "still no idea", site_id="local")
    assert "didn't catch" not in second
    assert conversation.done
    lead = interaction_store.leads(db)[0]
    assert lead["customer_name"] == ""
    assert lead["consent_at"] is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0412 345 678", {"phone": "0412345678", "email": ""}),
        ("+61 412 345 678", {"phone": "+61412345678", "email": ""}),
        ("02 9876 5432", {"phone": "0298765432", "email": ""}),
        ("jo@example.com", {"phone": "", "email": "jo@example.com"}),
        # digits inside an address must not be mistaken for a phone number
        ("jo1975@example.com", {"phone": "", "email": "jo1975@example.com"}),
        ("nothing useful here", {"phone": "", "email": ""}),
    ],
)
def test_parse_contact_details(text, expected):
    assert agent_core.parse_contact_details(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hi, I'm John Smith", "John Smith"),
        ("my name is Priya", "Priya"),
        ("it's Dave here", "Dave"),
        ("Sarah", "Sarah"),
    ],
)
def test_clean_name(text, expected):
    assert agent_core.clean_name(text) == expected


def test_problem_statement_does_not_repeat_the_backfilled_opening():
    opening = "traffic noise through the front wall of my townhouse"
    statement = agent_core.build_problem_statement(
        {"problem": opening, "application": opening, "conditions": "limited cavity"}
    )
    assert statement.count(opening) == 1
    assert "Constraints: limited cavity." in statement
