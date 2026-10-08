"""Pricing boundary: direct customers to sales without ending their intake."""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class CommercialTool:
    name = "commercial"

    def matches(self, category: str) -> bool:
        return category == "commercial"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        return ToolResult(
            reply="For pricing and availability details, please contact our sales team directly.",
            done=conversation.done,
            log_status="routed:commercial",
            log_reason="Router classified this as commercial; no product recommendation was made.",
        )
