"""Shared, types-only schema for explicit assistant persona contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantContract:
    persona_id: str
    audience: str
    purpose: str
    tone: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    restricted_sources: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    memory_boundary: str
    output_format: tuple[str, ...]
    escalation_rules: tuple[str, ...]
    model_prompt: str | None = None

    def __post_init__(self) -> None:
        if not self.persona_id or not self.audience or not self.purpose or not self.memory_boundary:
            raise ValueError("Persona contract identity, audience, purpose, and memory boundary are required")
