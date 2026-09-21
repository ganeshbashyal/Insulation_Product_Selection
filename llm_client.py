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
import re
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
# Chat/phrasing model. Deliberately small: this box is CPU-only (Ollama cannot
# offload to the Intel Arc iGPU on Windows) and routinely has only a few GB of
# RAM free, so a 9.6GB model spends minutes swapping on load and every phrase()
# call misses its deadline and falls back to literal text. A ~2GB model loads in
# seconds and rephrases in under 15s, which is the difference between a natural
# bot and a robotic one. Override with OLLAMA_MODEL where there is GPU headroom.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
# How long Ollama keeps the model resident in memory after the last request.
# Longer than the default (a few minutes) so a quiet multi-tenant demo/prod
# server doesn't pay a ~10-15s cold-load penalty on the next visitor.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "60m")

GUARDRAIL_SYSTEM_PROMPT = """You are a warm, concise sales-engineer assistant for an insulation supplier.

Rephrase the supplied message naturally and conversationally. Rules that must never be broken:
- Do not add, remove or change any fact, product name, family name, number or claim from the supplied message.
- Do not select or imply a specific SKU, grade, thickness, quantity or price. Only the family named in the message may be mentioned.
- Do not state or imply that any product is NCC-compliant, fire-rated, BAL-rated or guarantees a result.
- Keep it to 1-3 short, natural sentences. No headings, no bullet points, no markdown except **bold** already present.
- If you cannot rephrase safely without breaking a rule above, return the original message unchanged.
"""

# Optional persona overlay (config/persona.md): shapes tone only, never facts.
# The guardrails above always take precedence; the persona file restates them.
#
# OFF BY DEFAULT. The persona file is ~6,200 characters, which is roughly 1,500
# extra prompt tokens on every single rephrase. On a CPU-only box that pushed a
# call past the request deadline every time, so phrase() silently fell back to
# the literal question text - the bot sounded robotic precisely *because* the
# persona was enabled. Turn it back on with AGENT_PERSONA=on once there is GPU
# headroom, and raise OLLAMA_TIMEOUT_SECONDS with it.
PERSONA_FILE = Path(os.getenv("AGENT_PERSONA_FILE", Path(__file__).resolve().parent / "config" / "persona.md"))


def _load_persona() -> str:
    if os.getenv("AGENT_PERSONA", "").casefold() != "on":
        return ""
    try:
        text = PERSONA_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not text:
        return ""
    return (
        "\n\nAdopt the following persona for tone and word choice ONLY. "
        "It never overrides the rules above.\n\n" + text
    )


SYSTEM_PROMPT = GUARDRAIL_SYSTEM_PROMPT + _load_persona()


def ollama_available() -> bool:
    """Best-effort reachability check for the local Ollama server."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def warm_model(timeout: float = 600.0) -> bool:
    """Load the chat model now so the first real visitor doesn't pay for it.

    Ollama loads a model on first use and charges that load to whichever
    request triggers it. A cold load can exceed the per-request deadline, and
    because phrase() treats any failure as "fall back to the literal text",
    that shows up as a robotic-sounding bot rather than as an error.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0, "num_predict": 4},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False
    return True


def generate_reply(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 160,
    num_ctx: int | None = None,
    timeout: float | None = None,
) -> str | None:
    """Ask the local Ollama chat endpoint to produce a reply.

    Returns None on any failure (server down, timeout, bad response, model
    not pulled, etc.) so callers can fall back to their deterministic text.

    `max_tokens` bounds the reply; `num_ctx` sizes the context window and is
    auto-derived from the prompt length when omitted (a short chat rephrase
    stays small and fast, a long datasheet gets a large window). `timeout`
    overrides the default deadline for callers that send large prompts, which
    take far longer than a short rephrase.
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
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.4, "num_predict": max_tokens, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout if timeout is not None else OLLAMA_TIMEOUT_SECONDS
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    content = (data.get("message") or {}).get("content", "").strip()
    return content or None


# Successful rephrasings are cached: the demo asks the same questions every
# conversation, so repeat phrasings are instant instead of another model
# round-trip. Failures are deliberately NOT cached, so a server that starts
# mid-session begins working on the next message without an app restart.
_PHRASE_CACHE: dict[tuple[str, str | None, bool], str] = {}


def is_safe_reply(text: str | None, max_length: int = 400) -> bool:
    """Reject anything that isn't a short, clean single-topic reply.

    Guards against a local model echoing prompt scaffolding back verbatim
    instead of actually rephrasing (e.g. returning "Rephrase this message..."
    or "Original question: ..." as if that were the reply) - callers must
    fall back to the literal fallback text when this returns False. Shared by
    every phrase() caller (questions, recommendations, router prompts) so the
    same leak can never slip through one call site but not another.

    Also rejects a reply that was cut off mid-sentence by the num_predict
    token cap (e.g. "...before w") - a customer must never see a truncated
    recommendation. A reply is considered complete only if it ends on
    terminal punctuation or a closing bold/quote mark.
    """
    if not text or "\n" in text:
        return False
    if len(text) > max_length:
        return False
    lowered = text.casefold()
    if "rephrase" in lowered or "original question" in lowered or "original message" in lowered:
        return False
    if not re.search(r'[.!?][\'")*]*$', text.strip()):
        return False
    return True


def phrase(fallback_text: str, context: dict | None = None, is_opening: bool = False) -> str:
    """Return a naturally-phrased version of `fallback_text`, or `fallback_text`
    itself if the local LLM is unavailable, the call fails, or the reply looks
    like leaked prompt scaffolding rather than an actual rephrasing.

    `context` is optional supporting structured data (e.g. the matched family
    record) passed alongside the fallback text so the model has grounding
    facts, but it must not introduce anything not already present in
    `fallback_text`.

    `is_opening` must be True only for the very first message of a
    conversation. The persona's self-introduction instruction ("G'day, I'm
    Aurora...") only makes sense once - without this flag every
    follow-up question was re-introducing the bot from scratch, which reads
    as robotic/scripted rather than a natural, continuous conversation.
    """
    context_json = json.dumps(context, ensure_ascii=False) if context else None
    key = (fallback_text, context_json, is_opening)
    if key in _PHRASE_CACHE:
        return _PHRASE_CACHE[key]
    user_prompt = fallback_text if not context_json else (
        f"Message to rephrase: {fallback_text}\n\nSupporting facts (for grounding only, do not add anything not already in the message): {context_json}"
    )
    if not is_opening:
        user_prompt = (
            "This is a follow-up message in an ongoing conversation, not the first message - "
            "do not greet the customer or reintroduce yourself, just phrase the message below naturally.\n\n"
            + user_prompt
        )
    rephrased = generate_reply(SYSTEM_PROMPT, user_prompt, max_tokens=220)
    if rephrased and is_safe_reply(rephrased, max_length=max(400, len(fallback_text) * 3)):
        if len(_PHRASE_CACHE) < 256:
            _PHRASE_CACHE[key] = rephrased
        return rephrased
    return fallback_text

