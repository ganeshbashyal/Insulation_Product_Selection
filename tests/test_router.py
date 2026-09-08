"""Tests for message router (LLM classifier + rules fallback)."""
import pytest

import llm_client
from router import MessageRouter, RouterClassification


@pytest.fixture
def router():
    """Create a MessageRouter with LLM enabled."""
    return MessageRouter(use_llm=True)


@pytest.fixture
def router_rules_only():
    """Create a MessageRouter with rules only (no LLM)."""
    return MessageRouter(use_llm=False)


class TestRouterClassification:
    """Tests for RouterClassification dataclass."""

    def test_classification_properties(self):
        """Classification has correct properties."""
        c = RouterClassification("product-fit", confidence=0.9)
        assert c.category == "product-fit"
        assert c.confidence == 0.9
        assert c.is_informational is False
        assert c.is_commercial is False
        assert c.is_escalate is False

    def test_escalate_property(self):
        """Escalate classification is recognized."""
        c = RouterClassification("escalate")
        assert c.is_escalate is True

    def test_commercial_property(self):
        """Commercial classification is recognized."""
        c = RouterClassification("commercial")
        assert c.is_commercial is True

    def test_informational_property(self):
        """Informational classification is recognized."""
        c = RouterClassification("informational")
        assert c.is_informational is True


class TestRulesBasedClassification:
    """Tests for rules-only router (no LLM)."""

    def test_escalate_ncc(self, router_rules_only):
        """Messages mentioning NCC are escalated."""
        c = router_rules_only.classify("Is this NCC compliant?")
        assert c.is_escalate

    def test_escalate_fire(self, router_rules_only):
        """Messages mentioning fire are escalated."""
        c = router_rules_only.classify("Does it have fire rating?")
        assert c.is_escalate

    def test_escalate_bal(self, router_rules_only):
        """Messages mentioning BAL are escalated."""
        c = router_rules_only.classify("What's the BAL rating?")
        assert c.is_escalate

    def test_commercial_price(self, router_rules_only):
        """Messages asking about price are commercial."""
        c = router_rules_only.classify("How much does it cost?")
        assert c.is_commercial

    def test_commercial_quote(self, router_rules_only):
        """Messages asking for quote are commercial."""
        c = router_rules_only.classify("Can you give me a quote?")
        assert c.is_commercial

    def test_size_availability(self, router_rules_only):
        """Messages asking about sizes are size-availability."""
        c = router_rules_only.classify("Available in 50mm?")
        assert c.category == "size-availability"

    def test_size_stock(self, router_rules_only):
        """Messages asking about stock are size-availability."""
        c = router_rules_only.classify("Is this in stock?")
        assert c.category == "size-availability"

    def test_product_fit_scenario(self, router_rules_only):
        """Messages describing a scenario are product-fit."""
        c = router_rules_only.classify("Our house is a single storey brick.")
        assert c.is_commercial is False  # Not commercial

    def test_informational_default(self, router_rules_only):
        """Unclassified messages default to product-fit."""
        c = router_rules_only.classify("Tell me about insulation")
        # Rules don't specifically target "informational", so defaults to product-fit
        assert c.category in ("product-fit", "informational")

    def test_empty_message(self, router_rules_only):
        """Empty message gets default classification."""
        c = router_rules_only.classify("")
        assert c.confidence < 1.0  # Low confidence on empty

    def test_none_message(self, router_rules_only):
        """None message gets default classification."""
        c = router_rules_only.classify(None)
        assert c.category == "product-fit"


class TestLLMClassification:
    """Local-model classification, with the Ollama boundary stubbed.

    These must not call the live model: a real call costs ~15s each, makes the
    suite non-deterministic, and asserting only "some valid category came back"
    would pass even if the classifier were broken. Here the model's reply is
    fixed so the parsing, validation and fallback logic are what get tested.
    """

    def test_llm_reply_is_used(self, router, monkeypatch):
        """A valid category from the model is trusted and reported confidently."""
        monkeypatch.setattr(llm_client, "phrase", lambda *a, **k: "commercial")
        c = router.classify("What is an R-value?")
        assert c.category == "commercial"  # proves the model's reply won, not the rules
        assert c.confidence == 0.95

    def test_llm_reply_is_normalised(self, router, monkeypatch):
        """Whitespace/casing from the model is tolerated."""
        monkeypatch.setattr(llm_client, "phrase", lambda *a, **k: "  ESCALATE\n")
        assert router.classify("Is this NCC compliant?").category == "escalate"

    def test_invalid_llm_reply_falls_back_to_rules(self, router, monkeypatch):
        """A category outside the allowed set is discarded, not passed through."""
        monkeypatch.setattr(llm_client, "phrase", lambda *a, **k: "banana")
        c = router.classify("Does it meet NCC requirements?")
        assert c.category == "escalate"  # from the rules, which catch "NCC"
        assert c.confidence == 0.7

    def test_llm_exception_falls_back_to_rules(self, router, monkeypatch):
        """An unreachable/erroring model must not break classification."""
        def boom(*a, **k):
            raise RuntimeError("ollama down")

        monkeypatch.setattr(llm_client, "phrase", boom)
        c = router.classify("How much does it cost?")
        assert c.category == "commercial"
        assert c.confidence == 0.7


class TestRouterEdgeCases:
    """Edge cases and special scenarios."""

    def test_very_long_message(self, router_rules_only):
        """Very long message is classified (truncated if needed)."""
        long_msg = "Tell me " * 1000 + "about insulation"
        c = router_rules_only.classify(long_msg)
        assert c.category in {"informational", "product-fit", "size-availability", "commercial", "escalate"}

    def test_message_with_numbers(self, router_rules_only):
        """Message with numbers is classified."""
        c = router_rules_only.classify("I need 50mm thickness for my 100sqm attic")
        # Should recognize "50mm" as size-related
        assert c.category == "size-availability" or c.category == "product-fit"

    def test_case_insensitivity(self, router_rules_only):
        """Rules are case-insensitive."""
        c1 = router_rules_only.classify("Is it NCC compliant?")
        c2 = router_rules_only.classify("is it ncc compliant?")
        assert c1.category == c2.category

    def test_multiple_triggers(self, router_rules_only):
        """Message with multiple triggers uses priority (escalate > commercial > size > product-fit)."""
        # Message with both price and NCC
        c = router_rules_only.classify("What's the cost and NCC rating?")
        # Should escalate (higher priority than commercial)
        assert c.is_escalate

    def test_confidence_decreases_with_fallback(self, router_rules_only):
        """Rules-based classification has lower confidence than LLM."""
        c_rules = router_rules_only.classify("What is R-value?")
        # Rules return 0.5-0.7 for default cases
        assert c_rules.confidence <= 0.8
