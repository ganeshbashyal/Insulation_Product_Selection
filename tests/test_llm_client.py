"""The shared local model utility never selects a persona implicitly."""
from __future__ import annotations

import json

import llm_client
import pytest
from aurora_persona import AURORA_CONTRACT


def _aurora_prompt() -> str:
    assert AURORA_CONTRACT.model_prompt is not None
    return AURORA_CONTRACT.model_prompt


def test_generate_reply_returns_none_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.setattr(llm_client, "OLLAMA_TIMEOUT_SECONDS", 1.0)
    assert llm_client.generate_reply("system", "hello") is None
    assert llm_client._MODEL_CALL_FAILURE.get() is not None


def test_phrase_falls_back_to_original_text_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.setattr(llm_client, "OLLAMA_TIMEOUT_SECONDS", 1.0)
    original = "This exact text must survive unchanged."
    assert llm_client.phrase(original, system_prompt=_aurora_prompt()) == original
    assert llm_client.phrase(
        original, context={"family": "Example"}, system_prompt=_aurora_prompt(),
    ) == original


def test_ollama_available_is_false_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:1")
    assert llm_client.ollama_available() is False


def test_phrase_passes_the_explicit_persona_prompt(monkeypatch):
    calls = []

    def fake_generate_reply(system_prompt, user_prompt, **kwargs):
        calls.append((system_prompt, user_prompt))
        return None

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate_reply)
    llm_client._PHRASE_CACHE.clear()
    original = "Some literal fallback message."
    assert llm_client.phrase(original, system_prompt=_aurora_prompt()) == original
    assert calls[0][0] == _aurora_prompt()


def test_phrase_cache_is_partitioned_by_persona_prompt(monkeypatch):
    calls = []

    def fake_generate_reply(system_prompt, user_prompt, **kwargs):
        calls.append(system_prompt)
        return "A concise reply."

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate_reply)
    llm_client._PHRASE_CACHE.clear()
    first = _aurora_prompt()
    second = first + "\nA distinct test persona."
    text = "A concise reply."
    assert llm_client.phrase(text, system_prompt=first) == text
    assert llm_client.phrase(text, system_prompt=second) == text
    assert calls == [first, second]
    llm_client._PHRASE_CACHE.clear()


def test_phrase_cache_and_model_request_follow_request_local_model(monkeypatch):
    calls = []

    def fake_generate_reply(system_prompt, user_prompt, **kwargs):
        calls.append(kwargs["model"])
        return "A concise reply."

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate_reply)
    llm_client._PHRASE_CACHE.clear()
    original = "Some literal fallback message."
    try:
        with llm_client.using_model("gemma4:latest"):
            assert llm_client.phrase(original, system_prompt=_aurora_prompt()) == "A concise reply."
        with llm_client.using_model("llama3.2:latest"):
            assert llm_client.phrase(original, system_prompt=_aurora_prompt()) == "A concise reply."
    finally:
        llm_client._PHRASE_CACHE.clear()
    assert calls == ["gemma4:latest", "llama3.2:latest"]


def test_generation_seed_is_scoped_and_sent_to_ollama(monkeypatch):
    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"message":{"content":"A local reply."}}'

    def fake_urlopen(request, **_kwargs):
        captured.append(json.loads(request.data))
        return Response()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    with llm_client.using_model("llama3.2:latest", seed=73, num_thread=2):
        assert llm_client.generate_reply("system", "user") == "A local reply."
    assert captured[0]["model"] == "llama3.2:latest"
    assert captured[0]["options"]["seed"] == 73
    assert captured[0]["options"]["num_thread"] == 2
    assert llm_client._GENERATION_SEED.get() is None
    assert llm_client._GENERATION_THREADS.get() is None
    assert llm_client._MODEL_CALL_FAILURE.get() is None


def test_local_only_model_context_disables_proxies_and_redirects(monkeypatch):
    captured = []

    class Opener:
        def open(self, request, timeout):
            captured.append((request.full_url, timeout))
            return "local-response"

    def fake_build_opener(*handlers):
        captured.append(tuple(type(handler).__name__ for handler in handlers))
        return Opener()

    monkeypatch.setattr(llm_client.urllib.request, "build_opener", fake_build_opener)
    with llm_client.using_model("llama3.2:latest", local_only=True):
        result = llm_client._open_ollama(
            llm_client.urllib.request.Request("http://127.0.0.1:11434/api/chat"),
            timeout=3,
        )

    assert result == "local-response"
    assert captured[0] == ("ProxyHandler", "_NoRedirect")
    assert captured[1] == ("http://127.0.0.1:11434/api/chat", 3)


def test_generation_rejects_invalid_seed_before_request(monkeypatch):
    monkeypatch.setattr(
        llm_client.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("No request expected")),
    )
    with pytest.raises(ValueError, match="non-negative integer"):
        llm_client.generate_reply("system", "user", seed=True)


def test_model_context_rejects_invalid_thread_limit():
    with pytest.raises(ValueError, match="thread count"):
        with llm_client.using_model("llama3.2:latest", num_thread=0):
            pass


def test_shared_model_module_has_no_default_persona_prompt():
    assert not hasattr(llm_client, "SYSTEM_PROMPT")
    assert not hasattr(llm_client, "PERSONA_FILE")
