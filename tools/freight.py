"""Freight/shipping cost placeholder.

Per the user's decision this session: freight is driven by a local rate table
(CSV/JSON in the repo), not a carrier API - keeping it local-only. That table
does not exist yet, so this tool is wired into the registry but inert: it only
matches a "freight" router category, which router.py does not currently emit.
Registering it now means adding the category and the rate table later needs no
change to web_agent.py's dispatch code.
"""
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
