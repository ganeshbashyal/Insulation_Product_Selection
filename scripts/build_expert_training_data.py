"""Compile the Australian insulation expert corpus into machine-ingestible training data.

Reads the hand-verified structured corpus at
    knowledge/industry/training/expert_corpus.json
and emits three artifacts next to it (override with --out-dir):

  expert_finetune.jsonl   OpenAI/Ollama chat-format pairs (system/user/assistant),
                          matching the convention of training/qa_pairs.jsonl.
  expert_rag_chunks.jsonl One retrieval chunk per corpus record, with metadata
                          and a deterministic content hash (same style as
                          data/processed/retrieval_cards.jsonl).
  expert_training_report.json  Coverage/validation report (counts per module,
                          kind histogram, word counts, artifact paths).

Validation is always run first; the build aborts on errors (duplicate IDs,
missing fields, empty answers). Warnings (e.g. record without Q&A) are printed
and become fatal with --strict.

Stdlib only — no new dependencies.

Usage:
    python scripts/build_expert_training_data.py                 # validate + build
    python scripts/build_expert_training_data.py --include-legacy-qa   # merge qa_pairs.json
    python scripts/build_expert_training_data.py --validate-only
    python scripts/build_expert_training_data.py --strict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "knowledge" / "industry" / "training" / "expert_corpus.json"
LEGACY_QA = ROOT / "knowledge" / "industry" / "training" / "qa_pairs.json"

VALID_KINDS = {"fact", "rule", "procedure", "comparison", "mistake"}
REQUIRED_RECORD_FIELDS = ("id", "topic", "kind", "content", "key_points", "qa", "sources")


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate_corpus(corpus: dict, strict: bool) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    for field in ("corpus_id", "version", "system_persona", "modules"):
        if not corpus.get(field):
            errors.append(f"corpus missing top-level field: {field}")

    seen_ids: set[str] = set()
    seen_module_ids: set[str] = set()
    for module in corpus.get("modules", []):
        module_id = module.get("module_id")
        if not module_id:
            errors.append("module missing module_id")
            continue
        if module_id in seen_module_ids:
            errors.append(f"duplicate module_id: {module_id}")
        seen_module_ids.add(module_id)
        if not module.get("records"):
            warnings.append(f"module {module_id} has no records")

        for record in module.get("records", []):
            rid = record.get("id", "<no id>")
            for field in REQUIRED_RECORD_FIELDS:
                if field not in record:
                    errors.append(f"{module_id}/{rid}: missing field {field}")
            if rid in seen_ids:
                errors.append(f"duplicate record id: {rid}")
            seen_ids.add(rid)
            if record.get("kind") not in VALID_KINDS:
                errors.append(
                    f"{rid}: kind must be one of {sorted(VALID_KINDS)}, got {record.get('kind')!r}"
                )
            if len(str(record.get("content", "")).split()) < 50:
                warnings.append(f"{rid}: content is thin (<50 words)")
            if not record.get("qa"):
                warnings.append(f"{rid}: no Q&A pairs (contributes RAG chunk only)")
            for i, pair in enumerate(record.get("qa", [])):
                q, a = pair.get("question", ""), pair.get("answer", "")
                if not q.strip() or not a.strip():
                    errors.append(f"{rid}/qa[{i}]: empty question or answer")
                if len(a.split()) < 15:
                    warnings.append(f"{rid}/qa[{i}]: answer very short (<15 words)")
            if not record.get("sources"):
                warnings.append(f"{rid}: no sources recorded")

    if strict:
        errors.extend(warnings)
        warnings = []
    return errors, warnings


def chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_rag_chunks(corpus: dict) -> list[dict]:
    chunks = []
    for module in corpus["modules"]:
        for record in module["records"]:
            key_points = "; ".join(record["key_points"])
            text = (
                f"{record['topic']} — {module['title']}\n"
                f"{record['content']}\n"
                f"Key points: {key_points}"
            )
            chunks.append(
                {
                    "chunk_id": f"{record['id']}",
                    "module_id": module["module_id"],
                    "module_title": module["title"],
                    "topic": record["topic"],
                    "kind": record["kind"],
                    "text": text,
                    "key_points": record["key_points"],
                    "sources": record["sources"],
                    "chunk_hash": chunk_hash(text),
                }
            )
    return chunks


def build_finetune_pairs(corpus: dict, include_legacy: bool) -> tuple[list[dict], int]:
    """Return (jsonl-ready message dicts, number of legacy pairs merged)."""
    system = corpus["system_persona"]
    pairs: list[dict] = []
    seen_questions: set[str] = set()

    for module in corpus["modules"]:
        for record in module["records"]:
            for pair in record.get("qa", []):
                key = " ".join(pair["question"].lower().split())
                seen_questions.add(key)
                pairs.append(
                    {
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": pair["question"]},
                            {"role": "assistant", "content": pair["answer"]},
                        ],
                        "metadata": {
                            "record_id": record["id"],
                            "module_id": module["module_id"],
                            "origin": "expert_corpus",
                        },
                    }
                )

    legacy_merged = 0
    if include_legacy and LEGACY_QA.exists():
        legacy = load_json(LEGACY_QA)
        for pair in legacy.get("qa_pairs", []):
            key = " ".join(pair["question"].lower().split())
            if key in seen_questions:
                continue  # corpus answer wins on duplication
            seen_questions.add(key)
            pairs.append(
                {
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": pair["question"]},
                        {"role": "assistant", "content": pair["answer"]},
                    ],
                    "metadata": {
                        "record_id": None,
                        "module_id": pair.get("section", "legacy"),
                        "origin": "qa_pairs_v" + str(legacy.get("version", "?")),
                    },
                }
            )
            legacy_merged += 1
    return pairs, legacy_merged


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Defaults to the corpus directory")
    parser.add_argument("--include-legacy-qa", action="store_true",
                        help="Merge training/qa_pairs.json (deduped by question)")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors")
    args = parser.parse_args()

    corpus = load_json(args.corpus)
    errors, warnings = validate_corpus(corpus, args.strict)
    for warning in warnings:
        print(f"WARN  {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        print(f"\nValidation failed: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"Validation passed: {len(warnings)} warning(s)")
    if args.validate_only:
        return 0

    out_dir = args.out_dir or args.corpus.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = build_rag_chunks(corpus)
    pairs, legacy_merged = build_finetune_pairs(corpus, args.include_legacy_qa)

    rag_path = out_dir / "expert_rag_chunks.jsonl"
    ft_path = out_dir / "expert_finetune.jsonl"
    report_path = out_dir / "expert_training_report.json"
    write_jsonl(rag_path, chunks)
    write_jsonl(ft_path, pairs)

    modules = corpus["modules"]
    report = {
        "corpus_id": corpus["corpus_id"],
        "corpus_version": corpus["version"],
        "generated_by": "scripts/build_expert_training_data.py",
        "modules": [
            {
                "module_id": m["module_id"],
                "title": m["title"],
                "records": len(m["records"]),
                "qa_pairs": sum(len(r.get("qa", [])) for r in m["records"]),
                "words": sum(len(str(r["content"]).split()) for r in m["records"]),
            }
            for m in modules
        ],
        "totals": {
            "modules": len(modules),
            "records": sum(len(m["records"]) for m in modules),
            "qa_pairs_corpus": sum(len(r.get("qa", [])) for m in modules for r in m["records"]),
            "qa_pairs_legacy_merged": legacy_merged,
            "finetune_rows": len(pairs),
            "rag_chunks": len(chunks),
            "words": sum(len(str(r["content"]).split()) for m in modules for r in m["records"]),
        },
        "kind_histogram": dict(
            Counter(r["kind"] for m in modules for r in m["records"])
        ),
        "artifacts": {
            "finetune_jsonl": str(ft_path.relative_to(ROOT)),
            "rag_chunks_jsonl": str(rag_path.relative_to(ROOT)),
            "report": str(report_path.relative_to(ROOT)),
        },
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    totals = report["totals"]
    print(
        f"Built {totals['finetune_rows']} fine-tune rows "
        f"({totals['qa_pairs_corpus']} corpus + {legacy_merged} legacy), "
        f"{totals['rag_chunks']} RAG chunks, "
        f"{totals['words']} corpus words across {totals['modules']} modules."
    )
    print(f"  {ft_path.relative_to(ROOT)}")
    print(f"  {rag_path.relative_to(ROOT)}")
    print(f"  {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
