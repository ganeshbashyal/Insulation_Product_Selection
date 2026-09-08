"""Evaluate knowledge retrieval over the ingested building-class corpus.

Builds an evaluation set directly from the ingested profiles: each construction
stage yields a question whose known-correct chunk is that stage's chunk. This
gives a ground truth without any hand labelling, so retrieval quality can be
measured today rather than waiting on the gold-label enquiry set.

Everything runs locally: embeddings and generation both go to the local Ollama
instance, and nothing leaves the machine.

Reports recall@k and MRR for retrieval, and optionally grounding checks on
generated answers.

Usage:
    python scripts/eval_knowledge_retrieval.py
    python scripts/eval_knowledge_retrieval.py --with-answers --limit 15
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag_answerer import RAGAnswerer  # noqa: E402

REPORT_PATH = ROOT / "data" / "local" / "knowledge_eval_report.json"


def build_eval_set(answerer: RAGAnswerer, seed: int = 7) -> list[dict]:
    """Derive questions whose correct chunk is known from the chunk metadata."""
    cases: list[dict] = []
    for index, chunk in enumerate(answerer.knowledge_chunks):
        topic = chunk.get("topic")
        if not topic:
            continue

        if chunk.get("kind") == "construction_stage" and chunk.get("stage_name"):
            building = topic.split(" - ")[0]
            question = (
                f"During {chunk['stage_name']}, what insulation or membrane "
                f"is installed in a {building}?"
            )
        elif chunk.get("kind") == "overview":
            question = f"What are the construction stages for a {topic}?"
        else:
            continue

        cases.append(
            {
                "question": question,
                "expected_index": index,
                "topic": topic,
                "kind": chunk.get("kind"),
                "classes": chunk.get("building_class_codes", []),
            }
        )

    random.Random(seed).shuffle(cases)
    return cases


def evaluate_retrieval(answerer: RAGAnswerer, cases: list[dict], top_k: int) -> dict:
    index_of = {id(chunk): i for i, chunk in enumerate(answerer.knowledge_chunks)}
    hits_at_1 = hits_at_k = 0
    reciprocal_total = 0.0
    failures: list[dict] = []

    for case in cases:
        ranked = answerer._rank_chunks(case["question"], top_k=top_k)
        positions = [index_of.get(id(chunk), -1) for chunk in ranked]

        if case["expected_index"] in positions:
            rank = positions.index(case["expected_index"])
            hits_at_k += 1
            reciprocal_total += 1.0 / (rank + 1)
            if rank == 0:
                hits_at_1 += 1
        else:
            top = answerer.knowledge_chunks[positions[0]] if positions and positions[0] >= 0 else {}
            failures.append(
                {
                    "question": case["question"],
                    "expected_topic": case["topic"],
                    "got_topic": top.get("topic", "?"),
                }
            )

    total = len(cases) or 1
    return {
        "cases": len(cases),
        "top_k": top_k,
        "recall_at_1": round(hits_at_1 / total, 4),
        f"recall_at_{top_k}": round(hits_at_k / total, 4),
        "mrr": round(reciprocal_total / total, 4),
        "failures": failures[:20],
    }


def evaluate_answers(answerer: RAGAnswerer, cases: list[dict]) -> dict:
    """Check generated answers are produced, cited, and free of LaTeX artefacts."""
    generated = cited = latex_free = 0
    samples: list[dict] = []
    latency: list[float] = []

    for case in cases:
        started = time.monotonic()
        result = answerer.answer(case["question"])
        latency.append(time.monotonic() - started)
        text = result.get("answer", "")

        is_generated = bool(text) and not text.startswith("Retrieved ")
        if is_generated:
            generated += 1
            if "](" in text:
                cited += 1
            if "\\" not in text and "$" not in text:
                latex_free += 1

        if len(samples) < 5:
            samples.append({"question": case["question"], "answer": text[:400]})

    total = len(cases) or 1
    return {
        "cases": len(cases),
        "generated_rate": round(generated / total, 4),
        "cited_rate": round(cited / total, 4),
        "latex_free_rate": round(latex_free / total, 4),
        "mean_latency_s": round(sum(latency) / total, 2),
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=0, help="cap the number of cases (0 = all)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--with-answers",
        action="store_true",
        help="also generate answers via local Ollama (much slower)",
    )
    parser.add_argument("--answer-limit", type=int, default=10)
    args = parser.parse_args()

    print("loading knowledge base and embeddings (local Ollama)...")
    answerer = RAGAnswerer()
    print(f"  {len(answerer.knowledge_chunks)} chunks, {len(answerer.embeddings)} embeddings")
    if not answerer.embeddings:
        print("  warning: no embeddings; retrieval will fall back to keyword overlap")

    cases = build_eval_set(answerer)
    if args.limit:
        cases = cases[: args.limit]
    print(f"  {len(cases)} evaluation cases derived from the corpus\n")

    print("evaluating retrieval...")
    retrieval = evaluate_retrieval(answerer, cases, args.top_k)
    print(f"  recall@1  : {retrieval['recall_at_1']:.1%}")
    print(f"  recall@{args.top_k}  : {retrieval[f'recall_at_{args.top_k}']:.1%}")
    print(f"  MRR       : {retrieval['mrr']:.4f}")

    report = {"retrieval": retrieval}

    if args.with_answers:
        subset = cases[: args.answer_limit]
        print(f"\ngenerating {len(subset)} answers via local Ollama...")
        answers = evaluate_answers(answerer, subset)
        print(f"  generated : {answers['generated_rate']:.1%}")
        print(f"  cited     : {answers['cited_rate']:.1%}")
        print(f"  latex-free: {answers['latex_free_rate']:.1%}")
        print(f"  latency   : {answers['mean_latency_s']:.2f}s mean")
        report["answers"] = answers

    if retrieval["failures"]:
        print("\nretrieval misses (first 5):")
        for failure in retrieval["failures"][:5]:
            print(f"  - {failure['question'][:70]}")
            print(f"      expected: {failure['expected_topic'][:60]}")
            print(f"      got     : {failure['got_topic'][:60]}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nreport written to {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
