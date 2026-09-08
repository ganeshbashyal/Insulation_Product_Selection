"""Message classifier: route to informational, product-fit, size-availability, commercial, or escalate.

Uses the local Ollama model with a rules-based fallback. Returns classification
+ confidence. No hosted or third-party model is involved.
"""
from __future__ import annotations

import re

import llm_client

# Rules for fallback classification
_SIZE_Q_RE = re.compile(
    r"\b(size|thickness|width|depth|height|roll|sheet|dimension|how\s+big|how\s+much|available|stock|order|buy)\b",
    re.IGNORECASE,
)
_COMMERCIAL_Q_RE = re.compile(
    r"\b(price|cost|quote|invoice|freight|shipping|delivery|bulk|discount|payment|order|purchase|where\s+to\s+buy|supply)\b",
    re.IGNORECASE,
)
_ESCALATE_Q_RE = re.compile(
    r"\b(NCC|fire|BAL|compliance|regulation|certificate|approval|standard|liability|warrant|guarantee|legal|insurance)\b",
    re.IGNORECASE,
)

CLASSIFIER_PROMPT = """Classify the customer's message into ONE of these categories:

1. **informational** — asks about products in general ("what is R-value?", "how does insulation work?", "what's the difference between...")
2. **product-fit** — asks which product suits their situation ("best for a garage?", "good for attic retrofit?", "our house is...")
3. **size-availability** — asks about sizes, stock, ordering ("available in 50mm?", "how much do I need?", "where can I order?")
4. **commercial** — asks about price, quotes, bulk deals, freight ("how much does it cost?", "bulk discount?", "can you quote?")
5. **escalate** — mentions compliance, fire, NCC, guarantees, legal issues ("is it fire-rated?", "NCC compliant?", "liability?")

Message: "{message}"

Respond ONLY with the category name (lowercase, one word). No explanation.
"""


class RouterClassification:
    """Result of message classification."""

    def __init__(self, category: str, confidence: float = 0.8):
        self.category = category  # informational | product-fit | size-availability | commercial | escalate
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

    def classify(self, message: str) -> RouterClassification:
        """
        Classify a message. Returns RouterClassification with category + confidence.
        Falls back to rules if LLM fails.
        """
        if not message or not isinstance(message, str):
            return RouterClassification("product-fit", confidence=0.5)

        # Try LLM first
        if self.use_llm:
            try:
                result = self._classify_llm(message)
                if result:
                    return result
            except Exception:
                pass  # Fall through to rules

        # Fallback to rules
        return self._classify_rules(message)

    def _classify_llm(self, message: str) -> RouterClassification | None:
        """Use the local model to classify. Returns None on failure."""
        try:
            prompt = CLASSIFIER_PROMPT.format(message=message[:500])
            reply = llm_client.phrase(prompt, context={})

            category = reply.strip().lower()
            # Validate category
            valid = {"informational", "product-fit", "size-availability", "commercial", "escalate"}
            if category in valid:
                return RouterClassification(category, confidence=0.95)
        except Exception:
            pass
        return None

    def _classify_rules(self, message: str) -> RouterClassification:
        """Fallback rules-based classification."""
        msg_lower = message.lower()

        # Check escalate first (highest priority)
        if _ESCALATE_Q_RE.search(msg_lower):
            return RouterClassification("escalate", confidence=0.7)

        # Check commercial (price/ordering)
        if _COMMERCIAL_Q_RE.search(msg_lower):
            return RouterClassification("commercial", confidence=0.7)

        # Check size/availability
        if _SIZE_Q_RE.search(msg_lower):
            return RouterClassification("size-availability", confidence=0.7)

        # Check if sounds like product-fit (e.g., describing a scenario)
        if any(kw in msg_lower for kw in ["my", "our", "house", "building", "garage", "attic", "retrofit", "new build", "basement"]):
            return RouterClassification("product-fit", confidence=0.6)

        # Default to product-fit (most common case)
        return RouterClassification("product-fit", confidence=0.5)
