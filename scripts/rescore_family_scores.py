"""Re-score auto-generated product families using classification-aware scoring.

The first deep-dive pass scored families by physical form alone (every "batt"
received energy_efficiency 5), so manufacturer-classified acoustic products
outranked genuine thermal products on thermal enquiries. This script applies
scripts/family_scoring.classify_scores to every family whose scores were
machine-generated (score_notes starting with "Deep-dive scoring"), updates
knowledge/<manufacturer>/families.json, and patches the matching lines in the
family's markdown doc (front matter priority_*_score and the ratings table).

Hand-curated families (Thermotec benchmark, Fletcher, and any family with a
custom score_notes) are left untouched.

Usage:
    python scripts/rescore_family_scores.py --dry-run   # report only
    python scripts/rescore_family_scores.py             # apply changes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from family_scoring import classify_scores

RESCORE_NOTE = (
    " Re-scored 2026-09-05 by scripts/rescore_family_scores.py using classification "
    "signals (manufacturer name/applications) instead of physical form alone."
)

SCORE_TO_FRONTMATTER = {
    "sustainability": "priority_sustainability_score",
    "energy_efficiency": "priority_energy_efficiency_score",
    "acoustic_comfort": "priority_acoustic_comfort_score",
    "installation_practicality": "priority_installation_practicality_score",
}
SCORE_TO_TABLE_ROW = {
    "sustainability": "Sustainability",
    "energy_efficiency": "Energy efficiency",
    "acoustic_comfort": "Acoustic comfort",
    "installation_practicality": "Installation practicality",
}


def patch_markdown(md_path: Path, scores: dict, dry_run: bool) -> bool:
    if not md_path.exists():
        return False
    text = md_path.read_text(encoding="utf-8")
    original = text
    for key, value in scores.items():
        if key not in SCORE_TO_FRONTMATTER:
            continue
        fm_key = SCORE_TO_FRONTMATTER[key]
        text = re.sub(rf"(?m)^{fm_key}: \d+", f"{fm_key}: {value}", text)
        row_label = SCORE_TO_TABLE_ROW[key]
        text = re.sub(rf"(?m)^\| {row_label} \| \d+/5", f"| {row_label} | {value}/5", text)
    if text != original and not dry_run:
        md_path.write_text(text, encoding="utf-8")
    return text != original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed_families = 0
    patched_docs = 0
    skipped_manual = 0
    unchanged = 0

    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for family in data["families"]:
            notes = family.get("score_notes", "")
            if not notes.startswith("Deep-dive scoring"):
                skipped_manual += 1
                continue
            new_scores = classify_scores(
                family.get("category", ""),
                name=family.get("name", ""),
                applications=family.get("applications", []),
                keywords=family.get("keywords", []),
            )
            if new_scores == family.get("scores"):
                unchanged += 1
                continue
            changed_families += 1
            print(
                f"{path.parent.name:<22} {family['name'][:55]:<57} "
                f"{family['scores']} -> {new_scores}"
            )
            md_path = path.parent / family.get("knowledge_file", "")
            if patch_markdown(md_path, new_scores, dry_run=args.dry_run):
                patched_docs += 1
            if args.dry_run:
                continue
            family["scores"] = new_scores
            if RESCORE_NOTE.strip() not in notes:
                family["score_notes"] = notes.rstrip() + RESCORE_NOTE
            dirty = True
        if dirty and not args.dry_run:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"families re-scored: {changed_families}")
    print(f"markdown docs patched: {patched_docs}")
    print(f"unchanged (already classification-consistent): {unchanged}")
    print(f"skipped (hand-curated score_notes): {skipped_manual}")
    if args.dry_run:
        print("dry run - no files written")


if __name__ == "__main__":
    main()
