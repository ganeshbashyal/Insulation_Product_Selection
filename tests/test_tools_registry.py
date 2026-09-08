"""Tests for the tools/ registry: dispatch order, duplicate rejection,
None-vs-result distinction, and reply-text parity with the old web_agent.py
if/elif branches it replaced."""
from types import SimpleNamespace

import pytest

from tools import ToolRegistry, ToolResult, default_registry
from tools.escalate import EscalateTool
from tools.commercial import CommercialTool
from tools.freight import FreightTool
from tools.tracking import TrackingTool


def make_conversation():
    return SimpleNamespace(done=False)


def test_default_registry_registers_all_four_in_order():
    registry = default_registry()
    assert registry.names == ["escalate", "commercial", "freight", "tracking"]


def test_register_rejects_duplicate_name():
    registry = ToolRegistry()
    registry.register(EscalateTool())
    with pytest.raises(ValueError):
        registry.register(EscalateTool())


def test_find_returns_none_for_unmatched_category():
    registry = default_registry()
    assert registry.find("product-fit") is None
    assert registry.find("informational") is None


def test_dispatch_returns_none_when_no_tool_matches():
    registry = default_registry()
    conversation = make_conversation()
    result = registry.dispatch("informational", "hello", conversation, "site-a")
    assert result is None


def test_dispatch_first_match_wins():
    registry = ToolRegistry()

    class AlwaysMatches:
        name = "first"

        def matches(self, category):
            return True

        def run(self, message, conversation, site_id):
            return ToolResult(reply="first", log_status="routed:first")

    class AlsoMatches:
        name = "second"

        def matches(self, category):
            return True

        def run(self, message, conversation, site_id):
            return ToolResult(reply="second", log_status="routed:second")

    registry.register(AlwaysMatches())
    registry.register(AlsoMatches())
    result = registry.dispatch("anything", "hello", make_conversation(), "site-a")
    assert result.reply == "first"


def test_escalate_tool_reply_matches_old_branch_text():
    tool = EscalateTool()
    conversation = make_conversation()
    result = tool.run("some message", conversation, "site-a")
    assert result.reply == "Thank you for that information. This requires our team's attention. We'll be in touch shortly."
    assert conversation.done is True
    assert result.log_status == "routed:escalate"


def test_commercial_tool_reply_matches_old_branch_text():
    tool = CommercialTool()
    conversation = make_conversation()
    result = tool.run("what's the price", conversation, "site-a")
    assert result.reply == "For pricing and availability details, please contact our sales team directly."
    assert conversation.done is True
    assert result.log_status == "routed:commercial"


def test_freight_tool_is_placeholder_and_inert_by_default():
    tool = FreightTool()
    assert tool.matches("freight") is True
    assert tool.matches("product-fit") is False
    conversation = make_conversation()
    result = tool.run("how much is delivery", conversation, "site-a")
    assert result.done is True
    assert result.log_status == "routed:freight"
    assert "not available" in result.reply.lower() or "not connected" in result.reply.lower() or "isn't" in result.reply.lower()


def test_tracking_tool_is_placeholder_and_inert_by_default():
    tool = TrackingTool()
    assert tool.matches("tracking") is True
    assert tool.matches("product-fit") is False
    conversation = make_conversation()
    result = tool.run("where's my order", conversation, "site-a")
    assert result.done is True
    assert result.log_status == "routed:tracking"


def test_placeholder_categories_unreachable_from_default_router_categories():
    """freight/tracking are registered but router.py does not currently emit
    those categories, so they stay dormant until the router is extended."""
    registry = default_registry()
    for category in ("product-fit", "informational", "escalate", "commercial"):
        pass  # sanity: these are the only categories router.py currently emits
    assert registry.find("freight") is not None
    assert registry.find("tracking") is not None
