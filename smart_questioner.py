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


def _looks_like_a_question(text: str | None) -> bool:
    """Reject anything that isn't a short, single-line reply.

    Guards against a local LLM echoing prompt scaffolding back verbatim
    instead of actually rephrasing (e.g. returning "Rephrase this
    question..." or "Original question: ..." as if that were the message) -
    the caller falls back to the plain deterministic question when this
    returns False.
    """
    if not text or "\n" in text:
        return False
    if len(text) > 220:
        return False
    lowered = text.casefold()
    if "rephrase" in lowered or "original question" in lowered:
        return False
    return True


class SmartQuestioner:
    """Context-aware question flow using router + conversation state."""

    def __init__(self, use_llm: bool = True):
        self.router = MessageRouter(use_llm=use_llm)
        self.use_llm = use_llm

    def next_question(self, conversation: any, step: int | None = None) -> str:
        """
        Generate next question based on conversation context and active step.
        Returns a naturally-phrased question tailored to what they've said so far.
        """
        answers = conversation.answers
        problem = answers.get("problem", "")

        # If we have no problem statement yet, return default
        if not problem:
            return ""

        # Determine the active step (prefer explicitly passed step, fallback to conversation.step or length)
        active_step = step
        if active_step is None:
            active_step = getattr(conversation, "step", None)
        if active_step is None:
            active_step = len(answers)

        if active_step >= len(agent_core.QUESTIONS):
            return ""

        # Get the standard key and default question for the active step
        key, default_question = agent_core.QUESTIONS[active_step]

        # Scenario-specific customization of standard questions before LLM rephrasing
        scenario = self._detect_scenario(problem)
        question = default_question

        if key == "application":
            if scenario == "retrofit":
                question = "Where is this retrofit happening — wall, floor, roof, pipe or somewhere else?"
            elif scenario == "garage":
                question = "Is this insulation for the garage wall, roof, ceiling, or somewhere else?"
        elif key == "priority":
            if scenario == "retrofit":
                question = "For this retrofit, what matters most: comfort, energy savings, budget, or acoustic performance?"
            elif scenario == "garage":
                question = "What's the main priority for your garage insulation: climate control, noise reduction, or budget?"
        elif key == "project":
            if scenario == "retrofit":
                question = "Is this bathroom or building retrofit residential, commercial, or industrial?"
            elif scenario == "garage":
                question = "Is your garage project residential, commercial, or industrial?"

        # Use LLM to rephrase naturally if enabled
        if self.use_llm and question:
            question = self._rephrase_naturally(question, problem)

        return question or default_question

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
        """Deprecated: kept for backward compatibility if called elsewhere."""
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
        """Use the LLM to rephrase a question naturally, grounded in what the
        customer has already told us.

        Reuses llm_client.phrase() - the same guardrailed rephrasing path
        used everywhere else in the app - instead of building a second,
        separate meta-prompt ("Rephrase this question... Original question:
        ... Rephrased:") on top of it. That double-prompt made a small local
        model sometimes echo the whole instruction back verbatim as if it
        were the chat reply, which is exactly the bug this fixes: a customer
        must never see prompt scaffolding instead of a real question.
        """
        try:
            rephrased = llm_client.phrase(question, context={"customer_said": context} if context else None)
        except Exception:
            return question
        return rephrased if _looks_like_a_question(rephrased) else question

    def _default_question(self) -> str:
        """Fallback to first standard question if nothing else fits."""
        return agent_core.QUESTIONS[0][1]
