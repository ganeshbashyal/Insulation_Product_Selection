"""Headless conversation engine for the deployable local FastAPI agent.

This module owns the shared plain-Python conversation flow used by the local
service and offline tests:
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
import sku_catalogue
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
    ("name", "Before we go further — what's your name?"),
    ("application", "Where is the problem — wall, floor, roof, pipe or somewhere else?"),
    ("priority", "What matters most: comfort, energy savings, sustainability, easy installation, budget or compliance?"),
    ("conditions", "Any practical constraints, such as limited space, weather exposure, temperature or floor finish?"),
    ("project", "Is this residential, commercial or industrial? New work or a retrofit?"),
    ("locality", "What suburb and postcode is the project in? I'll use it for the climate-zone check."),
    ("requirements", "Do you have a target rating, NCC, fire, BAL or consultant requirement? It's okay if you're unsure."),
]

# Asked only after a recommendation has been given, so the customer sees the
# product match before being asked to hand over personal details.
LEAD_CONSENT_TEXT = (
    "By sharing your contact details, you agree that we'll use them only to "
    "follow up on this enquiry."
)
LEAD_QUESTIONS = [
    ("contact_details", f"What's the best number or email for the team to reach you on? {LEAD_CONSENT_TEXT}"),
    ("callback_time", "And when suits you for a callback — a day and rough time is plenty."),
]

# Customer ways of declining to leave details. Honour them rather than asking again.
_DECLINE_TERMS = ("no thanks", "no thank", "not now", "rather not", "prefer not", "skip", "don't want", "dont want", "no details", "later")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Australian numbers: mobiles (04xx), landlines with area code, and +61 forms.
_PHONE_RE = re.compile(r"(?:\+?61[\s-]?|0)[2-478](?:[\s-]?\d){8}")


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
    # Require at least two distinct priority-signal words before treating the
    # priority question as already answered. A single incidental word (e.g.
    # "cold" in "cold bedroom") merely describes the presenting symptom, not
    # a stated preference, and locking it in as "priority" skipped the
    # explicit priority question entirely - observed to misdirect the whole
    # recommendation when a stronger, more specific signal (e.g. "rain noise
    # on the roof") only showed up in a later answer. A real opening
    # statement like "traffic noise through the front wall" still matches
    # two terms ("noise" + "traffic") and continues to auto-skip correctly.
    priority_hits = sum(term in folded for terms in _PRIORITY_TERMS.values() for term in terms)
    if priority_hits >= 2:
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


# Scenario detection for question personalization: distinct from
# detected_element (which is about *where*), this is about the *kind* of
# project so the priority/project questions stop reading as a generic form.
_SCENARIO_TERMS = {
    "garage": ["garage", "carport", "shed", "outbuilding"],
    "retrofit": ["retrofit", "upgrade", "replace", "existing", "old", "current"],
    "new_build": ["new build", "new house", "building a", "construction", "newly"],
}


def detected_scenario(answers: dict[str, str]) -> str | None:
    text = " ".join(answers.values()).casefold()
    for scenario, terms in _SCENARIO_TERMS.items():
        if any(term in text for term in terms):
            return scenario
    return None


def question_for_step(step: int, answers: dict[str, str]) -> str:
    scenario = detected_scenario(answers)
    # Branch on the question key rather than its position: these follow-ups
    # used to be keyed on hardcoded step indices, which silently attached the
    # wrong question to the wrong slot as soon as the question list changed.
    key = QUESTIONS[step][0]
    if key == "application":
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
        if scenario == "garage":
            return "Is this insulation for the garage wall, roof, ceiling, or somewhere else?"
        if scenario == "retrofit":
            return "Where is this retrofit happening — wall, floor, roof, pipe or somewhere else?"
    if key == "priority" and scenario:
        if scenario == "garage":
            return "What's the main priority for your garage insulation: climate control, noise reduction, or budget?"
        if scenario == "retrofit":
            return "For this retrofit, what matters most: comfort, energy savings, budget, or acoustic performance?"
    if key == "conditions":
        text = " ".join(answers.values()).casefold()
        element = detected_element(answers)
        if element == "roof":
            if any(t in text for t in ["metal roof", "tiled roof", "tile roof"]):
                return "How much space is available, and are condensation or rain noise concerns?"
            return "What type of roof is it, and are condensation or rain noise concerns?"
        if element == "floor":
            return "What access, cavity depth, moisture or floor-finish constraints should we allow for?"
    if key == "project" and scenario:
        if scenario == "garage":
            return "Is your garage project residential, commercial, or industrial?"
        if scenario == "retrofit":
            return "Is this a residential, commercial, or industrial retrofit?"
    return QUESTIONS[step][1]


@dataclass
class Conversation:
    conversation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    step: int = 0
    answers: dict[str, str] = field(default_factory=dict)
    done: bool = False
    recommendation: dict | None = None
    gate: tuple[str, str] | None = None
    lead_step: int = 0
    lead: dict[str, str] = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)

    @property
    def capturing_lead(self) -> bool:
        """True once the recommendation is out but contact details are pending."""
        return not self.done and self.step >= len(QUESTIONS)

    def next_prompt(self) -> str:
        if self.step < len(QUESTIONS):
            return QUESTIONS[self.step][1]
        if self.lead_step < len(LEAD_QUESTIONS):
            return LEAD_QUESTIONS[self.lead_step][1]
        return ""

    def to_dict(self) -> dict:
        """Serialize all state required to resume the conversation."""
        return {
            "conversation_id": self.conversation_id,
            "step": self.step,
            "answers": self.answers,
            "done": self.done,
            "recommendation": self.recommendation,
            "gate": list(self.gate) if self.gate else None,
            "lead_step": self.lead_step,
            "lead": self.lead,
            "candidates": self.candidates,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        """Restore a conversation, including sessions written by older builds."""
        answers = dict(data.get("answers") or {})
        gate = data.get("gate")
        return cls(
            conversation_id=data.get("conversation_id") or uuid.uuid4().hex[:12],
            step=int(data.get("step", min(len(answers), len(QUESTIONS)))),
            answers=answers,
            done=bool(data.get("done", False)),
            recommendation=data.get("recommendation"),
            gate=tuple(gate) if gate else None,
            lead_step=int(data.get("lead_step", 0)),
            lead=dict(data.get("lead") or {}),
            candidates=list(data.get("candidates") or []),
        )


def parse_contact_details(text: str) -> dict[str, str]:
    """Pull an email address and/or phone number out of a free-text answer."""
    email = _EMAIL_RE.search(text)
    # Strip the email before scanning for a phone, so digits inside an address
    # (e.g. jo1975@example.com) cannot be misread as a phone number.
    remainder = _EMAIL_RE.sub(" ", text)
    phone = _PHONE_RE.search(remainder)
    return {
        "email": email.group(0) if email else "",
        "phone": re.sub(r"[\s-]", "", phone.group(0)) if phone else "",
    }


def is_decline(text: str) -> bool:
    folded = text.casefold().strip()
    return folded in {"no", "nope", "n"} or any(term in folded for term in _DECLINE_TERMS)


def clean_name(text: str) -> str:
    """Reduce 'hi, it's John Smith here' to something usable as a name."""
    stripped = re.sub(r"^\s*(?:hi|hey|hello|yeah|yes|sure)\b[,!.\s]*", "", text.strip(), flags=re.I)
    stripped = re.sub(r"^\s*(?:i'?m|my name is|it'?s|this is|names?)\b[\s:]*", "", stripped, flags=re.I)
    stripped = re.sub(r"\b(?:here|speaking)\b[.!]*\s*$", "", stripped, flags=re.I)
    return stripped.strip(" .,!-")[:80]


