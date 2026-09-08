"""Evaluate hybrid ranking against gold labels.

Compares lexical-only baseline vs hybrid (lexical + dense) ranking on the
gold-label enquiry set. Generates:
  - data/local/eval_results_lexical.csv
  - data/local/eval_results_hybrid.csv
  - data/local/eval_report.txt (summary stats)

Labels can be real (from `data/local/gold_labels_todo.csv`) or synthetic
(current ranker's top-1 as a stand-in for testing infrastructure).

Usage:
    python scripts/eval_hybrid_baseline.py              # eval on real labels (if any filled)
    python scripts/eval_hybrid_baseline.py --synthetic  # eval on synthetic labels
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
from bot_engine import rank_families
from hybrid_retrieval import load_or_embed_cards, hybrid_rank


def load_retrieval_cards() -> list[dict]:
    """Load the 283 retrieval cards."""
    cards = []
    with open(ROOT / "data" / "processed" / "retrieval_cards.jsonl", encoding="utf-8") as f:
        cards = [json.loads(l) for l in f if l.strip()]
    return cards


def load_gold_labels() -> list[dict] | None:
    """Load real gold labels from CSV if any are filled. Return None if none are filled."""
    path = ROOT / "data" / "local" / "gold_labels_todo.csv"
    if not path.exists():
        return None
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    filled = [r for r in rows if r.get("gold_family_id") or r.get("gold_verdict")]
    return filled if filled else None


def synthetic_labels(n: int = 240) -> list[dict]:
    """Generate synthetic labels: current ranker's top-1 pick for each enquiry."""
    cards = load_retrieval_cards()
    labels = []
    for i, card in enumerate(cards[:n]):
        # Use the card's text as the synthetic enquiry
        text = card.get("text", "")[:500]
        if not text:
            continue
        # Get current ranker's top-1
        ranked = rank_families(agent_core.FAMILIES, {
            "problem": text, "application": "", "priority": "",
            "conditions": "", "project": "", "locality": "",
            "requirements": "", "contact": "",
        }, "Compare both")
        top_fid = ranked[0]["family_id"] if ranked else None
        labels.append({
            "enquiry_text": text,
            "gold_family_id": top_fid or "",
            "gold_verdict": "no_reliable_match" if not ranked[0].get("reliable_match") else "",
            "source": "synthetic_from_ranker",
        })
    return labels


def eval_ranker(ranker_name: str, ranker_fn, labels: list[dict], embeddings: dict) -> dict:
    """Evaluate one ranker (lexical or hybrid). Returns accuracy stats."""
    hits_1 = hits_3 = mrr = count_valid = 0
    for label in labels:
        text = label["enquiry_text"]
        gold_fid = label.get("gold_family_id", "").strip()
        if not gold_fid or gold_fid == "no_reliable_match":
            continue  # skip verdicts, evaluate only product-fit labels
        count_valid += 1
        if ranker_name == "lexical":
            ranked = ranker_fn(agent_core.FAMILIES, {
                "problem": text, "application": "", "priority": "",
                "conditions": "", "project": "", "locality": "",
                "requirements": "", "contact": "",
            }, "Compare both")
        else:  # hybrid
            ranked = ranker_fn(text, agent_core.FAMILIES, embeddings)
        ranked_ids = [f["family_id"] for f in ranked[:3]]
        if gold_fid in ranked_ids:
            hits_1 += 1 if gold_fid == ranked_ids[0] else 0
            hits_3 += 1
            mrr += 1.0 / (ranked_ids.index(gold_fid) + 1)
    if count_valid == 0:
        return {"ranker": ranker_name, "evaluated": 0}
    return {
        "ranker": ranker_name,
        "evaluated": count_valid,
        "precision_1": round(hits_1 / count_valid, 3),
        "precision_3": round(hits_3 / count_valid, 3),
        "mrr": round(mrr / count_valid, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true", help="use synthetic labels (current ranker's picks)")
    args = parser.parse_args()

    print("Loading retrieval cards and embeddings (this may take a few minutes if Ollama is warming up)...")
    cards = load_retrieval_cards()
    embeddings, _ = load_or_embed_cards(cards)

    if args.synthetic:
        labels = synthetic_labels(len(cards))
        print(f"Using {len(labels)} synthetic labels (current ranker's top-1)")
    else:
        labels = load_gold_labels()
        if not labels:
            print("No gold labels filled yet. Use --synthetic for testing infrastructure, or fill gold_labels_todo.csv")
            return

    print(f"Evaluating on {len(labels)} enquiries...\n")

    # Eval lexical baseline
    lex_result = eval_ranker("lexical", rank_families, labels, embeddings)
    print(f"Lexical:  {lex_result}")

    # Eval hybrid
    hybrid_result = eval_ranker("hybrid", hybrid_rank, labels, embeddings)
    print(f"Hybrid:   {hybrid_result}\n")

    # Report improvement
    if lex_result.get("evaluated") and hybrid_result.get("evaluated"):
        lex_p1 = lex_result.get("precision_1", 0)
        hyb_p1 = hybrid_result.get("precision_1", 0)
        improvement = ((hyb_p1 - lex_p1) / max(lex_p1, 0.001)) * 100 if lex_p1 > 0 else 0
        print(f"Improvement (precision@1): {improvement:+.1f}%\n")

    # Write results
    (ROOT / "data" / "local").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "data" / "local" / "eval_report.txt", "w") as f:
        f.write(f"Lexical baseline:\n{lex_result}\n\n")
        f.write(f"Hybrid (RRF):\n{hybrid_result}\n")
    print(f"Report written to data/local/eval_report.txt")


if __name__ == "__main__":
    main()
