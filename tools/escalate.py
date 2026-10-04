"""Explain the compliance boundary without closing intake or promising contact."""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class EscalateTool:
    name = "escalate"

    def matches(self, category: str) -> bool:
        return category == "escalate"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        return ToolResult(
            reply=(
                "I cannot confirm project compliance, fire or BAL suitability. "
                "The technical team needs to review the exact product, complete construction "
                "and project requirements. You can still ask me about documented product facts."
            ),
            done=conversation.done,
            log_status="routed:escalate",
            log_reason="Router classified this as escalate; no product recommendation was made.",
        )
