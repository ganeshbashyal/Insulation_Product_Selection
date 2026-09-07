"""Build the gold-label labeling template from real enquiry data.

Reads the (gitignored, PII-bearing) external enquiry dumps and produces
``data/local/gold_labels_todo.csv`` — one row per enquiry with the current
deterministic ranker's top-3 candidates prefilled. A sales engineer then fills
``gold_family_id`` (or a verdict) per row. The completed file becomes the
labelled enquiry set that IMPLEMENTATION_STATUS.md requires before embeddings
or any learned reranker may influence ranking, and the evaluation baseline for
LEARNING_MODEL_PLAN.md P1.

Everything here stays under data/local/ (gitignored): the source excerpts are
real customer communications and must never be committed.

Labelling convention per row (fill exactly one):
  gold_family_id   the correct family, when a family recommendation is right
  gold_verdict     'no_reliable_match'  (bot should decline and hand off)
                   'out_of_scope'       (price/stock/freight/quantity question)

Usage:
    python scripts/build_gold_label_template.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
from bot_engine import rank_families

DUMP_DIR = ROOT / "evidence" / "inbox" / "external-dump-2026-09-07"
OUT_PATH = ROOT / "data" / "local" / "gold_labels_todo.csv"


def load_structured_records() -> list[dict]:
    """The 42 structured thermal/acoustic enquiry records (JSONL)."""
    path = DUMP_DIR / "Thermal Acoustic BOt Training Dataset.txt"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = " ".join(
            [item.get("problem_summary", "")] + list(item.get("customer_asks") or [])
        ).strip()
        if not text:
            continue
        records.append({
            "source": "ta_dataset",
            "record_id": item.get("id", ""),
            "enquiry_text": text,
            "goal": item.get("goal", ""),
        })
    return records


def load_acoustic_enquiries() -> list[dict]:
    """The Top-200 real acoustic enquiry excerpts (CSV)."""
    path = DUMP_DIR / "Acoustic Enquiries Top 200.csv"
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            text = (row.get("enquiry_excerpt") or "").strip()
            if not text:
                continue
            records.append({
                "source": "acoustic_top200",
                "record_id": row.get("record_id", ""),
                "enquiry_text": text,
                "goal": "acoustic",
            })
    return records


def candidates_for(text: str) -> list[dict]:
    # long email excerpts make the ranker's fuzzy word-matching very slow and
    # add no signal past the opening lines — cap what we rank on
    text = text[:500]
    answers = {"problem": text, "application": "", "priority": "",
               "conditions": "", "project": "", "locality": "",
               "requirements": "", "contact": ""}
    return rank_families(agent_core.FAMILIES, answers, "Compare both")[:3]


def main() -> None:
    records = load_structured_records() + load_acoustic_enquiries()
    if not records:
        print(f"no source dumps found under {DUMP_DIR} — nothing to do")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source", "record_id", "enquiry_text", "goal",
        "candidate_1", "candidate_2", "candidate_3",
        "candidate_1_reliable",
        "gold_family_id", "gold_verdict", "labelled_by", "notes",
    ]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            ranked = candidates_for(record["enquiry_text"])
            writer.writerow({
                **record,
                "candidate_1": ranked[0]["family_id"] if ranked else "",
                "candidate_2": ranked[1]["family_id"] if len(ranked) > 1 else "",
                "candidate_3": ranked[2]["family_id"] if len(ranked) > 2 else "",
                "candidate_1_reliable": bool(ranked and ranked[0].get("reliable_match")),
                "gold_family_id": "", "gold_verdict": "", "labelled_by": "", "notes": "",
            })
    print(f"wrote {len(records)} rows -> {OUT_PATH.relative_to(ROOT)} (gitignored, stays local)")
    print("fill gold_family_id OR gold_verdict per row; 'labelled_by' must name the reviewer")


if __name__ == "__main__":
    main()
