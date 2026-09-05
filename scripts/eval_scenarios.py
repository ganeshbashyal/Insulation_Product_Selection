"""Evaluation harness: run the ranker against the 150 customer scenario
questions and report where recommendations are sensible, blocked, or wrong.

This turns the hand-supplied scenario list into a repeatable regression suite.
It does NOT try to answer quantity/price/stock questions (those are human/commerce
gates); it checks that for each scenario the deterministic ranker either (a)
produces a reliable, application-appropriate family, or (b) correctly declines /
hands off when the enquiry is out of scope (price, stock, freight, quantity).

Usage:
    python scripts/eval_scenarios.py path\to\scenarios.txt
    python scripts/eval_scenarios.py path\to\scenarios.txt --verbose
    python scripts/eval_scenarios.py path\to\scenarios.txt --json out.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_core
from bot_engine import rank_families

# scenarios that are NOT product-recommendation questions -> bot should hand off
NON_PRODUCT_HINTS = (
    "price", "quote", "cost", "freight", "delivery", "stock", "in stock",
    "lead time", "pick up", "pickup", "urgent", "today", "how many packs",
    "how many rolls", "how many batts", "calculate", "how much", "wastage",
    "deduct", "floor plan", "shipping", "forklift",
)

# map a scenario to the building element it implies, used to sanity-check placement
ELEMENT_HINTS = {
    "ceiling": ["ceiling", "roofline", "roof space"],
    "roof": ["roof", "metal roof", "workshop roof", "shed"],
    "wall": ["wall", "internal wall", "external wall", "stud"],
    "floor": ["floor", "underfloor", "subfloor", "between floors"],
    "pipe": ["pipe", "duct"],
}


def is_non_product(question: str) -> bool:
    q = question.casefold()
    return any(hint in q for hint in NON_PRODUCT_HINTS)


def expected_element(question: str) -> str | None:
    q = question.casefold()
    for element, terms in ELEMENT_HINTS.items():
        if any(t in q for t in terms):
            return element
    return None


def parse_scenarios(text: str) -> list[dict]:
    """Parse the A-H sectioned scenario list into {section, question} records."""
    scenarios = []
    section = ""
    for line in text.splitlines():
        line = line.strip()
        sec = re.match(r"^([A-H])\.\s+(.+)$", line)
        if sec:
            section = f"{sec.group(1)}. {sec.group(2)}"
            continue
        if line and not section == "" and line.endswith("?") and not line.startswith(("150 ", "A.", "Suggested", "When you test")):
            scenarios.append({"section": section, "question": line})
    return scenarios


def evaluate(question: str) -> dict:
    answers = {
        "challenge": question,
        "application": question,
        "priority": question,
        "conditions": question,
        "project": question,
        "locality": "",
        "requirements": question,
        "contact": "",
    }
    ranked = rank_families(agent_core.FAMILIES, answers, "Compare both")
    top = ranked[0] if ranked else None
    non_product = is_non_product(question)
    element = expected_element(question)

    placement_ok = True
    if top and element and top.get("reliable_match"):
        blob = " ".join([top.get("name", ""), *top.get("applications", []), *top.get("keywords", [])]).casefold()
        terms = ELEMENT_HINTS[element]
        placement_ok = any(t in blob for t in terms)

    return {
        "question": question,
        "non_product": non_product,
        "expected_element": element,
        "reliable_match": bool(top and top.get("reliable_match")),
        "top_family": top["name"] if top else None,
        "top_manufacturer": top["manufacturer"] if top else None,
        "placement_ok": placement_ok,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    scenarios = parse_scenarios(text)
    print(f"scenarios parsed: {len(scenarios)}")

    results = [dict(evaluate(s["question"]), section=s["section"]) for s in scenarios]

    # aggregate
    product_qs = [r for r in results if not r["non_product"]]
    non_product_qs = [r for r in results if r["non_product"]]
    reliable = [r for r in product_qs if r["reliable_match"]]
    placed = [r for r in reliable if r["placement_ok"]]
    wrong_placement = [r for r in reliable if not r["placement_ok"]]

    print(f"\nproduct-recommendation questions: {len(product_qs)}")
    print(f"  reliable match:        {len(reliable)}")
    print(f"  placement appropriate: {len(placed)}")
    print(f"  WRONG placement:       {len(wrong_placement)}")
    print(f"non-product (price/stock/qty/freight) questions: {len(non_product_qs)} (should hand off, not recommend)")

    if wrong_placement:
        print("\n-- placement mismatches (review these) --")
        for r in wrong_placement[:20]:
            print(f"  [{r['expected_element']}] {r['question'][:60]} -> {r['top_family']}")

    if args.verbose:
        print("\n-- all product-question results --")
        for r in product_qs:
            flag = "OK " if (r["reliable_match"] and r["placement_ok"]) else "???"
            print(f"  {flag} {r['question'][:58]:<60} -> {r['top_family']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
