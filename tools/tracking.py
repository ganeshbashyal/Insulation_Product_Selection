"""Local-only order-tracking hand-off until an order export is available."""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class TrackingTool:
    name = "tracking"

    def matches(self, category: str) -> bool:
        return category == "tracking"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        return ToolResult(
            reply="Order tracking is not connected locally. Please contact sales with your order reference to check its status.",
            done=conversation.done,
            log_status="routed:tracking",
            log_reason="Router classified this as tracking; placeholder tool has no order system yet.",
        )
