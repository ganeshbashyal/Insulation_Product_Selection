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
from dataclasses import dataclass, field, fields
from pathlib import Path

import llm_client
import interaction_store
import enquiry_discovery as discovery
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
OPENING = (
    "I can answer a product question or prepare an enquiry for sales review. "
    "Tell me what you want to improve in your own words. I'll ask for the relevant project details "
    "so the team doesn't need to repeat basic questions; product selection stays with them."
)

QUESTIONS = [
    ("problem", "Tell me about your project or problem in your own words — e.g. 'my upstairs bedroom is freezing in winter and the walls are thin', or 'traffic noise through the front wall of my townhouse'. Mention where it is, what you're feeling, and anything about the building if you know it."),
    ("name", "What name would you like me to use? You can say skip."),
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
    ("callback_time", "When would a callback suit you? A day and rough time is plenty; you can skip this."),
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


def extract_turn_details(text: str) -> dict[str, str]:
    """Retain explicitly supplied details, including later multi-detail turns."""
    # A correction's negated old value must not become the new application.
    affirmative = re.split(r",?\s+(?:not|rather than|instead of)\s+(?:the\s+)?", text, maxsplit=1, flags=re.I)[0]
    found = extract_from_opening(affirmative)
    clauses = re.split(r"[,;]|\band\b", affirmative, flags=re.I)
    if "application" in found:
        relevant = [clause.strip() for clause in clauses if any(
            re.search(rf"\b{re.escape(term)}s?\b", clause, re.I)
            for terms in _APPLICATION_TERMS.values() for term in terms
        )]
        if relevant:
            found["application"] = ", ".join(relevant)
    signals = {
        "priority": r"\b(?:priority|comfort|energy savings|thermal|cold|hot|freezing|noise|sound|budget|sustainability)\b",
        "conditions": r"\b(?:space|airspace|cavity|access|lining|plasterboard|brick|exposed|exposure|weather|moisture|condensation|timber frame|steel frame|concrete|metal roof|\d+\s*mm|\d+\s*degrees)\b",
        "project": r"\b(?:residential|commercial|industrial|retrofit|renovation|new build|new home)\b",
        "locality": r"\b\d{4}\b",
        "requirements": r"\b(?:requirements?|NCC|fire|BAL|consultant|specifications?|targets?|ratings?)\b",
    }
    for key, pattern in signals.items():
        relevant = [clause.strip() for clause in clauses if re.search(pattern, clause, re.I)]
        if relevant:
            found[key] = ", ".join(relevant)
    places = [clause.strip() for clause in clauses if any(re.search(rf"\b{re.escape(place)}\b", clause, re.I) for place in _LOCALITY_ZONE_HINTS)]
    if places:
        found["locality"] = ", ".join(places)
    if re.search(r"\b(?:actually|I meant|correction)\b", affirmative, re.I):
        if any(re.search(rf"\b{re.escape(term)}\b", affirmative, re.I) for terms in _PRIORITY_TERMS.values() for term in terms):
            found.setdefault("priority", affirmative.strip())
    name = re.search(r"\b(?:my name is|I'm called|I am called)\s+([a-z][a-z '\-]{0,70})", text, re.I)
    if name:
        found["name"] = clean_name(name.group(1))
    return found

_LOCALITY_ZONE_HINTS = {
    "darwin": 1, "cairns": 1, "brisbane": 2, "gold coast": 2, "alice springs": 3,
    "perth": 5, "adelaide": 5, "sydney": 5, "newcastle": 5, "wollongong": 5,
    "melbourne": 6, "canberra": 7, "hobart": 7, "thredbo": 8,
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()[:60]


def load_families() -> list[dict]:
    from knowledge_release import configured_release
    release = configured_release()
    if release is not None:
        return release["payload"]["families"]
    from family_knowledge import load_families as read_families, load_research
    research = load_research(ROOT)
    families = []
    for key, family in read_families(ROOT).items():
        family.pop("record_path", None)
        family["documented_applications"] = list(family.get("applications", []))
        family["documented_keywords"] = list(family.get("keywords", []))
        retrieval = research.get(key, {}).get("retrieval") or {}
        if retrieval:
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
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms):
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
            element = detected_element(answers)
            subject = f"{element} retrofit" if element else "retrofit"
            return f"For this {subject}, what's the main priority: comfort, energy savings, budget or acoustic performance?"
    if key == "priority":
        element = detected_element(answers)
        if element:
            return f"For your {element}, what's the main priority: comfort, energy savings, noise reduction or budget?"
    if key == "conditions":
        text = " ".join(answers.values()).casefold()
        element = detected_element(answers)
        if element == "roof":
            if any(t in text for t in ["metal roof", "tiled roof", "tile roof"]):
                return "How much space is available, and are condensation or rain noise concerns?"
            return "What type of roof is it, and are condensation or rain noise concerns?"
        if element == "floor":
            return "What access, cavity depth, moisture or floor-finish constraints should we allow for?"
        if element == "wall":
            return "What is the wall construction, and are there space, access or moisture constraints?"
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
    topic_products: list[str] = field(default_factory=list)
    product_options: list[str] = field(default_factory=list)
    topic: str = ""
    mode: str = "enquiry"
    review_required: bool = False
    capture_version: int = 3
    manufacturer_scope: str | None = None
    discovery_status: dict[str, str] = field(default_factory=dict)
    pending_field: str | None = None
    discovery_ended_early: bool = False

    @property
    def capturing_lead(self) -> bool:
        """True once a brief is captured but voluntary contact is pending."""
        return not self.done and self.step >= len(QUESTIONS)

    def next_prompt(self) -> str:
        if self.done:
            return ""
        if self.mode == "discovery":
            return discovery.question(self.pending_field, self.answers) if self.pending_field else OPENING
        if self.mode == "capture":
            if self.step < len(QUESTIONS):
                return "What would you like to improve, and where is the problem?"
            return LEAD_QUESTIONS[self.lead_step][1]
        if self.step < len(QUESTIONS):
            return OPENING if self.step == 0 else question_for_step(self.step, self.answers)
        if self.lead_step < len(LEAD_QUESTIONS):
            return LEAD_QUESTIONS[self.lead_step][1]
        return ""

    def start_new_project(self) -> None:
        """A new brief gets a new audit identity, never overwrites an old lead."""
        fresh = Conversation()
        for item in fields(self):
            setattr(self, item.name, getattr(fresh, item.name))

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
            "topic_products": self.topic_products,
            "product_options": self.product_options,
            "topic": self.topic,
            "mode": self.mode,
            "review_required": self.review_required,
            "capture_version": self.capture_version,
            "manufacturer_scope": self.manufacturer_scope,
            "discovery_status": self.discovery_status,
            "pending_field": self.pending_field,
            "discovery_ended_early": self.discovery_ended_early,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        """Restore a conversation, including sessions written by older builds."""
        answers = dict(data.get("answers") or {})
        gate = data.get("gate")
        restored = cls(
            conversation_id=data.get("conversation_id") or uuid.uuid4().hex[:12],
            step=int(data.get("step", min(len(answers), len(QUESTIONS)))),
            answers=answers,
            done=bool(data.get("done", False)),
            recommendation=data.get("recommendation"),
            gate=tuple(gate) if gate else None,
            lead_step=int(data.get("lead_step", 0)),
            lead=dict(data.get("lead") or {}),
            candidates=list(data.get("candidates") or []),
            topic_products=list(data.get("topic_products") or [])[:2],
            product_options=list(data.get("product_options") or [])[:12],
            topic=str(data.get("topic") or "")[:160],
            mode=data.get("mode") or ("selection" if answers else "enquiry"),
            review_required=bool(data.get("review_required", False)),
            capture_version=int(data.get("capture_version", 1)),
            manufacturer_scope=data.get("manufacturer_scope"),
            discovery_status=dict(data.get("discovery_status") or {}),
            pending_field=data.get("pending_field"),
            discovery_ended_early=bool(data.get("discovery_ended_early", False)),
        )
        if restored.capture_version < 3:
            restored.recommendation = None
            restored.candidates = []
            restored.topic_products = [] if data.get("recommendation") else restored.topic_products
            if answers.get("problem") and not restored.done:
                restored.answers.update(discovery.observed(answers.get("conditions", "") or answers["problem"]))
                if restored.step >= len(QUESTIONS):
                    restored.mode = "capture"
                    restored.discovery_ended_early = True
                else:
                    restored.mode = "discovery"
                    restored.pending_field = discovery.next_field(restored.answers, restored.discovery_status)
                    restored.step = 1
            restored.capture_version = 3
        return restored


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
    ("placement", "Placement: {}."),
    ("construction", "Construction: {}."),
    ("wall_assembly", "Wall assembly: {}."),
    ("access", "Installation access: {}."),
    ("cavity_depth", "Usable depth: {}."),
    ("area", "Area/dimensions: {}."),
    ("existing_insulation", "Existing insulation: {}."),
    ("moisture", "Moisture/exposure: {}."),
    ("airspace", "Airspace: {}."),
    ("service", "Service: {}."),
    ("service_temperature", "Operating temperature: {}."),
    ("timeframe", "Project timing: {}."),
    ("project_stage", "Project stage: {}."),
    ("building_use", "Building use: {}."),
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
    if not use_llm:
        return text
    phrased = llm_client.phrase(text, context=context, is_opening=is_opening)
    if "saved locally" in text.casefold() and "local" not in phrased.casefold():
        return text
    if "skip" in text.casefold() and "skip" not in phrased.casefold():
        return text
    if context and context.get("pending_question") == "name":
        if re.search(r"\b(?:product|family|brand|model)\b", phrased, re.I):
            return text
        if not re.search(r"\b(?:name|call you|address you)\b", phrased, re.I):
            return text
    if context and context.get("family_id") and context.get("name", "").casefold() not in phrased.casefold():
        return text
    # Check plain as well as bold names; phrasing cannot introduce a product.
    if any(family["name"].casefold() in phrased.casefold() and family["name"].casefold() not in text.casefold() for family in FAMILIES):
        return text
    return phrased


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
    from sales_brief import SalesBriefBuilder

    brief = SalesBriefBuilder(FAMILIES).build(
        conversation.answers, scope=conversation.manufacturer_scope,
        discovery_status=conversation.discovery_status,
        site_id=site_id,
    )
    brief["discovery_ended_early"] = conversation.discovery_ended_early
    conversation.candidates = brief["candidates"]
    conversation.recommendation = None
    conversation.gate = ("REVIEW REQUIRED", "Internal candidates require source and installation review.")
    interaction_store.save_lead(
        conversation_id=conversation.conversation_id,
        site_id=site_id,
        customer_name=conversation.lead.get("customer_name", ""),
        phone=conversation.lead.get("phone", ""),
        email=conversation.lead.get("email", ""),
        callback_time=conversation.lead.get("callback_time", ""),
        problem_statement=build_problem_statement(conversation.answers),
        recommended_families=[],
        consent_text=LEAD_CONSENT_TEXT,
        sales_brief=brief,
    )
    interaction_store.log_conversation(
        conversation_id=conversation.conversation_id, site_id=site_id,
        answers=conversation.answers, recommendation=None,
        gate_status=conversation.gate[0], gate_reason=conversation.gate[1],
        climate_zone=None, candidates=conversation.candidates,
    )
    conversation.answers.pop("name", None)


def _capture_lead(conversation: Conversation, message: str, use_llm: bool, site_id: str) -> str:
    """Handle voluntary contact after discovery; no callback is booked."""
    key, _ = LEAD_QUESTIONS[conversation.lead_step]
    text = message.strip()

    if key == "contact_details" and is_decline(text):
        conversation.lead["declined"] = "yes"
        conversation.lead.pop("customer_name", None)
        _finalise_lead(conversation, site_id)
        conversation.done = True
        return _phrase("No problem, I won't ask for your details. The project brief is saved locally without your contact information.", use_llm)

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
            return _phrase("I haven't captured a phone number or email, so I can't arrange a follow-up. The project brief is saved locally without your contact information.", use_llm)
        conversation.lead.update({field_name: value for field_name, value in found.items() if value})
    else:
        conversation.lead[key] = text

    conversation.lead_step += 1
    if conversation.lead_step < len(LEAD_QUESTIONS):
        return _phrase(LEAD_QUESTIONS[conversation.lead_step][1], use_llm)

    _finalise_lead(conversation, site_id)
    conversation.done = True
    name = conversation.lead.get("customer_name", "")
    closing = f"Thanks {name}, your details and project summary are saved locally for sales review." if name else "Thanks, your details and project summary are saved locally for sales review."
    return closing + " A callback is not booked automatically."


def _discovery_prompt(conversation: Conversation) -> str:
    key = None if conversation.discovery_ended_early else discovery.next_field(conversation.answers, conversation.discovery_status)
    conversation.pending_field = key
    if key:
        conversation.mode = "discovery"
        conversation.step = 1
        return discovery.question(key, conversation.answers)
    conversation.mode = "capture"
    conversation.step = len(QUESTIONS)
    return "The project details will be reviewed by sales before any product is selected. " + LEAD_QUESTIONS[conversation.lead_step][1]


def _retain_details(conversation: Conversation, details: dict[str, str], *, correction: bool = False) -> None:
    for key, value in details.items():
        previous = conversation.answers.get(key, "")
        if conversation.discovery_status.get(key) in {"unknown", "skipped"} and not discovery.UNKNOWN.search(value):
            previous = ""
        conversation.answers[key] = value if correction or not previous else previous if value in previous else previous + "; " + value
        conversation.discovery_status[key] = "unknown" if discovery.UNKNOWN.search(value) else "provided"


def reply(conversation: Conversation, message: str, use_llm: bool = False, manufacturer_scope: str | None = None, site_id: str = "default") -> str:
    """Adaptive discovery followed by voluntary contact; selection is private."""
    if re.search(r"\b(?:new project|different project|start (?:again|over))\b", message, re.I):
        conversation.start_new_project()

    conversation.recommendation = None
    if manufacturer_scope:
        conversation.manufacturer_scope = manufacturer_scope
    affirmative = re.split(r",?\s+(?:not|rather than|instead of)\s+(?:the\s+)?", message, maxsplit=1, flags=re.I)[0]
    details = {**extract_turn_details(message), **discovery.observed(affirmative)}
    if conversation.step == 0 and set(details) == {"name"}:
        conversation.answers["name"] = details["name"]
        conversation.lead["customer_name"] = details["name"]
        return OPENING
    correction = bool(re.search(r"\b(?:actually|correction|I meant|rather than|instead of)\b", message, re.I))
    if correction and details:
        if conversation.done:
            # Keep a completed lead immutable; the corrected brief is a new enquiry.
            previous = dict(conversation.answers)
            conversation.start_new_project()
            conversation.answers = previous
        old_element = detected_element(conversation.answers)
        new_element = detected_element(details)
        if new_element and old_element != new_element:
            for key in ("application", "conditions", "placement", "construction", "wall_assembly", "access", "cavity_depth", "area", "existing_insulation", "moisture", "airspace", "service", "service_temperature"):
                conversation.answers.pop(key, None)
                conversation.discovery_status.pop(key, None)
        _retain_details(conversation, details, correction=True)
        conversation.answers["problem"] = message.strip()
        conversation.candidates = []
        conversation.review_required = True
        return "I've updated the project description for sales review. " + _discovery_prompt(conversation)

    if conversation.done:
        return "This project brief is saved locally for review. You can ask a product question, or say 'new project' to start another enquiry."

    if conversation.capturing_lead:
        if "name" in details:
            conversation.lead["customer_name"] = details["name"]
        if details and not any(parse_contact_details(message).values()) and not is_decline(message):
            _retain_details(conversation, details)
            return _discovery_prompt(conversation)
        return _capture_lead(conversation, message, False, site_id)

    conversation.review_required = True
    if discovery.EARLY_HANDOFF.search(message):
        conversation.discovery_ended_early = True
        conversation.answers.setdefault("problem", message.strip())
        return _discovery_prompt(conversation)
    pending = conversation.pending_field
    if pending:
        if any(parse_contact_details(message).values()):
            return "I'll ask for contact details with consent after the project questions. " + conversation.next_prompt()
        if pending == "cavity_depth" and re.fullmatch(r"\s*(?:about\s+)?\d+(?:\.\d+)?\s*(?:mm|cm|metres?|m)\s*[.!]?\s*", message, re.I):
            details[pending] = message.strip()
        if pending == "placement" and "application" in details:
            details[pending] = details["application"]
        if discovery.SKIP.fullmatch(message):
            conversation.discovery_status[pending] = "skipped"
        elif pending in details or not details:
            conversation.answers[pending] = message.strip()
            conversation.discovery_status[pending] = "unknown" if discovery.UNKNOWN.search(message) else "provided"
    _retain_details(conversation, details)
    if "name" in details:
        conversation.lead["customer_name"] = details["name"]
    conversation.answers.setdefault("problem", message.strip())
    return _discovery_prompt(conversation)
