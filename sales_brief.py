"""Internal provisional family discovery, never customer-facing selection."""
from __future__ import annotations

import re

from bot_engine import PRIORITY_TERMS, detected_priority, family_elements, rank_families, recommendation_allowed, text_elements
from local_source_review import SourceReview
from enquiry_discovery import completeness, question

class SalesBriefBuilder:
    def __init__(self, families: list[dict]):
        from knowledge_release import configured_release
        self.release = configured_release()
        self.families = families
        self.sources = None if self.release else SourceReview()

    def build(self, answers: dict[str, str], *, scope: str | None = None, discovery_status: dict[str, str] | None = None, site_id: str = "default") -> dict:
        from knowledge_release import visible_family_ids
        allowed = visible_family_ids(self.release, site_id) if self.release else None
        # Research keywords can help discovery, but must not establish fit.
        canonical = [{
            **family,
            "applications": family.get("documented_applications", family["applications"]),
            "keywords": family.get("documented_keywords", family["keywords"]),
        } for family in self.families if recommendation_allowed(family)
            and (allowed is None or family["family_id"] in allowed)]
        text = " ".join(value for key, value in answers.items() if key != "name")
        ranked = rank_families(canonical, {key: value for key, value in answers.items() if key != "name"}, scope or "Compare both", use_hybrid=False)
        priority = detected_priority(answers.get("priority", ""), text)
        elements = text_elements(answers.get("application", "") or text)
        has_goal = any(term in text.casefold() for terms in PRIORITY_TERMS.values() for term in terms)
        candidates = []
        capture = completeness(answers, discovery_status or {})
        seen_roles = set()
        for family in ranked:
            if not has_goal or not elements.intersection(family_elements(family)):
                continue
            if family.get("category", "").casefold() in {"accessory", "wrap", "membrane", "mesh", "reflective facing", "drainage / ventilation", "pliable building membrane", "roof membrane"}:
                continue
            if not family["scores"].get(priority, 0) >= 3:
                continue
            role = (family.get("manufacturer", ""), family.get("category", ""))
            if role in seen_roles:
                continue
            seen_roles.add(role)
            source = ({"guide_checks": [], "source_gaps": ["Review installation and exact variant against current source before selection."],
                       "release_id": self.release["release_id"], "review_status": "human_review_required"}
                      if self.release else self.sources.family(family["family_id"], include_compiled=True))
            checks = list(dict.fromkeys(family.get("questions", []) + family.get("human_gates", []) + source["guide_checks"]))
            disposition = "HOLD"
            reasons = ["Installation feasibility and exact product remain unapproved."]
            if re.search(r"\b(?:no access|inaccessible|cannot remove|can't remove|not removing|must remain intact)\b", text, re.I):
                reasons.append("Restricted installation access stated; do not assume this family can be installed.")
            if family["family_id"] == "THERMOTEC_E_THERM":
                checks.insert(0, "Confirm adjacent reflective airspace and full assembly; no airspace or unknown airspace does not establish suitability.")
                reasons.append("Reflective airspace/assembly must be confirmed; catalogue range data is not installation evidence.")
                if re.search(r"\b(?:no airspace|no air space|without airspace)\b", text, re.I):
                    disposition = "REJECTED"
                    reasons.append("Customer states no reflective airspace; do not progress this candidate without a reviewed design change.")
            if source["source_gaps"]:
                reasons.extend(source["source_gaps"])
            candidates.append({
                "family_id": family["family_id"], "name": family["name"],
                "manufacturer": family.get("manufacturer", ""),
                "documented_role": family.get("primary_function", ""),
                "why_consider": "Catalogue element overlap (not a suitability finding): " + ", ".join(sorted(elements.intersection(family_elements(family)))),
                "disposition": disposition, "reasons": reasons, "operator_checks": checks,
                "evidence": source,
            })
            if len(candidates) == 4:
                break
        return {
            "schema_version": 1, "decision_status": "HUMAN_REVIEW_REQUIRED",
            "release_id": self.release["release_id"] if self.release else None,
            "delivery_status": "saved_locally_not_sent", "approval": None,
            "known_facts": {key: value for key, value in answers.items() if key != "name"},
            "capture_completeness": capture,
            "candidates": candidates,
            "no_candidate_reason": None if candidates else "No supported provisional family could be justified from this brief. Ask for application/outcome details; do not guess.",
            "operator_questions": [question(key, answers) for key in capture["unresolved_fields"]],
            "limits": "These are internal discovery candidates, not approved products, installation advice, prices, quantities or booked callbacks.",
        }
