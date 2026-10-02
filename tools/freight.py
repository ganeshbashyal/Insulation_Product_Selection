"""Local-only freight hand-off until a reviewed rate table is available."""
from __future__ import annotations

from typing import Any

from .base import ToolResult

RATE_TABLE_NOTE = (
    "Freight costing isn't available yet - a team member will confirm delivery "
    "cost and timing for your postcode."
)


class FreightTool:
    name = "freight"

    def matches(self, category: str) -> bool:
        return category == "freight"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        conversation.done = True
        return ToolResult(
            reply=RATE_TABLE_NOTE,
            done=True,
            log_status="routed:freight",
            log_reason="Router classified this as freight; placeholder tool has no rate table yet.",
        )
