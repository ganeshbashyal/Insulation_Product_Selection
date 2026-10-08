"""Persona-neutral, loopback-only Ollama model invocation utilities."""
from __future__ import annotations

import ipaddress
import json
import logging
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import llm_client

LOGGER = logging.getLogger(__name__)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def loopback_ollama_base() -> str:
    value = llm_client.OLLAMA_HOST
    parsed = urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("Local assistants require Ollama at an unauthenticated local HTTP address")
    try:
        loopback = parsed.hostname.casefold() == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = False
    if not loopback or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError("Local assistants block non-loopback Ollama endpoints")
    return value.rstrip("/")


def installed_models(timeout: float = 3.0) -> list[str]:
    base = loopback_ollama_base()
    request = Request(base + "/api/tags", headers={"Accept": "application/json"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Local Ollama is unavailable: {type(exc).__name__}") from exc
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise RuntimeError("Local Ollama returned an invalid model list")
    return sorted({row["name"] for row in rows
                   if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"]})


@lru_cache(maxsize=16)
def _chat_model_names(base: str, models: tuple[str, ...], timeout: float) -> tuple[str, ...]:
    if not models:
        return ()
    result = []
    for model in models:
        request = Request(
            base + "/api/show",
            data=json.dumps({"model": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Local Ollama could not inspect model capabilities: {type(exc).__name__}"
            ) from exc
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
            raise RuntimeError("Local Ollama returned invalid model capabilities")
        if "completion" in capabilities:
            result.append(model)
    return tuple(result)


def chat_models(timeout: float = 3.0) -> list[str]:
    """Return installed models that support generation, excluding embedding-only models."""
    base = loopback_ollama_base()
    return list(_chat_model_names(base, tuple(installed_models(timeout)), timeout))


def call_model(model: str, messages: list[dict], timeout: float = 90.0) -> str:
    if model not in chat_models():
        raise RuntimeError("Selected local model is not installed, chat-capable, or Ollama is unavailable")
    base = loopback_ollama_base()
    request = Request(
        base + "/api/chat",
        data=json.dumps({
            "model": model, "messages": messages, "stream": False,
            "keep_alive": llm_client.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": 0.2,
                "num_predict": 500,
                "num_ctx": 8192,
                "num_thread": 2,
            },
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Local model call failed (%s)", type(exc).__name__)
        raise RuntimeError(f"Local Ollama request failed: {type(exc).__name__}") from exc
    answer = (payload.get("message") or {}).get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Local Ollama returned an empty or malformed reply")
    return answer.strip()
