"""Verify that the generated Aircall pack matches the governed catalogue."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_aircall_pack import CATALOGUE_PATHS, EVIDENCE_PATH, load_records, source_hash  # noqa: E402
from bot_engine import recommendation_allowed


def validate() -> list[str]:
    errors: list[str] = []
    directory = ROOT / "aircall"
    knowledge_path = directory / "aircall_knowledge_base.txt"
    manifest_path = directory / "manifest.json"
    for path in [knowledge_path, directory / "aircall_agent_instructions.txt", directory / "aircall_intake_questions.txt", manifest_path]:
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"missing or empty Aircall file: {path.relative_to(ROOT)}")
    if errors:
        return errors
    knowledge = knowledge_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    families, _ = load_records()
    enabled = [family for family in families if recommendation_allowed(family)]
    blocked = [family for family in families if not recommendation_allowed(family)]
    if len(knowledge) >= 300000:
        errors.append("Aircall knowledge exceeds the documented context threshold")
    if manifest.get("source_sha256") != source_hash([*CATALOGUE_PATHS, EVIDENCE_PATH]):
        errors.append("Aircall manifest is stale relative to catalogue/evidence sources")
    if manifest.get("recommendation_eligible_families") != len(enabled) or manifest.get("blocked_families") != len(blocked):
        errors.append("Aircall manifest family counts are stale")
    supported_section, blocked_section = knowledge.split("PRODUCTS THAT MUST NOT BE RECOMMENDED", 1)
    for family in enabled:
        if family["family_id"] not in supported_section:
            errors.append(f"eligible family missing from supported section: {family['family_id']}")
    for family in blocked:
        if family["family_id"] in supported_section:
            errors.append(f"blocked family leaked into supported section: {family['family_id']}")
        if family["family_id"] not in blocked_section:
            errors.append(f"blocked family missing from recognition list: {family['family_id']}")
    return errors


if __name__ == "__main__":
    issues = validate()
    if issues:
        print("Aircall pack validation failed:")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)
    print("Aircall pack validation passed.")
