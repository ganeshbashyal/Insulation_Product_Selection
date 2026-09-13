from __future__ import annotations

import agent_core
import interaction_store
from conversation_service import ConversationService
from router import MessageRouter


def test_conversation_state_round_trip_preserves_progress():
    conversation = agent_core.Conversation()
    agent_core.reply(conversation, "Cold external wall in my house")

    restored = agent_core.Conversation.from_dict(conversation.to_dict())

    assert restored.step == conversation.step
    assert restored.answers == conversation.answers
    assert restored.conversation_id == conversation.conversation_id


def test_service_answers_size_query_without_advancing_qualification(tmp_path, monkeypatch):
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", tmp_path / "interactions.sqlite3")
    service = ConversationService(use_llm=False, router=MessageRouter(use_llm=False))
    conversation = agent_core.Conversation()

    result = service.handle(conversation, "Is R2.5 available in 90mm?", site_id="local")

    assert result.category == "size-availability"
    assert result.retrieval_mode == "catalogue"
    assert conversation.step == 0


def test_service_advances_product_qualification(tmp_path, monkeypatch):
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", tmp_path / "interactions.sqlite3")
    service = ConversationService(use_llm=False, router=MessageRouter(use_llm=False))
    conversation = agent_core.Conversation()

    result = service.handle(
        conversation,
        "My external wall is cold in winter in my house",
        site_id="local",
    )

    assert result.category == "product-fit"
    assert result.retrieval_mode == "deterministic-ranking"
    assert conversation.step > 0