_STATEMENT_PARTS = (
    ("application", "Affected element: {}."),
    ("priority", "Main priority: {}."),
    ("project", "Project type: {}."),
    ("locality", "Location: {}."),
    ("conditions", "Constraints: {}."),
    ("requirements", "Stated requirements: {}."),
)


def build_problem_statement(answers: dict[str, str]) -> str:
    """Assemble the brief deterministically from what the customer told us.

    Deliberately not LLM-generated: this text is handed to a salesperson and
    may be quoted back to the customer, so it must never contain anything the
    customer did not actually say.
    """
    opening = (answers.get("problem") or "").strip()
    parts = [opening] if opening else []
    for key, template in _STATEMENT_PARTS:
        value = (answers.get(key) or "").strip()
        # extract_from_opening backfills some keys with the whole opening
        # sentence; repeating it here would just pad the brief.
        if value and value != opening:
            parts.append(template.format(value.rstrip(".")))
    return " ".join(parts)



def _phrase(text: str, use_llm: bool, context: dict | None = None, is_opening: bool = False) -> str:
    return llm_client.phrase(text, context=context, is_opening=is_opening) if use_llm else text


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
    answer = f"For {'/'.join(bits)}, current options include {names}{extra}. We'll confirm the exact variant, pack coverage and availability before quoting."

    if sku_catalogue.available():
        # Attach real SKU codes for the top match only, so the reply stays a
        # short options list rather than a dump of every candidate's stock.
        sku_rows = sku_catalogue.skus_matching(
            matches[0]["family_id"],
            width=constraints["width"],
            thickness=constraints["thickness"],
            rvalue=constraints["rvalue"],
            limit=3,
        )
        if sku_rows:
            codes = ", ".join(r["sku"] or r["our_sku"] for r in sku_rows)
            answer += f" Orderable SKU(s) for {matches[0]['name']}: {codes}."
    return answer


