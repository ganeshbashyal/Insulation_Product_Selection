"""Deterministic, application-specific discovery; no product approval."""
from __future__ import annotations

import re

from bot_engine import detected_priority, text_elements

QUESTIONS = {
    "application": "Where is the problem: a wall, roof or ceiling, floor, pipe, or somewhere else?",
    "priority": "What would you most like to improve: temperature, noise, moisture, or something else?",
    "placement": "Which part needs insulation: {options}?",
    "project_stage": "Is this an existing building being upgraded, or a new build?",
    "building_use": "What is the building used for: a home, commercial premises, or something else?",
    "construction": "Do you know how the {element} is built - for example, its frame or layers?",
    "wall_assembly": "Is that brick veneer with a framed cavity, solid/double brick, or another arrangement? Unknown is fine.",
    "access": "What access is available to install insulation{access_hint}?",
    "cavity_depth": "How much usable depth or clearance is available for insulation? An estimate or 'unknown' is fine.",
    "area": "Roughly how large is the affected area, or what dimensions do you have?",
    "existing_insulation": "What insulation is already there, if any?",
    "moisture": "Are there any dampness, condensation, leaks or weather-exposure concerns?",
    "airspace": "Is there a continuous air gap beside the proposed insulation layer? If it hasn't been checked, say unknown.",
    "service": "What does the pipe or duct carry, and is it indoors or exposed outdoors?",
    "service_temperature": "What operating temperature does the pipe or duct need to handle? Unknown is fine.",
    "requirements": "Are there any specified thermal, acoustic, fire or other project requirements? None or unknown is fine.",
    "locality": "Which suburb or postcode is the project in?",
    "timeframe": "When are you planning the work? You can skip this.",
}

UNKNOWN = re.compile(r"\b(?:unknown|unsure|not sure|don't know|do not know|not known|haven't checked|not checked)\b", re.I)
SKIP = re.compile(r"^\s*(?:please\s+)?(?:skip(?: this)?|no thanks|rather not|prefer not to (?:say|answer)|pass)[.! ]*$", re.I)
EARLY_HANDOFF = re.compile(
    r"\b(?:finish (?:here|now)|stop (?:the )?questions|skip (?:the )?(?:remaining|rest)(?: questions)?|contact (?:details )?now|"
    r"(?:rather|prefer to|want to) (?:speak|talk) (?:with|to) (?:a person|someone|sales|the team))\b", re.I,
)


def element(answers: dict[str, str]) -> str | None:
    elements = text_elements(answers.get("application", "") or answers.get("problem", ""))
    return next(iter(elements)) if len(elements) == 1 else None


def observed(text: str) -> dict[str, str]:
    """Only explicit signals establish an answer; absence never means 'none'."""
    found = {}
    clauses = re.split(r"[,;]|\band\b", text, flags=re.I)
    signals = {
        "project_stage": r"\b(?:existing|retrofit(?:ting)?|renovat(?:ion|ing)|new build|new home|new construction)\b",
        "building_use": r"\b(?:residential|commercial|industrial|house|home|apartment|townhouse|school|hospital|office)\b",
        "construction": r"\b(?:brick|masonry|plasterboard|timber frame|steel frame|concrete|blockwork|metal roof|tile[d]? roof|timber floor)\b",
        "wall_assembly": r"\b(?:brick veneer|solid brick|double brick|solid masonry|timber frame|steel frame)\b",
        "access": r"\b(?:access|inaccessible|lining (?:will|can|must)|(?:remove|removing|removed|intact).{0,25}(?:lining|plasterboard)|(?:lining|plasterboard).{0,25}(?:remove|removed|intact))\b",
        "cavity_depth": r"\b(?:cavity|depth|clearance).{0,25}\d+\s*mm\b|\b\d+\s*mm.{0,25}(?:cavity|depth|clearance)\b",
        "area": r"\b\d+(?:\.\d+)?\s*(?:m2|m\u00b2|sqm|square metres?)\b|\b\d+(?:\.\d+)?\s*(?:m|metres?)\s*(?:by|x)\s*\d+",
        "existing_insulation": r"\b(?:existing insulation|already insulated|no insulation|uninsulated|old insulation|insulation already)\b",
        "moisture": r"\b(?:damp|dampness|condensation|leaks?|weather exposure|exposed outdoors|mould|moisture)\b",
        "airspace": r"\b(?:airspace|air gap|air space)\b",
        "placement": r"\b(?:(?:internal|external|interior|exterior)(?:\s+(?:brick(?: veneer)?|timber(?: frame)?|steel(?: frame)?|masonry|concrete))?\s+walls?|ceiling level|roofline|rafters?|underfloor|subfloor|between (?:floors|storeys)|floor finish)\b",
        "service": r"\b(?:waste pipe|hot water|cold water|steam|air conditioning|ventilation duct)\b",
        "service_temperature": r"\b\d+\s*(?:degrees|deg|celsius|\u00b0c)\b",
        "timeframe": r"\b(?:next (?:week|month)|this (?:week|month)|urgent|asap|no rush|within \d+ (?:weeks?|months?))\b",
    }
    for key, pattern in signals.items():
        matches = [clause.strip() for clause in clauses if re.search(pattern, clause, re.I)]
        if matches:
            found[key] = ", ".join(matches)
    return found


