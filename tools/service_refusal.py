"""Refusal for services this business does not offer.

The business operates supply-only: it must never offer, imply availability
of, or quote for installation, removal/vacuuming of existing insulation, or
tool hire. This tool intercepts those requests before any product
recommendation logic runs, so a customer asking "can you install this?"
never gets a batt recommendation as if that answered the question.
"""
from __future__ import annotations

from typing import Any

from .base import ToolResult


class ServiceRefusalTool:
    name = "service_refusal"

    def matches(self, category: str) -> bool:
        return category == "service_refusal"

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        conversation.done = True
        return ToolResult(
            reply=(
                "We supply insulation products only - we don't offer installation, "
                "removal or vacuuming of existing insulation, or tool hire. "
                "A licensed installer or removalist in your area can help with that "
                "part of the job."
            ),
            done=True,
            log_status="routed:service_refusal",
            log_reason="Router classified this as a request for a service (install/removal/tool hire) the business does not offer.",
        )
