"""Message classifier for local knowledge, catalogue, and hand-off routes.

Uses the local Ollama model with a rules-based fallback. Returns classification
+ confidence. No hosted or third-party model is involved.
"""
from __future__ import annotations

import re

from aurora_persona import AURORA_CLASSIFIER_PROMPT
import llm_client

# Rules for fallback classification
_SIZE_Q_RE = re.compile(
    r"\b(sizes?|thickness(?:es)?|thick|widths?|lengths?|depth|height|rolls?|sheets?|dimensions?|how\s+big|how\s+much|available|stock|order|buy|carry|sell)\b"
    r"|\bdo\s+you\s+have\b",
    re.IGNORECASE,
)
_COMMERCIAL_Q_RE = re.compile(
    r"\b(price|cost|quote|invoice|bulk|discount|payment|order|purchase|where\s+to\s+buy|supply)\b",
    re.IGNORECASE,
)
_FREIGHT_Q_RE = re.compile(
    r"\b(freight|shipping|delivery|deliver|courier)\b",
    re.IGNORECASE,
)
_TRACKING_Q_RE = re.compile(
    r"\b(track|tracking|shipment\s+status|where(?:'s|\s+is)\s+my\s+order|order\s+status)\b",
    re.IGNORECASE,
)
_SERVICE_REFUSAL_Q_RE = re.compile(
    r"\b(?:can|could|do|does|will|would)\s+you\s+(?:install|fit|remove|vacuum)\b"
    r"|\binstall(?:ation)?\s+(?:service|team|crew|it\s+for\s+me)\b"
    r"|\bcome\s+(?:and\s+|out\s+(?:and\s+)?)?install\b"
    r"|\bremov(?:e|al)\s+(?:of\s+)?(?:the\s+|my\s+|our\s+)?(?:old|existing)\s+insulation\b"
    r"|\bvacuum(?:ing)?\s+(?:out\s+)?(?:the\s+|my\s+|our\s+)?(?:old|existing)?\s*insulation\b"
    r"|\btool\s?hire\b|\bhire\s+(?:a|the)?\s*tools?\b|\bborrow\s+(?:a|the)?\s*tools?\b",
    re.IGNORECASE,
)
_ESCALATE_Q_RE = re.compile(
    r"\b(NCC|fire|BAL|compliance|regulation|certificate|approval|standard|liability|warrant|guarantee|legal|insurance)\b",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(r"^(?:hi|hello|hey|good (?:morning|afternoon|evening)|thanks|thank you|cheers)[!. ]*$", re.I)
_SELECTION_RE = re.compile(
    r"\b(?:which|what)\b.*\b(?:should|best|suits?|suitable|recommend|need)\b"
    r"|\b(?:recommend|help me (?:choose|select)|looking for insulation|need insulation|"
    r"suitable|good for|best for|suit my|right product|can I use|can (?:it|this|that) be used|would .* work|will .* work)\b", re.I,
)
_INFORMATION_RE = re.compile(
    r"^(?:what (?:is|are|does)|how (?:does|do|is)|why|tell me|explain|(?:can|could) you (?:tell|explain|describe|compare)|"
    r"does|is|are|can (?:it|this|that)|what about|and (?:its|the))\b"
    r"|\b(?:used for|made (?:of|from)|difference between|compare)\b", re.I,
)


def asks_selection(message: str) -> bool:
    return bool(_SELECTION_RE.search(message))


def asks_question(message: str) -> bool:
    return bool(_INFORMATION_RE.search(message) or "?" in message)

CLASSIFIER_PROMPT = """Classify the customer's message into ONE of these categories:

1. **informational** — asks about products in general ("what is R-value?", "how does insulation work?", "what's the difference between...")
2. **product-fit** — asks which product suits their situation ("best for a garage?", "good for attic retrofit?", "our house is...")
3. **size-availability** — asks about sizes, stock, ordering ("available in 50mm?", "how much do I need?", "where can I order?")
4. **commercial** — asks about price, quotes, bulk deals, freight ("how much does it cost?", "bulk discount?", "can you quote?")
5. **escalate** — mentions compliance, fire, NCC, guarantees, legal issues ("is it fire-rated?", "NCC compliant?", "liability?")
6. **freight** — asks about shipping, delivery cost or delivery timing
7. **tracking** — asks for the status or location of an existing order
8. **service_refusal** — asks the business to install, remove/vacuum existing insulation, or hire out tools (this business supplies products only)

Message: "{message}"

Respond ONLY with the category name (lowercase, one word, use underscore for service_refusal). No explanation.
"""


class RouterClassification:
    """Result of message classification."""

    def __init__(self, category: str, confidence: float = 0.8):
        self.category = category
        self.confidence = confidence  # 0.0-1.0

    @property
    def is_escalate(self) -> bool:
        return self.category == "escalate"

    @property
    def is_commercial(self) -> bool:
        return self.category == "commercial"

    @property
    def is_informational(self) -> bool:
        return self.category == "informational"


class MessageRouter:
    """Route messages to appropriate handler using LLM + rules fallback."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    def classify(self, message: str, *, answering: bool = False) -> RouterClassification:
        """
        Classify a message. Returns RouterClassification with category + confidence.
        Falls back to rules if LLM fails.
        """
        if not message or not isinstance(message, str):
            return RouterClassification("product-fit", confidence=0.5)

        # A bare 1-2 word reply (e.g. "no", "wall", "residential", a postcode)
        # is almost always a direct answer to the structured intake question
        # just asked, not a free-form request - it carries no context for the
        # LLM classifier to reason about and has been observed to be
        # misclassified (e.g. "no" -> service_refusal), derailing the flow.
        # Rules still apply here so a genuine short trigger (e.g. "NCC?",
        # "price?") is still caught; only the LLM guess is skipped.
        if len(message.split()) <= 2:
            return self._classify_rules(message)

        # Clear requests and safety boundaries do not need a model round-trip.
        rules = self._classify_rules(message)
        if answering or rules.confidence >= 0.6:
            return rules

        # Only an ambiguous message needs optional local interpretation.
        if self.use_llm:
            try:
                result = self._classify_llm(message)
                if result:
                    return result
            except Exception:
                pass  # Fall through to rules

        # Fallback to rules
        return rules

    def _classify_llm(self, message: str) -> RouterClassification | None:
        """Use the local model only for an advisory route label."""
        prompt = CLASSIFIER_PROMPT.format(message=message[:500])
        reply = llm_client.generate_reply(
            AURORA_CLASSIFIER_PROMPT,
            prompt,
            max_tokens=16,
        )
        if not reply:
            return None
        category = reply.strip().casefold()
        valid = {
            "informational", "product-fit", "size-availability",
            "commercial", "escalate", "freight", "tracking", "service_refusal",
        }
        if category in valid:
            return RouterClassification(category, confidence=0.95)
        return None

    def _classify_rules(self, message: str) -> RouterClassification:
        """Fallback rules-based classification."""
        msg_lower = message.lower()

        if _GREETING_RE.fullmatch(message.strip()):
            return RouterClassification("greeting", confidence=1.0)
        # Check escalate first (highest priority)
        if _ESCALATE_Q_RE.search(msg_lower):
            return RouterClassification("escalate", confidence=0.7)

        # A request for a service the business doesn't offer must be caught
        # before commercial/size-availability, so "can you install this?"
        # never falls through to a pricing or product answer.
        if _SERVICE_REFUSAL_Q_RE.search(msg_lower):
            return RouterClassification("service_refusal", confidence=0.8)

        if _TRACKING_Q_RE.search(msg_lower):
            return RouterClassification("tracking", confidence=0.8)

        if _FREIGHT_Q_RE.search(msg_lower):
            return RouterClassification("freight", confidence=0.8)

        # Check commercial (price/ordering)
        if _COMMERCIAL_Q_RE.search(msg_lower):
            return RouterClassification("commercial", confidence=0.7)

        if asks_selection(message):
            return RouterClassification("product-fit", confidence=0.8)

        # Check size/availability
        if _SIZE_Q_RE.search(msg_lower):
            return RouterClassification("size-availability", confidence=0.7)

        if asks_question(message):
            return RouterClassification("informational", confidence=0.8)
        # Check if sounds like product-fit (e.g., describing a scenario)
        if any(kw in msg_lower for kw in ["my", "our", "house", "building", "garage", "attic", "retrofit", "new build", "basement"]):
            return RouterClassification("product-fit", confidence=0.6)

        # Default to product-fit (most common case)
        return RouterClassification("product-fit", confidence=0.5)
