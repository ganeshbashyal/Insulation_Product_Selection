"""Pure recommendation and gating logic used by the Streamlit UI and tests."""
from __future__ import annotations

import re
import json
from difflib import SequenceMatcher
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "matching.json"
MATCHING_CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
STATE_CONFIG = json.loads((CONFIG_PATH.parent / "catalogue_states.json").read_text(encoding="utf-8"))
FUZZY_WORD_THRESHOLD = float(MATCHING_CONFIG["fuzzy_word_threshold"])
NO_RELIABLE_MATCH_SCORE = float(MATCHING_CONFIG["no_reliable_match_score"])
SINGULARISATION_EXCEPTIONS = set(MATCHING_CONFIG["singularisation_exceptions"])

PRIORITY_LABELS = {
    "acoustic_comfort": "Acoustic comfort",
    "energy_efficiency": "Energy efficiency",
    "sustainability": "Sustainability",
    "installation_practicality": "Installation practicality",
    "compliance_readiness": "Evidence readiness",
}

PRIORITY_TERMS = {
    "acoustic_comfort": ["acoustic", "quiet", "noise", "noisy", "sound", "soundproof"],
    "energy_efficiency": ["energy", "thermal", "heat", "hot", "cold", "summer", "winter", "temperature", "condensation", "efficiency", "r-value", "r value"],
    "sustainability": ["sustainable", "sustainability", "environment", "recycled", "low carbon"],
    "installation_practicality": ["install", "easy", "access", "space", "thin", "practical", "retrofit"],
    "compliance_readiness": ["compliance", "ncc", "fire", "bal", "spec", "consultant", "certification"],
}

SYNONYMS = MATCHING_CONFIG["synonyms"]

RECOMMENDATION_ALLOWED_STATES = set(STATE_CONFIG["recommendation_allowed"])
RECOMMENDATION_BLOCKED_STATES = set(STATE_CONFIG["recommendation_blocked"])


def canonical_text(value: str) -> str:
    text = value.casefold().replace("’", "'")
    for phrase, replacement in sorted(SYNONYMS.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(phrase, replacement)
    return text


def normalised_words(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", canonical_text(value))
    return {word[:-1] if len(word) > 3 and word.endswith("s") and word not in SINGULARISATION_EXCEPTIONS else word for word in words}


def fuzzy_word_match(expected: str, actual_words: set[str]) -> bool:
    if len(expected) < 5:
        return False
    return any(SequenceMatcher(None, expected, actual).ratio() >= FUZZY_WORD_THRESHOLD for actual in actual_words if len(actual) >= 5)


def term_match_score(term: str, text: str, text_words: set[str]) -> float:
    folded_term = canonical_text(term)
    if folded_term in text:
        return 1.0
    term_words = normalised_words(folded_term)
    if term_words and term_words.issubset(text_words):
        return 0.95
    if term_words and all(word in text_words or fuzzy_word_match(word, text_words) for word in term_words):
        return 0.65
    return 0.0


def detected_priority(text: str, context: str = "") -> str:
    def score(source: str) -> dict[str, int]:
        folded = canonical_text(source)
        return {key: sum(term in folded for term in terms) for key, terms in PRIORITY_TERMS.items()}

    explicit = score(text)
    highest = max(explicit.values())
    leaders = [key for key, value in explicit.items() if value == highest and value > 0]
    if len(leaders) == 1:
        return leaders[0]
    contextual = score(context)
    combined = {key: explicit[key] * 3 + contextual[key] for key in PRIORITY_TERMS}
    best = max(combined, key=combined.get)
    return best if combined[best] else "energy_efficiency"


def placement_adjustment(family_id: str, text: str, priority: str) -> float:
    ceiling = any(x in text for x in ["ceiling level", "ceiling space", "above the ceiling", "below the roof space"])
    roofline = any(x in text for x in ["roofline", "rafter", "truss", "under the roof", "beneath the roof"])
    subfloor = any(x in text for x in ["subfloor", "underfloor", "under the suspended", "suspended ground floor"])
    between = any(x in text for x in ["between floors", "between storeys", "midfloor", "inter-floor", "inside the cavity between"])
    underlay = any(x in text for x in ["underlay", "beneath the floor finish", "under the carpet", "under laminate"])
    boosts = {
        "FLETCHER_PINK_BATTS_CEILING": 12 if ceiling and priority == "energy_efficiency" else 0,
        "FLETCHER_PINK_BATTS_FLOOR": 12 if subfloor and priority == "energy_efficiency" else 0,
        "FLETCHER_SOUNDBREAK": 12 if between and priority == "acoustic_comfort" else 0,
        "THERMOTEC_NUWAVE_UNDERLAY": 12 if underlay and priority == "acoustic_comfort" else 0,
        "THERMOTEC_E_THERM": 5 if roofline and priority == "energy_efficiency" else 0,
        "FLETCHER_PERMASTOP": 5 if roofline and priority == "energy_efficiency" else 0,
    }
    return boosts.get(family_id, 0)


def recommendation_allowed(family: dict | None) -> bool:
    if not family:
        return False
    return family.get("confidence") in RECOMMENDATION_ALLOWED_STATES


def rank_families(families: list[dict], answers: dict[str, str], manufacturer_scope: str | None = None) -> list[dict]:
    raw_text = " ".join(answers.values())
    text = canonical_text(raw_text)
    text_words = normalised_words(text)
    context = " ".join(value for key, value in answers.items() if key != "priority")
    priority = detected_priority(answers.get("priority", ""), context)
    ranked = []
    for family in families:
        if manufacturer_scope and manufacturer_scope != "Compare both" and family["manufacturer"].casefold() != manufacturer_scope.casefold():
            continue
        keyword_scores = [(term, term_match_score(term, text, text_words)) for term in family["keywords"]]
        application_scores = [(term, term_match_score(term, text, text_words)) for term in family["applications"]]
        keyword_hits = [term for term, score in keyword_scores if score]
        application_hits = [term for term, score in application_scores if score]
        match_score = sum(score for _, score in keyword_scores) * 4
        match_score += sum(score for _, score in application_scores) * 3
        match_score += family["scores"].get(priority, 0) * 1.5
        match_score += placement_adjustment(family["family_id"], text, priority)
        if not recommendation_allowed(family):
            match_score -= 6
        reliable_match = bool(keyword_hits or application_hits) and match_score >= NO_RELIABLE_MATCH_SCORE
        ranked.append({
            **family,
            "match_score": round(match_score, 3),
            "matched": keyword_hits + application_hits,
            "matched_keywords": keyword_hits,
            "matched_applications": application_hits,
            "priority_key": priority,
            "reliable_match": reliable_match,
        })
    return sorted(ranked, key=lambda item: (item["match_score"], item["scores"].get(priority, 0)), reverse=True)


def technical_gate(answers: dict[str, str], family: dict | None) -> tuple[str, str]:
    if family and not family.get("reliable_match", True):
        return "BLOCKED", "There is no reliable product-family match yet. A person needs to review the enquiry."
    if not recommendation_allowed(family):
        return "BLOCKED", "We need to confirm the product identity and evidence before selecting or quoting it."
    requirements = answers.get("requirements", "").casefold()
    if any(term in requirements for term in ["rw", "ncc", "fire", "bal", "bushfire", "consultant", "spec", "certifier"]):
        return "REVIEW REQUIRED", "The team needs to check the complete system against the stated requirement."
    return "REVIEW REQUIRED", "The team will confirm the construction, exact product and availability before quoting."
