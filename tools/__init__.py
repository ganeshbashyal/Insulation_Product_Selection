"""Pluggable tool registry for non-product-fit conversation categories.

The dispatcher in web_agent.py used to be a hardcoded if/elif chain keyed on
router category. Adding freight, tracking, or MYOB meant editing that function
each time, and it was easy to forget the interaction-logging call for a new
branch (escalate/commercial/informational turns went unlogged until 86a6739
fixed that omission for the existing categories).

A Tool is: matches(classification) -> bool, run(message, conversation, site_id)
-> str. Tools are tried in registration order; the first match wins. Logging
happens once, in the dispatch loop, so a new tool cannot silently skip it.

Local-only: no tool in this package may call a paid/hosted API. See each
tool's docstring for what it actually does today (freight and tracking are
placeholders pending real rate tables / order systems).
"""
from __future__ import annotations

from .base import Tool, ToolResult
from .registry import ToolRegistry, default_registry

__all__ = ["Tool", "ToolResult", "ToolRegistry", "default_registry"]
