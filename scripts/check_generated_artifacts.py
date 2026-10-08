"""Fail when checked-in runtime artifacts do not match their local sources."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from construction_ingest import building_class
from scripts import build_aircall_pack
from scripts import build_compliance_chunks
from scripts import build_expert_training_data
from scripts import build_retrieval_cards


def _jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def _same_text(path: Path, expected: str) -> bool:
    return path.exists() and path.read_text(encoding="utf-8") == expected


def check(profile: str = "legacy") -> list[str]:
    if profile == "authoring":
        from knowledge_service import KnowledgeService
        reader = KnowledgeService(ROOT)
        idx = reader.index()
        errors = list(idx.errors)
        for key in idx.families:
            dossier = reader.family(key)["dossier"]
            if dossier["family_id"] != key or dossier["retained"]["family"]["family_id"] != key:
                errors.append(f"{key}: retained projection identity mismatch")
        return errors
    if profile != "legacy":
        raise ValueError("Artifact profile must be authoring or legacy")
    stale: list[str] = []

    retrieval = _jsonl(build_retrieval_cards.build_all())
    if not _same_text(build_retrieval_cards.OUT_PATH, retrieval):
        stale.append(
            "data/processed/retrieval_cards.jsonl "
            "(run: python scripts/build_retrieval_cards.py)"
        )

    compliance_rows = build_compliance_chunks.build()
    compliance_rows.sort(
        key=lambda row: (
            row["module_id"],
            row.get("page_start", 0),
            row["chunk_id"],
        )
    )
    if not _same_text(
        build_compliance_chunks.OUT_PATH, _jsonl(compliance_rows)
    ):
        stale.append(
            "knowledge/industry/training/compliance_rag_chunks.jsonl "
            "(run: python scripts/build_compliance_chunks.py)"
        )

    corpus = build_expert_training_data.load_json(
        build_expert_training_data.DEFAULT_CORPUS
    )
    expert_chunks = build_expert_training_data.build_rag_chunks(corpus)
    expert_pairs, _ = build_expert_training_data.build_finetune_pairs(
        corpus, include_legacy=True
    )
    training_dir = build_expert_training_data.DEFAULT_CORPUS.parent
    if not _same_text(
        training_dir / "expert_rag_chunks.jsonl", _jsonl(expert_chunks)
    ):
        stale.append(
            "knowledge/industry/training/expert_rag_chunks.jsonl "
            "(run: python scripts/build_expert_training_data.py)"
        )
    if not _same_text(
        training_dir / "expert_finetune.jsonl", _jsonl(expert_pairs)
    ):
        stale.append(
            "knowledge/industry/training/expert_finetune.jsonl "
            "(run: python scripts/build_expert_training_data.py "
            "--include-legacy-qa)"
        )

    profiles = building_class.load_profiles(building_class.DEFAULT_SOURCE)
    class_chunks = building_class.build_rag_chunks(profiles)
    class_chunk_path = (
        ROOT
        / "knowledge"
        / "industry"
        / "training"
        / "building_class_rag_chunks.jsonl"
    )
    if not _same_text(class_chunk_path, _jsonl(class_chunks)):
        stale.append(
            "knowledge/industry/training/building_class_rag_chunks.jsonl "
            "(run: python -m construction_ingest.building_class "
            "--export-training)"
        )

    families, evidence = build_aircall_pack.load_records()
    aircall_outputs = {
        ROOT / "aircall" / "aircall_knowledge_base.txt":
            build_aircall_pack.build_knowledge(families, evidence),
        ROOT / "aircall" / "aircall_agent_instructions.txt":
            build_aircall_pack.agent_instructions(),
        ROOT / "aircall" / "aircall_intake_questions.txt":
            build_aircall_pack.intake_questions(),
    }
    for path, expected in aircall_outputs.items():
        if not _same_text(path, expected):
            stale.append(
                f"{path.relative_to(ROOT)} "
                "(run: python scripts/build_aircall_pack.py)"
            )

    return stale


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["authoring", "legacy"], default="authoring")
    profile = parser.parse_args().profile
    stale = check(profile)
    if stale:
        print("Generated artifact drift detected:")
        for item in stale:
            print(f"- {item}")
        return 1
    print(f"{profile} projection checks passed; draft/legacy outputs are not reviewed release evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
