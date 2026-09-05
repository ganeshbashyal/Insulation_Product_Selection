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
from bot_engine import (
    PRIORITY_LABELS,
    rank_families,
    recommendation_allowed,
    technical_gate,
)

ROOT = Path(__file__).resolve().parent

QUESTIONS = [
    ("challenge", "What would you like to improve — noise, heat, condensation or general comfort?"),
    ("application", "Where is the problem — wall, floor, roof, pipe or somewhere else?"),
    ("priority", "What matters most: comfort, energy savings, sustainability, easy installation, budget or compliance?"),
    ("conditions", "Any practical constraints, such as limited space, weather exposure, temperature or floor finish?"),
    ("project", "Is this residential, commercial or industrial? New work or a retrofit?"),
    ("locality", "What suburb and postcode is the project in? I'll use it for the climate-zone check."),
    ("requirements", "Do you have a target rating, NCC, fire, BAL or consultant requirement? It's okay if you're unsure."),
    ("contact", "Would you prefer to call us, receive a callback or have the brief emailed to the team?"),
]

_LOCALITY_ZONE_HINTS = {
    "darwin": 1, "cairns": 1, "brisbane": 2, "gold coast": 2, "alice springs": 3,
    "perth": 5, "adelaide": 5, "sydney": 5, "newcastle": 5, "wollongong": 5,
    "melbourne": 6, "canberra": 7, "hobart": 7, "thredbo": 8,
}


def load_families() -> list[dict]:
    families = []
    for path in sorted((ROOT / "knowledge").glob("*/families.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            family.setdefault("manufacturer", path.parent.name.title())
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


def reply(conversation: Conversation, message: str, use_llm: bool = False, manufacturer_scope: str | None = None) -> str:
    """Advance the conversation by one customer message and return the agent reply."""
    if conversation.done:
        return "This enquiry is already with the team for review. Start a new conversation for another project."

    key, _ = QUESTIONS[conversation.step]
    conversation.answers[key] = message.strip()
    conversation.step += 1

    # locality can be auto-filled if a postcode appeared earlier
    if conversation.step < len(QUESTIONS) and QUESTIONS[conversation.step][0] == "locality":
        existing = next((v for v in conversation.answers.values() if re.search(r"\b\d{4}\b", v)), None)
        if existing:
            conversation.answers["locality"] = existing
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
