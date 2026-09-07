"""Headless conversation engine for the deployable website agent.

This module extracts the demo's conversation flow from the Streamlit UI into a
plain-Python class so the same logic can run anywhere (web server, background
job, future channels) without Streamlit. It owns nothing except the flow:
  - product ranking and gating come from bot_engine (unchanged, deterministic)
  - optional natural phrasing comes from llm_client (unchanged, safe fallback)
  - conversation logging + reviewer feedback come from interaction_store

Interaction learning model: the agent logs every completed conversation and
the top recommendation. A reviewer then records an outcome (approved /
edited / rejected) per conversation. The store aggregates these outcomes per
family and per query pattern so the team can see where the deterministic
ranker is misfiring and tune it. Learning never changes live behaviour
automatically; it produces evidence for human tuning of bot_engine and the
family data.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import llm_client
import interaction_store
import size_index
from retrieval_hygiene import ranker_safe_terms
from bot_engine import (
    PRIORITY_LABELS,
    rank_families,
    recommendation_allowed,
    technical_gate,
)

ROOT = Path(__file__).resolve().parent

QUESTIONS = [
    ("problem", "Tell me about your project or problem in your own words — e.g. 'my upstairs bedroom is freezing in winter and the walls are thin', or 'traffic noise through the front wall of my townhouse'. Mention where it is, what you're feeling, and anything about the building if you know it."),
    ("application", "Where is the problem — wall, floor, roof, pipe or somewhere else?"),
    ("priority", "What matters most: comfort, energy savings, sustainability, easy installation, budget or compliance?"),
    ("conditions", "Any practical constraints, such as limited space, weather exposure, temperature or floor finish?"),
    ("project", "Is this residential, commercial or industrial? New work or a retrofit?"),
    ("locality", "What suburb and postcode is the project in? I'll use it for the climate-zone check."),
    ("requirements", "Do you have a target rating, NCC, fire, BAL or consultant requirement? It's okay if you're unsure."),
    ("contact", "Would you prefer to call us, receive a callback or have the brief emailed to the team?"),
]

# signals used to decide whether the opening statement already answered a step
_APPLICATION_TERMS = {
    "roof": ["roof", "ceiling", "rafter", "truss", "attic"],
    "floor": ["floor", "subfloor", "underfloor", "storey", "storeys"],
    "wall": ["wall", "partition", "cladding"],
    "pipe": ["pipe", "plumbing", "waste", "duct", "hvac"],
}
_PRIORITY_TERMS = {
    "noise": ["noise", "noisy", "sound", "acoustic", "quiet", "neighbour", "traffic", "footstep", "voices"],
    "heat": ["heat", "hot", "cold", "freezing", "thermal", "energy", "summer", "winter", "temperature"],
    "condensation": ["condensation", "moisture", "mould", "damp"],
    "budget": ["budget", "cheap", "affordable", "cost"],
}
_PROJECT_TERMS = ["residential", "commercial", "industrial", "apartment", "townhouse", "house", "shed", "office", "renovation", "retrofit", "new build", "new home"]


def extract_from_opening(text: str) -> dict[str, str]:
    """Pull whatever the free-text opening statement already tells us."""
    folded = " " + text.casefold() + " "
    found: dict[str, str] = {}
    if any(term in folded for terms in _APPLICATION_TERMS.values() for term in terms):
        found["application"] = text
    if any(term in folded for terms in _PRIORITY_TERMS.values() for term in terms):
        found["priority"] = text
    if any(term in folded for term in _PROJECT_TERMS):
        found["project"] = text
    if re.search(r"\b\d{4}\b", text):
        found["locality"] = text
    return found

_LOCALITY_ZONE_HINTS = {
    "darwin": 1, "cairns": 1, "brisbane": 2, "gold coast": 2, "alice springs": 3,
    "perth": 5, "adelaide": 5, "sydney": 5, "newcastle": 5, "wollongong": 5,
    "melbourne": 6, "canberra": 7, "hobart": 7, "thredbo": 8,
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()[:60]


def load_families() -> list[dict]:
    families = []
    for path in sorted((ROOT / "knowledge").glob("*/families.json")):
        mdir = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            family.setdefault("manufacturer", mdir.title())
            # merge retrieval/decision signals from the research agent, if present
            research_file = path.parent / "research" / f"{_slug(family['name'])}.json"
            if research_file.exists():
                try:
                    research = json.loads(research_file.read_text(encoding="utf-8"))
                    retrieval = research.get("retrieval") or {}
                except (json.JSONDecodeError, OSError):
                    retrieval = {}
                if retrieval:
                    # ranker_safe_terms keeps long scenario sentences (valuable for
                    # retrieval cards/embeddings) out of lexical keyword matching
                    family["keywords"] = sorted(set(family.get("keywords", [])) | set(ranker_safe_terms(retrieval.get("search_keywords"))) | set(ranker_safe_terms(retrieval.get("problem_keywords"))))
                    family["applications"] = sorted(set(family.get("applications", [])) | set(ranker_safe_terms(retrieval.get("placement"))) | set(ranker_safe_terms(retrieval.get("use_cases"))))
                    family["not_for"] = ranker_safe_terms(retrieval.get("not_for"))
                    family["priority_fit"] = retrieval.get("priority_fit") or []
                    family["rag_summary"] = retrieval.get("rag_summary") or ""
            families.append(family)
    return families


FAMILIES = load_families()


def detected_element(answers: dict[str, str]) -> str | None:
    text = " ".join(answers.values()).casefold()
    for element, terms in {
        "roof": ["roof", "ceiling", "rafter", "truss"],
        "floor": ["floor", "subfloor", "underfloor", "storey", "storeys"],
        "wall": ["wall", "partition"],
        "pipe": ["pipe", "plumbing", "waste", "solar hot water"],
        "duct": ["duct", "hvac"],
    }.items():
        if any(term in text for term in terms):
            return element
    return None


def question_for_step(step: int, answers: dict[str, str]) -> str:
    if step == 1:
        text = " ".join(answers.values()).casefold()
        element = detected_element(answers)
        if element == "roof":
            if any(t in text for t in ["ceiling level", "ceiling space", "roofline", "rafter", "truss"]):
                return "What type of roof is it — metal, tile or something else?"
            return "Should the insulation sit at ceiling level or up near the roofline, rafters or trusses?"
        if element == "floor":
            if any(t in text for t in ["subfloor", "underfloor", "suspended floor", "between floors", "between storeys", "floor finish", "underlay"]):
                return "What is the floor construction — timber, concrete or something else?"
            return "Is it under a suspended ground floor, inside the cavity between storeys, or directly beneath the floor finish?"
        if element == "wall":
            return "Is it an internal or external wall, and what is the frame made from?"
        if element in {"pipe", "duct"}:
            return "What service is it, and is it indoors or exposed to weather?"
    if step == 3:
        text = " ".join(answers.values()).casefold()
        element = detected_element(answers)
        if element == "roof":
            if any(t in text for t in ["metal roof", "tiled roof", "tile roof"]):
                return "How much space is available, and are condensation or rain noise concerns?"
            return "What type of roof is it, and are condensation or rain noise concerns?"
        if element == "floor":
            return "What access, cavity depth, moisture or floor-finish constraints should we allow for?"
    return QUESTIONS[step][1]


@dataclass
class Conversation:
    conversation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    step: int = 0
    answers: dict[str, str] = field(default_factory=dict)
    done: bool = False
    recommendation: dict | None = None
    gate: tuple[str, str] | None = None

    def next_prompt(self) -> str:
        return QUESTIONS[self.step][1] if self.step < len(QUESTIONS) else ""


def _phrase(text: str, use_llm: bool, context: dict | None = None) -> str:
    return llm_client.phrase(text, context=context) if use_llm else text


_SIZE_Q_RE = re.compile(
    r"\b(?:r\s?\d+(?:\.\d+)?|\d{2,3}\s?mm|\d{3,4}\s?mm|width|thickness|cavity|size|dimension|pack cover|square metre|sqm)\b",
    re.I,
)
_QUESTION_MARK = "?"


def detect_size_query(text: str) -> dict:
    """Pull width / thickness / R-value constraints out of a customer message."""
    folded = text.casefold()
    width = thickness = rvalue = None
    w = re.search(r"\b(\d{3,4})\s?mm\b(?=[^.]{0,40}(?:width|cavity|stud|fram))", folded) or \
        re.search(r"(?:width|cavity|stud|fram)[^.]{0,40}?\b(\d{3,4})\s?mm\b", folded) or \
        re.search(r"\b(430|450|580|600|415|565)\s?mm\b", folded)
    if w:
        width = float(w.group(1))
    t = re.search(r"\b(\d{2,3})\s?mm\b(?=[^.]{0,40}thick)", folded) or \
        re.search(r"thick(?:ness)?[^.]{0,40}?\b(\d{2,3})\s?mm\b", folded)
    if t:
        thickness = float(t.group(1))
    r = re.search(r"\br\s?(\d+(?:\.\d+)?)\b", folded)
    if r:
        rvalue = float(r.group(1))
    return {"width": width, "thickness": thickness, "rvalue": rvalue}


def answer_size_query(text: str) -> str | None:
    """If the message is a size/R-value availability question, answer it directly
    from the size index. Returns None when it isn't such a question."""
    if _QUESTION_MARK not in text and not _SIZE_Q_RE.search(text):
        return None
    constraints = detect_size_query(text)
    if not any(constraints.values()):
        return None
    matches = size_index.query(
        width=constraints["width"],
        thickness=constraints["thickness"],
        rvalue=constraints["rvalue"],
    )
    if not matches:
        bits = [f"{k} {v:g}" for k, v in constraints.items() if v is not None]
        return f"I don't have a family with {' and '.join(bits)} in the current catalogue. I'll flag it for the team to confirm a special order."
    names = ", ".join(f"**{m['name']}** ({m['manufacturer']})" for m in matches[:4])
    bits = []
    if constraints["rvalue"]:
        bits.append(f"R{constraints['rvalue']:g}")
    if constraints["width"]:
        bits.append(f"{constraints['width']:g} mm wide")
    if constraints["thickness"]:
        bits.append(f"{constraints['thickness']:g} mm thick")
    extra = f" and {len(matches) - 4} more" if len(matches) > 4 else ""
    return f"For {'/'.join(bits)}, current options include {names}{extra}. We'll confirm the exact variant, pack coverage and availability before quoting."


