from __future__ import annotations

import json

import local_model


def test_call_model_forces_loopback_request_without_proxy_and_caps_threads(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"message": {"content": "Local response."}}).encode()

    class Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(local_model, "chat_models", lambda: ["llama3.2:latest"])
    monkeypatch.setattr(local_model, "loopback_ollama_base", lambda: "http://127.0.0.1:11434")
    monkeypatch.setattr(local_model, "build_opener", fake_build_opener)

    answer = local_model.call_model(
        "llama3.2:latest",
        [{"role": "user", "content": "Synthetic local test."}],
    )

    request = captured["request"]
    payload = json.loads(request.data)
    assert answer == "Local response."
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert payload["options"]["num_thread"] == 2
    assert captured["handlers"][0].proxies == {}
    assert captured["timeout"] == 90.0
