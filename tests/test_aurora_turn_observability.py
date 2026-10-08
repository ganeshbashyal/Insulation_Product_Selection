from __future__ import annotations

from fastapi.testclient import TestClient

import agent_core
import interaction_store
import web_agent
from conversation_service import ConversationService


def test_binary_answers_are_valid_only_for_compatible_discovery_fields():
    conversation = agent_core.Conversation(
        mode="discovery",
        step=1,
        pending_field="application",
    )
    answer = agent_core.reply(conversation, "yes")
    assert "missed the context" in answer
    assert conversation.pending_field == "application"
    assert "application" not in conversation.answers

    conversation.pending_field = "moisture"
    answer = agent_core.reply(conversation, "no")
    assert "No moisture or exposure concerns" in conversation.answers["moisture"]
    assert conversation.discovery_status["moisture"] == "provided"
    assert "No problem" not in answer


def test_conflicting_application_prompts_for_focus_and_then_replaces_conflict():
    service = ConversationService(use_llm=False)
    conversation = agent_core.Conversation()
    first = service.handle(conversation, "My wall is cold and the roof is noisy")
    assert "both the wall and roof" in first.reply
    assert conversation.discovery_status["application"] == "conflict"
    assert "conflicting_application_requires_clarification" in first.review_labels
    assert conversation.pending_field == "application"

    resolved = service.handle(conversation, "The roof should be reviewed first")
    assert conversation.discovery_status["application"] == "provided"
    assert conversation.answers["application"] == "The roof should be reviewed first"
    assert conversation.pending_field != "application"
    assert "conflicting_application_requires_clarification" not in resolved.review_labels


def test_bare_answers_do_not_become_problem_statements_and_new_projects_reset_context():
    conversation = agent_core.Conversation()
    agent_core.reply(conversation, "yes")
    assert "problem" not in conversation.answers
    agent_core.reply(conversation, "unknown")
    assert "problem" not in conversation.answers

    conversation.answers["problem"] = "Old wall project"
    conversation.page_context = {"page": "old"}
    conversation.family_review_id = "OLD_FAMILY"
    previous_id = conversation.conversation_id
    reply = agent_core.reply(conversation, "New project: my roof is hot")
    assert "problem" in conversation.answers and "Old wall" not in conversation.answers["problem"]
    assert conversation.conversation_id != previous_id
    assert conversation.page_context is None
    assert conversation.family_review_id is None
    assert "roof" in reply.casefold() or conversation.answers.get("application")


def test_restored_state_rejects_invalid_progress_and_types():
    for data in (
        {"step": -1, "answers": {}},
        {"step": 1, "answers": {"application": ["wall"]}},
        {"step": 1, "answers": {}, "done": "false"},
        {"step": 1, "answers": {}, "pending_field": "secret"},
        {"step": 1, "answers": {}, "discovery_status": {"application": "other"}},
    ):
        try:
            agent_core.Conversation.from_dict(data)
        except ValueError:
            continue
        raise AssertionError(f"invalid state was accepted: {data!r}")


def test_turn_history_is_site_scoped_and_requires_operator_key(tmp_path, monkeypatch):
    database = tmp_path / "interactions.sqlite3"
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", database)
    monkeypatch.setenv("AURORA_LEAD_ADMIN_KEY", "turn-operator-key")
    interaction_store.log_turn(
        site_id="local", session_id="session-1", conversation_id="conversation-1",
        turn_number=0, user_message="", assistant_reply="Opening.",
        category="greeting", retrieval_mode="none", human_review_required=False,
    )
    interaction_store.log_turn(
        site_id="local", session_id="session-1", conversation_id="conversation-1",
        turn_number=1, user_message="My wall is cold.",
        assistant_reply="Where is the issue?", category="product-fit",
        retrieval_mode="needs-capture", human_review_required=True,
        review_labels=("customer_project_facts_unverified", "internal_human_review_required"),
    )
    interaction_store.log_turn(
        site_id="other", session_id="session-2", conversation_id="conversation-2",
        turn_number=1, user_message="Other site.", assistant_reply="Other reply.",
        category="informational", retrieval_mode="local-glossary",
        human_review_required=False,
    )
    app = web_agent.app
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 54321))
    assert client.get("/api/admin/interactions?site_id=local").status_code == 401
    authorized = client.get(
        "/api/admin/interactions?site_id=local&limit=1",
        headers={"X-Aurora-Lead-Admin-Key": "turn-operator-key"},
    )
    assert authorized.status_code == 200
    assert len(authorized.json()["turns"]) == 1
    assert authorized.json()["turns"][0]["review_labels"] == [
        "customer_project_facts_unverified", "internal_human_review_required",
    ]
    older = client.get(
        f"/api/admin/interactions?site_id=local&limit=1&before_turn_id={authorized.json()['next_cursor']}",
        headers={"X-Aurora-Lead-Admin-Key": "turn-operator-key"},
    )
    assert len(older.json()["turns"]) == 1
    assert older.json()["turns"][0]["assistant_reply"] == "Opening."
    assert interaction_store.turn_history("other", db_path=database)["turns"][0]["session_id"] == "session-2"


def test_turn_history_and_handoff_routes_are_disabled_in_serving_mode(monkeypatch):
    monkeypatch.setattr(web_agent, "SERVING_ONLY", True)
    monkeypatch.setenv("AURORA_LEAD_ADMIN_KEY", "turn-operator-key")
    client = TestClient(
        web_agent.app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 54321),
    )
    headers = {
        "X-Aurora-Lead-Admin-Key": "turn-operator-key",
        "Origin": "http://127.0.0.1",
    }
    assert client.get("/api/admin/interactions", headers=headers).status_code == 404
    assert client.post(
        "/api/admin/briefs/example/handoff",
        headers=headers,
        json={"operator_approved": True},
    ).status_code == 404