def reply(conversation: Conversation, message: str, use_llm: bool = False, manufacturer_scope: str | None = None) -> str:
    """Advance the conversation by one customer message and return the agent reply."""
    if conversation.done:
        # after completion, still answer direct size/availability follow-ups
        size_answer = answer_size_query(message)
        if size_answer:
            return _phrase(size_answer, use_llm)
        return "This enquiry is already with the team for review. Start a new conversation for another project."

    key, _ = QUESTIONS[conversation.step]
    conversation.answers[key] = message.strip()
    conversation.step += 1

    # if this was the opening problem statement, harvest whatever it already
    # answered so we only ask follow-ups for what's genuinely missing
    if key == "problem":
        for filled_key, value in extract_from_opening(message).items():
            conversation.answers.setdefault(filled_key, value)

    # locality can be auto-filled if a postcode appeared earlier
    if conversation.step < len(QUESTIONS) and QUESTIONS[conversation.step][0] == "locality":
        existing = next((v for v in conversation.answers.values() if re.search(r"\b\d{4}\b", v)), None)
        if existing:
            conversation.answers["locality"] = existing
            conversation.step += 1

    # skip any step the opening statement already answered
    while conversation.step < len(QUESTIONS) and QUESTIONS[conversation.step][0] in conversation.answers:
        conversation.step += 1

    if conversation.step < len(QUESTIONS):
        return _phrase(question_for_step(conversation.step, conversation.answers), use_llm)

    # conversation complete -> rank and respond
    conversation.done = True
    ranked = rank_families(FAMILIES, conversation.answers, manufacturer_scope or "Compare both")
    top = ranked[0] if ranked else None
    gate = technical_gate(conversation.answers, top)
    conversation.gate = gate

    if top is None or not top.get("reliable_match", False):
        reply_text = "I don't have a reliable product match from those details. I'll send this to the team for review rather than guess."
    elif recommendation_allowed(top):
        application = next(iter(dict.fromkeys(top.get("matched_applications", []))), "")
        priority = PRIORITY_LABELS[top["priority_key"]].lower()
        why = f"It suits {application} applications and your focus on {priority}." if application else f"It lines up with your focus on {priority}."
        reply_text = f"**{top['name']}** looks like the best fit. {why} We'll confirm the exact product and compliance details before quoting."
        conversation.recommendation = {"family_id": top["family_id"], "name": top["name"], "manufacturer": top["manufacturer"]}
    else:
        reply_text = f"**{top['name']}** is the closest match, but its product evidence still needs checking. I'll flag it for the team before anything is selected or quoted."
        conversation.recommendation = {"family_id": top["family_id"], "name": top["name"], "manufacturer": top["manufacturer"], "evidence_pending": True}

    locality = conversation.answers.get("locality", "")
    zone = next((z for place, z in _LOCALITY_ZONE_HINTS.items() if place in locality.casefold()), None)

    interaction_store.log_conversation(
        conversation_id=conversation.conversation_id,
        answers=conversation.answers,
        recommendation=conversation.recommendation,
        gate_status=gate[0],
        gate_reason=gate[1],
        climate_zone=zone,
        candidates=[{"family_id": r["family_id"], "name": r["name"]} for r in ranked[:3]],
    )
    return _phrase(reply_text, use_llm, context=conversation.recommendation)
