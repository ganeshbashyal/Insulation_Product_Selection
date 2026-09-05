"""llm_client must never break the demo: an unreachable/unconfigured local
LLM server must fall back to the caller-supplied literal text unchanged."""
from __future__ import annotations

import llm_client


def test_generate_reply_returns_none_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:1")  # nothing listens here
    monkeypatch.setattr(llm_client, "OLLAMA_TIMEOUT_SECONDS", 1.0)
    assert llm_client.generate_reply("system", "hello") is None


def test_phrase_falls_back_to_original_text_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.setattr(llm_client, "OLLAMA_TIMEOUT_SECONDS", 1.0)
    original = "This exact text must survive unchanged."
    assert llm_client.phrase(original) == original
    assert llm_client.phrase(original, context={"family": "Example"}) == original


def test_ollama_available_is_false_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:1")
    assert llm_client.ollama_available() is False


def test_phrase_never_calls_llm_endpoint_when_fallback_returns_none(monkeypatch):
    calls = []

    def fake_generate_reply(system_prompt, user_prompt):
        calls.append((system_prompt, user_prompt))
        return None

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate_reply)
    original = "Some literal fallback message."
    assert llm_client.phrase(original) == original
    assert len(calls) == 1