def _finalise_lead(conversation: Conversation, site_id: str) -> None:
    interaction_store.save_lead(
        conversation_id=conversation.conversation_id,
        site_id=site_id,
        customer_name=conversation.lead.get("customer_name", ""),
        phone=conversation.lead.get("phone", ""),
        email=conversation.lead.get("email", ""),
        callback_time=conversation.lead.get("callback_time", ""),
        problem_statement=build_problem_statement(conversation.answers),
        recommended_families=(
            [conversation.recommendation] if conversation.recommendation else []
        ),
        consent_text=LEAD_CONSENT_TEXT,
    )
    conversation.answers.pop("name", None)


def _capture_lead(conversation: Conversation, message: str, use_llm: bool, site_id: str) -> str:
    """Handle one answer in the post-recommendation contact-capture phase."""
    key, _ = LEAD_QUESTIONS[conversation.lead_step]
    text = message.strip()

    if key == "contact_details" and is_decline(text):
        conversation.lead["declined"] = "yes"
        conversation.lead.pop("customer_name", None)
        _finalise_lead(conversation, site_id)
        conversation.done = True
        return _phrase("No problem, I won't ask for your details. I've passed the project brief on without your contact information.", use_llm)

    if key == "contact_details":
        found = parse_contact_details(text)
        if not found["email"] and not found["phone"] and not conversation.lead.get("contact_retry"):
            # Ask once more, then accept whatever they wrote rather than
            # trapping the customer in a validation loop.
            conversation.lead["contact_retry"] = "1"
            return _phrase("Sorry, I didn't catch that. Could you write your phone number or email out for me? " + LEAD_CONSENT_TEXT, use_llm=False)
        if not found["email"] and not found["phone"]:
            conversation.lead.pop("customer_name", None)
            _finalise_lead(conversation, site_id)
            conversation.done = True
            return _phrase("I haven't captured a phone number or email, so I can't arrange a follow-up. I've passed the project brief on without your contact information.", use_llm)
        conversation.lead.update({field_name: value for field_name, value in found.items() if value})
    else:
        conversation.lead[key] = text

    conversation.lead_step += 1
    if conversation.lead_step < len(LEAD_QUESTIONS):
        return _phrase(LEAD_QUESTIONS[conversation.lead_step][1], use_llm)

    _finalise_lead(conversation, site_id)
    conversation.done = True
    name = conversation.lead.get("customer_name", "")
    closing = f"Thanks {name}, I've passed your details and a summary of your project to the team. They'll be in touch." if name else "Thanks, I've passed your details and a summary of your project to the team. They'll be in touch."
    return _phrase(closing, use_llm)


def reply(conversation: Conversation, message: str, use_llm: bool = False, manufacturer_scope: str | None = None, site_id: str = "default") -> str:
    """Advance the conversation by one customer message and return the agent reply."""
    if conversation.done:
        # after completion, still answer direct size/availability follow-ups
        size_answer = answer_size_query(message)
        if size_answer:
            return _phrase(size_answer, use_llm)
        return "This enquiry is already with the team for review. Start a new conversation for another project."

    if conversation.capturing_lead:
        return _capture_lead(conversation, message, use_llm, site_id)

    key, _ = QUESTIONS[conversation.step]
    conversation.answers[key] = message.strip()
    if key == "name":
        conversation.lead["customer_name"] = clean_name(message)
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

    # questions complete -> rank and respond, then ask for contact details
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

    conversation.candidates = [
        {
            "family_id": r["family_id"],
            "name": r["name"],
            "manufacturer": r.get("manufacturer", ""),
            "match_score": r.get("match_score"),
            "matched": r.get("matched", []),
            "reliable_match": r.get("reliable_match"),
            "confidence": r.get("confidence", ""),
        }
        for r in ranked[:5]
    ]

    interaction_store.log_conversation(
        conversation_id=conversation.conversation_id,
        site_id=site_id,
        answers=conversation.answers,
        recommendation=conversation.recommendation,
        gate_status=gate[0],
        gate_reason=gate[1],
        climate_zone=zone,
        candidates=conversation.candidates,
    )
    # The recommendation and the first contact question go out together, so the
    # customer sees the product match before being asked for personal details.
    return _phrase(reply_text, use_llm, context=conversation.recommendation) + "\n\n" + LEAD_QUESTIONS[0][1]
