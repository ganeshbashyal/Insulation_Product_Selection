"""Build one retrieval card per family -> data/processed/retrieval_cards.jsonl

A retrieval card is the single, clean, embedding-ready description of a family,
assembled from families.json metadata plus the (hygiene-cleaned) research JSON.
It is the unit the dense-retrieval channel embeds, and the grounding blob the
hosted LLM sees when phrasing an answer about a family. It carries the evidence
``confidence`` state so downstream consumers can respect the recommendation
gate, and a ``card_hash`` so embeddings rebuild only when content changes.

Usage:
    python scripts/build_retrieval_cards.py           # write the jsonl
    python scripts/build_retrieval_cards.py --stats   # also print field coverage
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrieval_hygiene import clean_retrieval, ranker_safe_terms

OUT_PATH = ROOT / "data" / "processed" / "retrieval_cards.jsonl"


def _slug(name: str) -> str:
    # must match the research filename convention (tds_research_agent.slugify)
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()[:60]


def _headline_specs(spec: dict, limit: int = 8) -> list[str]:
    """Pick the most decision-relevant technical lines from the researched spec."""
    out: list[str] = []
    for entry in spec.get("technical") or []:
        if not isinstance(entry, dict):
            continue
        prop = str(entry.get("property", "")).strip()
        value = str(entry.get("value", "")).strip()
        if prop and value:
            out.append(f"{prop}: {value}")
        if len(out) >= limit:
            break
    return out


def _merge_dedupe(*lists: list) -> list[str]:
    """Union of lists, case-insensitively deduped, keeping first-seen casing."""
    seen: set[str] = set()
    out: list[str] = []
    for terms in lists:
        for term in terms or []:
            key = str(term).casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(str(term))
    return sorted(out, key=str.casefold)


def build_card(mdir: str, family: dict, research: dict | None) -> dict:
    spec = (research or {}).get("spec") or {}
    if not isinstance(spec, dict):
        spec = {}
    retrieval = clean_retrieval((research or {}).get("retrieval") or {})

    keywords = _merge_dedupe(
        family.get("keywords", []),
        retrieval.get("search_keywords"),
        ranker_safe_terms(retrieval.get("problem_keywords")),
    )
    applications = _merge_dedupe(family.get("applications", []), retrieval.get("placement"))
    description = str(spec.get("description") or "").strip()
    rag_summary = str(retrieval.get("rag_summary") or "").strip()

    card = {
        "family_id": family["family_id"],
        "manufacturer": family.get("manufacturer", mdir.title()),
        "name": family["name"],
        "category": family.get("category", ""),
        "primary_function": family.get("primary_function", ""),
        "confidence": family.get("confidence", ""),
        "rag_summary": rag_summary,
        "description": description,
        "applications": applications,
        "keywords": keywords,
        "problem_keywords": retrieval.get("problem_keywords") or [],
        "use_cases": retrieval.get("use_cases") or [],
        "not_for": retrieval.get("not_for") or [],
        "priority_fit": retrieval.get("priority_fit") or [],
        "headline_specs": _headline_specs(spec),
        "source_url": family.get("source_url", ""),
    }

    # deterministic embedding text: identity, then what it is, where it goes,
    # what it solves, what it is not for
    lines = [f"{card['name']} — {card['manufacturer']} ({card['category']})"]
    if rag_summary:
        lines.append(rag_summary)
    elif description:
        lines.append(description)
    elif card["primary_function"]:
        lines.append(card["primary_function"])
    if applications:
        lines.append("Applications: " + "; ".join(applications))
    if card["problem_keywords"]:
        lines.append("Problems solved: " + "; ".join(card["problem_keywords"]))
    if card["use_cases"]:
        lines.append("Use cases: " + "; ".join(card["use_cases"]))
    if card["headline_specs"]:
        lines.append("Key specs: " + "; ".join(card["headline_specs"]))
    if card["not_for"]:
        lines.append("Not for: " + "; ".join(card["not_for"]))
    card["text"] = "\n".join(lines)
    card["card_hash"] = hashlib.sha256(card["text"].encode("utf-8")).hexdigest()[:16]
    return card


def build_all() -> list[dict]:
    cards = []
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        mdir = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        for family in data["families"]:
            research_file = path.parent / "research" / f"{_slug(family['name'])}.json"
            research = None
            if research_file.exists():
                try:
                    research = json.loads(research_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    research = None
            cards.append(build_card(mdir, family, research))
    return cards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    cards = build_all()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as handle:
        for card in cards:
            handle.write(json.dumps(card, ensure_ascii=False) + "\n")
    print(f"wrote {len(cards)} cards -> {OUT_PATH.relative_to(ROOT)}")

    if args.stats:
        def coverage(key):
            n = sum(1 for c in cards if c.get(key))
            return f"{n}/{len(cards)} ({n / len(cards):.0%})"
        for key in ("rag_summary", "description", "problem_keywords", "use_cases", "not_for", "headline_specs"):
            print(f"  {key:<18} {coverage(key)}")


if __name__ == "__main__":
    main()
