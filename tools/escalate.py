"""Compliance/legal/safety hand-off. Extracted from web_agent.py's former
if/elif chain; behaviour is unchanged from before the registry existed."""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class EscalateTool:
    name = "escalate"

    def matches(self, category: str) -> bool:
        return category == "escalate"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        conversation.done = True
        return ToolResult(
            reply=(
                "Thank you for that information. This requires our team's "
                "attention. We'll be in touch shortly."
            ),
            done=True,
            log_status="routed:escalate",
            log_reason="Router classified this as escalate; no product recommendation was made.",
        )
