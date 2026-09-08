"""Protocol and result type for a routed conversation tool."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolResult:
    """What a tool produced, plus what should be logged for it.

    ``done`` mirrors the existing escalate/commercial behaviour: those turns
    end the conversation. A tool sets it False to allow follow-up turns (not
    used by the current placeholders, but freight/tracking will need it once
    they support "what about a 40ft container" style follow-ups).
    """

    reply: str
    done: bool = True
    log_status: str = ""
    log_reason: str = ""
    log_extra: dict[str, Any] = field(default_factory=dict)


class Tool(Protocol):
    """A handler for one router category.

    ``name`` must be unique within a registry; it becomes the interaction log's
    ``gate_status`` prefix (``routed:<name>``), so keep it short and stable -
    changing it later fragments the audit trail's history for that tool.
    """

    name: str

    def matches(self, category: str) -> bool:
        """Should this tool handle a message classified as ``category``?"""
        ...

    def run(self, message: str, conversation: Any, site_id: str) -> ToolResult:
        """Produce a reply. Must not raise for local/offline conditions -
        callers treat an exception as an unhandled failure, not a fallback."""
        ...