def fields_for(answers: dict[str, str]) -> list[str]:
    which = element(answers)
    fields = ["application", "priority", "placement", "project_stage", "building_use"]
    if which == "pipe_duct":
        fields += ["service", "service_temperature", "access", "cavity_depth"]
    else:
        fields += ["construction"]
        construction = answers.get("construction", "")
        if which == "wall" and re.search(r"\bbrick\b", construction, re.I):
            fields += ["wall_assembly"]
        fields += ["access", "cavity_depth", "area", "existing_insulation"]
    fields += ["moisture"]
    priority = detected_priority(answers.get("priority", ""), answers.get("problem", ""))
    if which in {"wall", "roof"} and priority == "energy_efficiency":
        fields += ["airspace"]
    return fields + ["requirements", "locality", "timeframe"]


def next_field(answers: dict[str, str], statuses: dict[str, str]) -> str | None:
    return next((
        key for key in fields_for(answers)
        if statuses.get(key) == "conflict" or (not answers.get(key) and key not in statuses)
    ), None)


def question(key: str, answers: dict[str, str]) -> str:
    which = element(answers)
    if key == "application":
        priority = detected_priority(answers.get("priority", ""), answers.get("problem", ""))
        if priority == "acoustic_comfort":
            return "Where is the noise coming through: a wall, roof or ceiling, floor, pipe, or somewhere else?"
        return "Where is the insulation needed: a wall, roof or ceiling, floor, pipe, or somewhere else?"
    options = {
        "wall": "an internal partition or an external wall",
        "roof": "above the ceiling or up at the roofline/rafters",
        "floor": "under a ground floor, between storeys, or beneath the floor finish",
        "pipe_duct": "the pipe, duct, or surrounding enclosure",
    }
    access_hint = " - will the lining be removed, or must it stay intact" if which == "wall" else ""
    return QUESTIONS[key].format(
        element={"pipe_duct": "pipe or duct"}.get(which, which or "affected area"),
        options=options.get(which, "the affected layer or location"),
        access_hint=access_hint,
    )


def completeness(answers: dict[str, str], statuses: dict[str, str]) -> dict:
    unresolved = [
        key for key in fields_for(answers)
        if (not answers.get(key) or statuses.get(key) in {"unknown", "skipped", "conflict"}
            or UNKNOWN.search(answers.get(key, "")))
    ]
    return {
        "status": "needs_followup" if unresolved else "captured_for_review",
        "unresolved_fields": unresolved,
        "field_status": {key: statuses.get(key, "provided" if answers.get(key) else "not_asked") for key in fields_for(answers)},
        "note": "Customer-reported details are not verified design or installation evidence.",
    }
