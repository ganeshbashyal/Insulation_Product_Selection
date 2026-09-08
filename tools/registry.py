"""Ordered registry of tools, tried first-match-wins."""
from __future__ import annotations

from typing import Any

from .base import Tool, ToolResult


class ToolRegistry:
    """Holds tools in registration order and dispatches by category match.

    First match wins deliberately: it makes ordering the one thing a caller
    must get right, rather than requiring every tool to negotiate priority
    with every other tool's ``matches()``.
    """

    def __init__(self) -> None:
        self._tools: list[Tool] = []

    def register(self, tool: Tool) -> None:
        if any(t.name == tool.name for t in self._tools):
            raise ValueError(f"tool name already registered: {tool.name}")
        self._tools.append(tool)

    def find(self, category: str) -> Tool | None:
        for tool in self._tools:
            if tool.matches(category):
                return tool
        return None

    def dispatch(self, category: str, message: str, conversation: Any, site_id: str) -> ToolResult | None:
        """Run the first matching tool, or return None if none match.

        Returning None (rather than a "no match" ToolResult) keeps the
        distinction visible to the caller: "no tool wanted this category" is
        not the same outcome as "a tool ran and had nothing to say".
        """
        tool = self.find(category)
        if tool is None:
            return None
        return tool.run(message, conversation, site_id)

    @property
    def names(self) -> list[str]:
        return [t.name for t in self._tools]


def default_registry() -> ToolRegistry:
    """The registry web_agent.py wires up: escalate/commercial handoffs plus
    the freight and tracking placeholders. Kept as a factory (not a module
    singleton) so tests can build an isolated registry without import-order
    side effects.
    """
    from .escalate import EscalateTool
    from .commercial import CommercialTool
    from .freight import FreightTool
    from .tracking import TrackingTool

    registry = ToolRegistry()
    for tool in (EscalateTool(), CommercialTool(), FreightTool(), TrackingTool()):
        registry.register(tool)
    return registry
