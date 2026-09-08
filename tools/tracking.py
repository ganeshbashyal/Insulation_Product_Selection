"""Order-tracking placeholder.

No order/shipment system is wired up yet (MYOB integration was mentioned as
future scope, not this session's work). This tool exists so the registry shape
is proven with more than one placeholder, and so wiring a real tracking lookup
later is a change to this file only, not to web_agent.py's dispatch code.
"""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class TrackingTool:
    name = "tracking"

    def matches(self, category: str) -> bool:
        return category == "tracking"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        conversation.done = True
        return ToolResult(
            reply="Order tracking isn't connected yet - a team member will follow up on your order status.",
            done=True,
            log_status="routed:tracking",
            log_reason="Router classified this as tracking; placeholder tool has no order system yet.",
        )
