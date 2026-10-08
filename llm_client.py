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
import logging
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
import urllib.error
import urllib.request

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
# Keep this short by default: this local Windows host is CPU-only with limited
# free RAM, and pinning several models for an hour was enough to push it into
# swap-thrashing. Operators can raise OLLAMA_KEEP_ALIVE on a GPU/prod host.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m")
LOGGER = logging.getLogger(__name__)
_MODEL_OVERRIDE: ContextVar[str | None] = ContextVar("aurora_model_override", default=None)
_GENERATION_SEED: ContextVar[int | None] = ContextVar("aurora_generation_seed", default=None)
_LOCAL_ONLY: ContextVar[bool] = ContextVar("aurora_model_local_only", default=False)
_GENERATION_THREADS: ContextVar[int | None] = ContextVar("aurora_generation_threads", default=None)
_MODEL_CALL_FAILURE: ContextVar[str | None] = ContextVar("aurora_model_call_failure", default=None)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _open_ollama(request: urllib.request.Request, timeout: float):
    if _LOCAL_ONLY.get():
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
        )
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


@contextmanager
def using_model(
    model: str | None,
    *,
    seed: int | None = None,
    local_only: bool = False,
    num_thread: int | None = None,
):
    if num_thread is not None and (
        isinstance(num_thread, bool) or not isinstance(num_thread, int) or not 1 <= num_thread <= 128
    ):
        raise ValueError("Local generation thread count must be an integer from 1 to 128")
    model_token = _MODEL_OVERRIDE.set(model)
    seed_token = _GENERATION_SEED.set(seed)
    local_only_token = _LOCAL_ONLY.set(local_only or _LOCAL_ONLY.get())
    thread_token = _GENERATION_THREADS.set(
        num_thread if num_thread is not None else _GENERATION_THREADS.get()
    )
    try:
        yield
    finally:
        _GENERATION_THREADS.reset(thread_token)
        _LOCAL_ONLY.reset(local_only_token)
        _GENERATION_SEED.reset(seed_token)
        _MODEL_OVERRIDE.reset(model_token)


def ollama_available() -> bool:
    """Best-effort reachability check for the local Ollama server."""
    try:
        request = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with _open_ollama(request, timeout=2) as response:
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
        with _open_ollama(request, timeout=timeout) as response:
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
    *,
    model: str | None = None,
    seed: int | None = None,
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
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
        raise ValueError("Local generation seed must be a non-negative integer")
    _MODEL_CALL_FAILURE.set(None)
    generation_seed = seed if seed is not None else _GENERATION_SEED.get()
    options = {"temperature": 0.4, "num_predict": max_tokens, "num_ctx": num_ctx}
    generation_threads = _GENERATION_THREADS.get()
    if generation_threads is not None:
        options["num_thread"] = generation_threads
    if generation_seed is not None:
        if isinstance(generation_seed, bool) or not isinstance(generation_seed, int) or generation_seed < 0:
            raise ValueError("Local generation seed must be a non-negative integer")
        options["seed"] = generation_seed
    payload = {
        "model": model or _MODEL_OVERRIDE.get() or OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        # Keep the model loaded between calls (first call after idle is by far
        # the slowest) and bound the work.
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _open_ollama(
            request, timeout=timeout if timeout is not None else OLLAMA_TIMEOUT_SECONDS
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        _MODEL_CALL_FAILURE.set(type(exc).__name__)
        LOGGER.warning("Local wording unavailable (%s); retaining grounded text", type(exc).__name__)
        return None
    content = (data.get("message") or {}).get("content", "").strip()
    if not content:
        _MODEL_CALL_FAILURE.set("empty_reply")
    return content or None


# Successful rephrasings are cached: the demo asks the same questions every
# conversation, so repeat phrasings are instant instead of another model
# round-trip. Failures are deliberately NOT cached, so a server that starts
# mid-session begins working on the next message without an app restart.
_PHRASE_CACHE: dict[tuple[str, str | None, bool, str, str], str] = {}


def is_safe_reply(text: str | None, max_length: int = 400, source: str | None = None) -> bool:
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

    When `source` is given, also rejects a reply that emphasises a product
    name the source never mentioned. A small model asked to rephrase
    "what type of roof is it?" invented "**Thermatech 400**" - a product that
    does not exist. Naming a product is exactly the decision this module must
    never make, so an unsourced bold span is treated as fabrication.
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
    if source is not None:
        source_lowered = source.casefold()
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source))
        if not set(re.findall(r"\d+(?:\.\d+)?", text)).issubset(source_numbers):
            return False
        if "?" in source and (text.count("?") != source.count("?")):
            return False
        for claim in ("guarantee", "compliant", "fire-rated", "fire rated", "soundproof", "will", "ensure"):
            if re.search(rf"\b{re.escape(claim)}\b", lowered) and not re.search(rf"\b{re.escape(claim)}\b", source_lowered):
                return False
        for emphasised in re.findall(r"\*\*(.+?)\*\*", text):
            if emphasised.casefold().strip() not in source_lowered:
                return False
    return True


def phrase(
    fallback_text: str,
    context: dict | None = None,
    is_opening: bool = False,
    *,
    system_prompt: str,
) -> str:
    """Return a naturally-phrased version of `fallback_text`, or `fallback_text`
    itself if the local LLM is unavailable, the call fails, or the reply looks
    like leaked prompt scaffolding rather than an actual rephrasing.

    `system_prompt` must be supplied by the calling persona at runtime; this
    shared utility has no default persona or implicit prompt.

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
    model = _MODEL_OVERRIDE.get() or OLLAMA_MODEL
    key = (fallback_text, context_json, is_opening, system_prompt, model)
    if key in _PHRASE_CACHE:
        return _PHRASE_CACHE[key]
    # Always label the text as the thing to rephrase. Passing a bare question
    # as the user turn reads to a small model as a question to *answer*, so it
    # replied in the customer's voice ("I'm here to discuss...") or invented a
    # scenario outright. Only a large model reliably infers "rephrase" from the
    # system prompt alone; the label costs nothing and removes the ambiguity.
    user_prompt = f"Message to rephrase: {fallback_text}"
    if context_json:
        user_prompt += (
            "\n\nSupporting facts (for grounding only, do not add anything not "
            f"already in the message): {context_json}"
        )
    if not is_opening:
        user_prompt = (
            "This is a follow-up message in an ongoing conversation, not the first message - "
            "do not greet the customer or reintroduce yourself, just phrase the message below naturally.\n\n"
            + user_prompt
        )
    rephrased = generate_reply(system_prompt, user_prompt, max_tokens=220, model=model)
    safety_source = fallback_text if context_json is None else fallback_text + " " + context_json
    if rephrased and is_safe_reply(
        rephrased,
        max_length=max(400, len(fallback_text) * 3),
        source=safety_source,
    ):
        if len(_PHRASE_CACHE) < 256:
            _PHRASE_CACHE[key] = rephrased
        return rephrased
    return fallback_text
