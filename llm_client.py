"""Optional local LLM phrasing layer.

Calls a self-hosted Ollama server (https://ollama.com) so no customer data or
enquiry content ever leaves infrastructure you control — there is no call to
OpenAI, Anthropic, Azure or any other third-party API.

This module only ever *rephrases* text that the calling code has already
decided (which question to ask, which family was selected, whether the
technical gate passed). It must never be used to decide those things itself,
so a missing/unreachable Ollama server is always a safe, silent fallback to
the caller-supplied literal text, not a broken demo.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:latest")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "15"))

GUARDRAIL_SYSTEM_PROMPT = """You are a warm, concise sales-engineer assistant for an insulation supplier.

Rephrase the supplied message naturally and conversationally. Rules that must never be broken:
- Do not add, remove or change any fact, product name, family name, number or claim from the supplied message.
- Do not select or imply a specific SKU, grade, thickness, quantity or price. Only the family named in the message may be mentioned.
- Do not state or imply that any product is NCC-compliant, fire-rated, BAL-rated or guarantees a result.
- Keep it to 1-3 short, natural sentences. No headings, no bullet points, no markdown except **bold** already present.
- If you cannot rephrase safely without breaking a rule above, return the original message unchanged.
"""


def ollama_available() -> bool:
    """Best-effort reachability check for the local Ollama server."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def generate_reply(system_prompt: str, user_prompt: str, max_tokens: int = 160, num_ctx: int | None = None) -> str | None:
    """Ask the local Ollama chat endpoint to produce a reply.

    Returns None on any failure (server down, timeout, bad response, model
    not pulled, etc.) so callers can fall back to their deterministic text.

    `max_tokens` bounds the reply; `num_ctx` sizes the context window and is
    auto-derived from the prompt length when omitted (a short chat rephrase
    stays small and fast, a long datasheet gets a large window).
    """
    # rough token estimate: ~4 chars per token, plus headroom for the reply
    if num_ctx is None:
        estimated = (len(system_prompt) + len(user_prompt)) // 4 + max_tokens + 256
        num_ctx = max(2048, min(16384, 1 << (estimated - 1).bit_length()))  # next power of two
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        # Keep the model loaded between calls (first call after idle is by far
        # the slowest) and bound the work.
        "keep_alive": "30m",
        "options": {"temperature": 0.4, "num_predict": max_tokens, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    content = (data.get("message") or {}).get("content", "").strip()
    return content or None


# Successful rephrasings are cached: the demo asks the same questions every
# conversation, so repeat phrasings are instant instead of another model
# round-trip. Failures are deliberately NOT cached, so a server that starts
# mid-session begins working on the next message without an app restart.
_PHRASE_CACHE: dict[tuple[str, str | None], str] = {}


def phrase(fallback_text: str, context: dict | None = None) -> str:
    """Return a naturally-phrased version of `fallback_text`, or `fallback_text`
    itself if the local LLM is unavailable or the call fails for any reason.

    `context` is optional supporting structured data (e.g. the matched family
    record) passed alongside the fallback text so the model has grounding
    facts, but it must not introduce anything not already present in
    `fallback_text`.
    """
    context_json = json.dumps(context, ensure_ascii=False) if context else None
    key = (fallback_text, context_json)
    if key in _PHRASE_CACHE:
        return _PHRASE_CACHE[key]
    user_prompt = fallback_text if not context_json else (
        f"Message to rephrase: {fallback_text}\n\nSupporting facts (for grounding only, do not add anything not already in the message): {context_json}"
    )
    rephrased = generate_reply(GUARDRAIL_SYSTEM_PROMPT, user_prompt)
    if rephrased:
        if len(_PHRASE_CACHE) < 256:
            _PHRASE_CACHE[key] = rephrased
        return rephrased
    return fallback_text
