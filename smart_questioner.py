"""Smart questioner: context-aware follow-ups based on conversation state.

Adapts questions based on:
- Router classification (product-fit context)
- Conversation history (what they've already said)
- Scenario hints (garage, retrofit, new build, etc.)
"""
from __future__ import annotations

import re

import agent_core
import llm_client
from router import MessageRouter

# Scenario patterns
GARAGE_PATTERN = re.compile(r"\b(garage|carport|shed|outbuilding)\b", re.IGNORECASE)
RETROFIT_PATTERN = re.compile(r"\b(retrofit|upgrade|replace|existing|old|current)\b", re.IGNORECASE)
NEW_BUILD_PATTERN = re.compile(r"\b(new\s+build|new\s+house|building|construction|newly)\b", re.IGNORECASE)
THERMAL_PATTERN = re.compile(r"\b(thermal|warm|cold|temperature|heat|cool)\b", re.IGNORECASE)
ACOUSTIC_PATTERN = re.compile(r"\b(sound|noise|quiet|acoustic|echo)\b", re.IGNORECASE)

# Question mappings by scenario
SCENARIO_QUESTIONS = {
    "garage": [
        "Is this for thermal comfort, noise reduction, or both?",
        "Are you planning a retrofit or new construction?",
    ],
    "retrofit": [
        "What's your main concern — staying warm, keeping cool, or reducing noise?",
        "Are you working with existing walls or starting fresh?",
    ],
    "new_build": [
        "What climate zone are you building in?",
        "Is thermal performance or sound isolation your priority?",
    ],
}


class SmartQuestioner:
    """Context-aware question flow using router + conversation state."""

    def __init__(self, use_llm: bool = True):
        self.router = MessageRouter(use_llm=use_llm)
        self.use_llm = use_llm

    def next_question(self, conversation: agent_core.Conversation) -> str:
        """
        Generate next question based on conversation context.
        Returns a naturally-phrased question tailored to what they've said so far.
        """
        answers = conversation.answers
        problem = answers.get("problem", "")

        # Detect scenario from conversation history
        scenario = self._detect_scenario(problem)

        # Get appropriate question for scenario
        question = self._get_contextual_question(scenario, answers)

        # Use LLM to rephrase naturally if enabled
        if self.use_llm and question:
            question = self._rephrase_naturally(question, problem)

        return question or self._default_question()

    def _detect_scenario(self, problem: str) -> str | None:
        """Detect building scenario from problem statement."""
        if GARAGE_PATTERN.search(problem):
            return "garage"
        if NEW_BUILD_PATTERN.search(problem):
            return "new_build"
        if RETROFIT_PATTERN.search(problem):
            return "retrofit"
        return None

    def _get_contextual_question(self, scenario: str | None, answers: dict) -> str:
        """Get next question based on scenario and what they've told us."""
        asked = set(answers.keys())

        # If we know the scenario, ask scenario-specific follow-ups
        if scenario and scenario in SCENARIO_QUESTIONS:
            for q in SCENARIO_QUESTIONS[scenario]:
                if q not in asked:
                    return q

        # Default fallback to standard flow (but skip some if we already know)
        if "project" not in asked:
            return "Are you working on a new build or retrofit?"
        if "priority" not in asked:
            return "What's your main concern — thermal comfort, noise reduction, or both?"
        if "climate_zone" not in asked:
            return "What's your climate zone or general location?"
        if "locality" not in asked:
            return "Can you tell me more about your building location?"

        return ""

    def _rephrase_naturally(self, question: str, context: str) -> str:
        """Use LLM to rephrase question naturally based on context."""
        try:
            prompt = f"""Rephrase this question to sound natural and conversational, as if asked by an experienced insulation adviser who understands: \"{context}\"

Original question: {question}

Rephrased (natural, 1-2 sentences, Australian construction language):"""
            response = llm_client.phrase(prompt, context={})
            return response.strip() if response else question
        except Exception:
            return question

    def _default_question(self) -> str:
        """Fallback to first standard question if nothing else fits."""
        return agent_core.QUESTIONS[0][1]
