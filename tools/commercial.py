"""Pricing/quoting hand-off. Extracted from web_agent.py's former if/elif
chain; behaviour is unchanged from before the registry existed."""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class CommercialTool:
    name = "commercial"

    def matches(self, category: str) -> bool:
        return category == "commercial"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        conversation.done = True
        return ToolResult(
            reply="For pricing and availability details, please contact our sales team directly.",
            done=True,
            log_status="routed:commercial",
            log_reason="Router classified this as commercial; no product recommendation was made.",
        )
