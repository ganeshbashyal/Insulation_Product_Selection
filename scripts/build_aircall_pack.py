"""Publish curated Aircall trial content from the approved family catalogue."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot_engine import recommendation_allowed  # noqa: E402

CATALOGUE_PATHS = [
    ROOT / "knowledge" / "thermotec" / "families.json",
    ROOT / "knowledge" / "fletcher" / "families.json",
]
EVIDENCE_PATH = ROOT / "knowledge" / "performance_evidence.json"


def load_records() -> tuple[list[dict], dict[str, dict]]:
    families: list[dict] = []
    for path in CATALOGUE_PATHS:
        manufacturer = path.parent.name.title()
        for family in json.loads(path.read_text(encoding="utf-8"))["families"]:
            families.append({**family, "manufacturer": family.get("manufacturer", manufacturer)})
    evidence = {
        item["family_id"]: item
        for item in json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))["families"]
    }
    return families, evidence


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def metric_line(item: dict) -> str:
    value = f"{item['value']} {item['unit']}".strip()
    return f"- {item['metric_type']}: {value}; variant: {item['variant']}; scope: {item['scope']}; context: {item['test_context']}"


def build_knowledge(families: list[dict], evidence: dict[str, dict]) -> str:
    enabled = sorted((family for family in families if recommendation_allowed(family)), key=lambda item: (item["manufacturer"], item["name"]))
    blocked = sorted((family for family in families if not recommendation_allowed(family)), key=lambda item: (item["manufacturer"], item["name"]))
    lines = [
        "INSULATION PRODUCT KNOWLEDGE — AIRCALL TRIAL",
        "",
        "Purpose: help qualify enquiries and identify a suitable supported product family for human review.",
        "This material does not authorise exact SKU, grade, thickness, quantity, price or compliance selection.",
        "R-value, Rw and NRC/alpha-w are different metrics and must never be substituted for one another.",
        "A product or material rating is not the rating of the completed wall, floor, ceiling, roof or service system.",
        "",
        "SUPPORTED PRODUCT FAMILIES",
    ]
    for family in enabled:
        record = evidence[family["family_id"]]
        verified = [item for item in record["evidence_items"] if item["evidence_status"] == "verified"]
        lines.extend([
            "",
            f"## {family['manufacturer']} — {family['name']}",
            f"Reference ID: {family['family_id']}",
            f"Product role: {family['primary_function']}",
            f"Typical applications: {', '.join(family['applications'])}.",
            f"Useful customer language: {', '.join(family['keywords'])}.",
            f"Selection guidance: {family['score_notes']}",
            "Before suggesting this family, clarify:",
            *[f"- {question}" for question in family["questions"]],
            "Mandatory checks before quote or order:",
            *[f"- {gate}" for gate in family["human_gates"]],
        ])
        if verified:
            lines.append("Approved structured performance evidence:")
            lines.extend(metric_line(item) for item in verified)
        else:
            lines.append("Approved structured performance evidence: no numerical claim is approved for voice use yet. Discuss product role only and arrange human review.")
        lines.extend([
            f"Primary product source: {family['source_url']}",
            f"Safe wording: {family['name']} may suit this application at product-family level. Our team must confirm the construction, exact product and project requirements before quoting.",
        ])

    lines.extend([
        "",
        "PRODUCTS THAT MUST NOT BE RECOMMENDED",
        "These names may be recognised if a caller asks about them, but their identity or primary evidence is unresolved. Say that the product record requires technical review and arrange a callback.",
    ])
    lines.extend(f"- {family['manufacturer']} — {family['name']} ({family['family_id']})" for family in blocked)
    lines.extend([
        "",
        "UNIVERSAL ESCALATION",
        "Arrange human technical review for NCC, fire, BAL, consultant specifications, target R/Rw/NRC/alpha-w values, high temperatures, condensation risk, exterior exposure, sensitive buildings, guarantees or installed-performance questions.",
        "Do not say that a product makes a project compliant. Do not invent availability, price, stock, lead time or performance.",
    ])
    return "\n".join(lines).strip() + "\n"


def agent_instructions() -> str:
    return """AIRCALL TRIAL — AGENT GOAL AND CONVERSATION RULES

Goal
Qualify insulation enquiries, give a short product-family suggestion only when the supplied knowledge explicitly supports it, and arrange human review before any SKU or quote decision.

Style
- Sound natural, warm and concise.
- Ask one question at a time.
- Normally reply in one to three short sentences.
- Do not repeatedly say “I noted that” or restate the caller’s answer.
- Do not use technical jargon unless the caller uses it or asks for an explanation.

Four intake topics
1. What are they trying to improve: heat, cold, noise, condensation or general comfort?
2. Where will insulation go? Distinguish external/internal wall; ceiling level versus roofline/rafters/trusses; suspended subfloor versus between storeys versus directly below floor finish; and pipe/duct service.
3. What is the project type, construction, access constraint, exposure and suburb/postcode?
4. What matters most, and is there a known NCC, BAL, fire, acoustic, thermal or consultant requirement?

Decision rule
- A supported family may be described as the best apparent family-level fit during this trial when the application clearly matches.
- Never select a SKU, thickness, density, facing, grade, quantity or installed system.
- Never claim compliance or guarantee performance.
- If evidence is absent, pending, conflicting or blocked, do not recommend the product. Arrange a callback.
- For roof and floor enquiries, do not ask where the issue is again after the caller has already identified it; ask for the unresolved placement/construction detail.

Close
Offer a human transfer or callback. Capture the caller’s preferred option and a concise reason for technical review.
"""


def intake_questions() -> str:
    return """AIRCALL TRIAL — INTAKE CONFIGURATION

1. What would you like to improve—noise, heat, condensation or general comfort?
2. Where will the insulation sit, and what is the surrounding construction?
3. What type of project is it, what suburb/postcode is it in, and are there access or exposure constraints?
4. What matters most, and do you know of any NCC, BAL, fire, thermal, acoustic or consultant requirement?

After intake, offer a transfer or callback. Do not request information the caller has already supplied.
"""


def publish(output_dir: Path) -> dict:
    families, evidence = load_records()
    knowledge = build_knowledge(families, evidence)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "knowledge_base": output_dir / "aircall_knowledge_base.txt",
        "agent_instructions": output_dir / "aircall_agent_instructions.txt",
        "intake_questions": output_dir / "aircall_intake_questions.txt",
    }
    files["knowledge_base"].write_text(knowledge, encoding="utf-8")
    files["agent_instructions"].write_text(agent_instructions(), encoding="utf-8")
    files["intake_questions"].write_text(intake_questions(), encoding="utf-8")
    enabled = [family for family in families if recommendation_allowed(family)]
    manifest = {
        "schema_version": "1.0",
        "generated_on": date.today().isoformat(),
        "source_sha256": source_hash([*CATALOGUE_PATHS, EVIDENCE_PATH]),
        "total_families": len(families),
        "recommendation_eligible_families": len(enabled),
        "blocked_families": len(families) - len(enabled),
        "knowledge_characters": len(knowledge),
        "aircall_context_threshold": 300000,
        "files": {name: path.name for name, path in files.items()},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "aircall")
    args = parser.parse_args()
    print(json.dumps(publish(args.output_dir)))


if __name__ == "__main__":
    main()
