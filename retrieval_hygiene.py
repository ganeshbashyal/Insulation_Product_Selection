"""Shared hygiene rules for family retrieval fields.

The retrieval blocks in ``knowledge/*/research/*.json`` are produced by several
pipelines (AI-studio batches, knowledge-base text dumps). The text-dump parser
in particular leaked line-wrapped fragments, section-label bleed and prose
sentences into what must be short matching terms. Because
``agent_core.load_families`` merges these lists straight into the ranker's
keywords/applications/not_for, every polluted entry either wastes matching
cycles or (worst case, ``not_for``) fires a spurious score penalty.

This module is the single source of truth for what a valid retrieval term
looks like. It is used by:
  - ``scripts/clean_retrieval_fields.py``  (one-off + repeatable cleanup)
  - ``scripts/ingest_knowledge_base_txt.py`` and ``scripts/studio_batch.py``
    (so future ingests arrive clean)
  - ``agent_core``   (defensive short-term filter at ranker-merge time)

Terms are salvaged before they are rejected: whitespace collapse fixes
line-wrap artifacts, and known label prefixes are stripped so the payload
("structural framing batten") survives even when the wrapper
("not_for): Not a structural framing batten") would not.
"""
from __future__ import annotations

import re

# Per-field maximum word counts. search/problem keywords and placement feed the
# lexical ranker so they must be short noun phrases; use_cases / not_for are
# scenario descriptions that also feed embeddings, so they may run longer.
WORD_CAPS = {
    "search_keywords": 6,
    "problem_keywords": 10,
    "placement": 4,
    "not_for": 10,
    "use_cases": 15,
    "priority_fit": 2,
}

LIST_FIELDS = tuple(WORD_CAPS)

# closed vocabulary from the studio batch prompt; anything else is dropped
PRIORITY_FIT_VOCAB = {
    "thermal", "acoustic", "condensation", "fire",
    "sustainability", "easy_install", "budget",
}

# canonical building elements (studio prompt list); kept verbatim regardless of
# the placement word cap
PLACEMENT_VOCAB = {
    "ceiling", "wall", "internal wall", "external wall", "floor", "underfloor",
    "between floors", "roof", "roofline", "pipe", "duct", "shed", "subfloor",
}

# section labels from the knowledge-base dumps that bleed into split lists
_LABEL_BLEED = re.compile(
    r"(?:negative filter|positive recommendation rule|accessories upsell|"
    r"complementary upsell|substitute mapping|search triggers|problem triggers|"
    r"priority fit|placement)\s*[:(]",
    re.I,
)

# leading wrappers to strip so the payload can be judged on its own
_NOT_FOR_PREFIX = re.compile(r"^(?:-\s*)?(?:negative filter\s*)?\(?not_for\)?\s*:?\s*(?:not\s+(?:a|an|for)\s+|not\s+)?", re.I)
_LEAD_JUNK = re.compile(r"^[\s\-•*\"'–—]+")

# instruction fragments masquerading as matching terms (split residue from
# "When X, recommend Y" style rule sentences in the knowledge-base dumps)
_INSTRUCTION_LEAD = re.compile(
    r"^(?:recommend|specify|use|when|must|avoid|install|stack|default|and|or|to|for)\b",
    re.I,
)

# a term ending on one of these is a truncated fragment, not a phrase
_DANGLING_TAIL = {
    "and", "or", "to", "for", "with", "without", "the", "a", "an", "of",
    "in", "on", "from", "into", "while", "must", "use", "where", "when",
    "recommend", "specify", "ensure",
}

# standalone words too generic to be a matching term (mid-sentence split residue)
_GENERIC_SOLO = {
    "high", "low", "and", "or", "the", "with", "without", "where", "when",
    "need", "want", "use", "spaces", "other", "more", "plus", "areas",
    "zones", "zone",
}

# pipeline artifacts that leaked into term lists
_ARTIFACT = re.compile(r"^batch\s*\d+$", re.I)


def _normalise(term: str) -> str:
    text = str(term)
    # mojibake: degree sign ("75�C"), dash in ranges ("38mm�50mm")
    text = re.sub(r"�(?=C\b)", "°", text)
    text = re.sub(r"(?<=\w)�(?=\d)", "-", text)
    text = text.replace("�", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = _LEAD_JUNK.sub("", text)
    # a lone "(" with no closing bracket marks a truncation -> cut there
    if "(" in text and ")" not in text:
        text = text.split("(", 1)[0].rstrip(" ,-")
    # strip wrapper junk until stable: quotes, sentence periods, stray brackets
    # can nest (e.g. a term ending in '".' needs two passes)
    for _ in range(4):
        before = text
        text = text.strip("\"'").strip()
        # single trailing sentence period (keep decimals like "R2.5" intact)
        if text.endswith(".") and not re.search(r"\d\.$", text):
            text = text[:-1].rstrip()
        # stray unbalanced bracket at either end
        if text.endswith(")") and "(" not in text:
            text = text[:-1].rstrip()
        if text.startswith("(") and ")" not in text:
            text = text[1:].lstrip()
        if text == before:
            break
    return text


def clean_term(term: str, field: str) -> str | None:
    """Return the cleaned term, or None when it cannot be salvaged."""
    text = _normalise(term)
    if field == "not_for":
        text = _NOT_FOR_PREFIX.sub("", text).strip()
    if field == "placement" and ". " in text:
        # keep the leading element when prose was glued on ("roofline. - Positive ...")
        text = text.split(". ", 1)[0].strip()

    if len(text) < 3:
        return None
    if field == "priority_fit":
        folded = text.casefold().replace(" ", "_")
        return folded if folded in PRIORITY_FIT_VOCAB else None
    if _LABEL_BLEED.search(text):
        return None
    if ":" in text or ";" in text:
        return None
    if ". " in text:  # internal sentence boundary -> prose, not a term
        return None
    if _ARTIFACT.match(text):
        return None
    words = text.split()
    if len(words[0]) == 1 and words[0].islower():  # orphan token from a mid-word split
        return None
    if words[-1].casefold() in _DANGLING_TAIL:  # truncated fragment
        return None
    if len(words) == 1 and words[0].casefold() in _GENERIC_SOLO:
        return None
    if _INSTRUCTION_LEAD.match(text):
        return None
    folded = text.casefold()
    if field == "placement" and folded in PLACEMENT_VOCAB:
        return folded
    if len(words) > WORD_CAPS[field]:
        return None
    return text


def clean_terms(terms: list, field: str) -> list[str]:
    """Clean a whole retrieval list: salvage, reject, dedupe (case-insensitive)."""
    seen: set[str] = set()
    out: list[str] = []
    for term in terms or []:
        cleaned = clean_term(term, field)
        if cleaned is None:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return sorted(out, key=str.casefold)


def clean_retrieval(retrieval: dict) -> dict:
    """Clean every known list field of a retrieval block; other keys pass through."""
    cleaned = dict(retrieval or {})
    for field in LIST_FIELDS:
        if field in cleaned:
            cleaned[field] = clean_terms(cleaned.get(field) or [], field)
    return cleaned


def ranker_safe_terms(terms: list, max_words: int = 6) -> list[str]:
    """Defensive filter for terms entering the lexical ranker: short, no label
    punctuation. Long-but-clean scenario sentences stay in the JSON for the
    retrieval cards but are kept out of keyword matching."""
    out = []
    for term in terms or []:
        text = re.sub(r"\s+", " ", str(term)).strip()
        if not text or ":" in text or ";" in text or ". " in text:
            continue
        if len(text.split()) > max_words:
            continue
        out.append(text)
    return out
