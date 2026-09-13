"""Local-only order-tracking hand-off until an order export is available."""
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
