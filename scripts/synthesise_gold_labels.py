"""Validate and synthesise the hand-labelled gold CSV into training artifacts.

Reads data/local/gold_labels_todo.csv, checks every label against the real
product catalogue, parses the structured `notes` prose into fields, and emits:

  data/local/gold_labels.validated.jsonl   one record per labelled row
  data/local/gold_labels_rationale.jsonl   chat-format pairs for the rationale
  data/local/gold_labels_report.json       validation + coverage report

Everything is local: no network, no cloud APIs. Run --validate-only while
labelling to catch mistakes early.

    python scripts/synthesise_gold_labels.py --validate-only
    python scripts/synthesise_gold_labels.py
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_CSV = ROOT / "data" / "local" / "gold_labels_todo.csv"
CARDS = ROOT / "data" / "processed" / "retrieval_cards.jsonl"
OUT_DIR = ROOT / "data" / "local"

VALID_VERDICTS = {"no_reliable_match", "ambiguous", "out_of_scope"}

# The `notes` column is written as "Intent: ... Reasoning: ... Decision: ..."
# Captured so the reasoning becomes training signal rather than dead prose.
NOTE_SECTIONS = [
    "Intent",
    "Reasoning",
    "Decision",
    "Candidate assessment",
    "Constraints",
]

RATIONALE_SYSTEM = (
    "You are an Australian insulation product specialist. Given a customer "
    "enquiry, identify the intended application and recommend a product family, "
    "explaining your reasoning. Never assert NCC compliance; compliance is "
    "determined by the project's certifier."
)


def load_family_ids() -> set[str]:
    if not CARDS.exists():
        raise SystemExit(f"missing catalogue: {CARDS}")
    ids = set()
    with open(CARDS, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ids.add(json.loads(line)["family_id"])
    return ids


def parse_notes(notes: str) -> dict[str, str]:
    """Split the structured note prose into its labelled sections."""
    notes = (notes or "").strip()
    if not notes:
        return {}
    pattern = "|".join(re.escape(s) for s in NOTE_SECTIONS)
    matches = list(re.finditer(rf"\b({pattern})\s*:\s*", notes))
    if not matches:
        return {"Reasoning": notes}
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(notes)
        key = match.group(1).strip()
        out[key] = notes[match.end():end].strip()
    return out


def split_ids(raw: str) -> list[str]:
    """Gold may name more than one acceptable family, separated by ; or |."""
    return [p.strip() for p in re.split(r"[;|]", raw or "") if p.strip()]


def validate_row(row: dict, index: int, valid_ids: set[str]) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    rid = (row.get("record_id") or f"row{index}").strip()
    gold_raw = (row.get("gold_family_id") or "").strip()
    verdict = (row.get("gold_verdict") or "").strip()
    enquiry = (row.get("enquiry_text") or "").strip()
    notes = (row.get("notes") or "").strip()

    if not gold_raw and not verdict:
        return None, []  # genuinely unlabelled, not an error

    # Labels are typed by hand, so accept any casing and repair it silently
    # rather than failing on "UNderFloor_Rolls_PolyFB".
    by_upper = {i.upper(): i for i in valid_ids}
    gold_ids = []
    for fid in split_ids(gold_raw):
        canonical = by_upper.get(fid.upper())
        if canonical:
            gold_ids.append(canonical)
            continue
        near = difflib.get_close_matches(fid.upper(), list(by_upper), n=3, cutoff=0.5)
        suggestions = [by_upper[n] for n in near]
        if not suggestions:
            tokens = {t for t in fid.upper().split("_") if len(t) > 3}
            suggestions = sorted(
                i for i in valid_ids
                if tokens and len(tokens & set(i.upper().split("_"))) >= 2
            )[:3]
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        errors.append(f"{rid}: unknown family_id {fid!r}.{hint}")
        gold_ids.append(fid)

    if verdict and verdict not in VALID_VERDICTS:
        errors.append(
            f"{rid}: gold_verdict {verdict!r} not one of {sorted(VALID_VERDICTS)}"
        )
    if gold_ids and verdict:
        errors.append(f"{rid}: has both gold_family_id and gold_verdict; pick one")
    if not enquiry:
        errors.append(f"{rid}: labelled but enquiry_text is empty")

    sections = parse_notes(notes)

    # A Decision naming several products but only one gold id will score the
    # ranker wrong for returning a family the note itself endorses.
    warnings: list[str] = []
    if len(gold_ids) == 1 and sections:
        prose = " ".join(sections.get(k, "") for k in ("Decision", "Alternative", "Constraints"))
        named = {
            by_upper[m.group(0).upper()]
            for m in re.finditer(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+", prose)
            if m.group(0).upper() in by_upper
        }
        extra = named - set(gold_ids)
        if extra:
            warnings.append(
                f"{rid}: notes also name {', '.join(sorted(extra))} but only "
                f"{gold_ids[0]} is labelled - consider 'a; b' multi-answer"
            )

    record = {
        "record_id": rid,
        "source": (row.get("source") or "").strip(),
        "enquiry_text": enquiry,
        "goal": (row.get("goal") or "").strip(),
        "gold_family_ids": gold_ids,
        "gold_family_id": gold_ids[0] if gold_ids else "",
        "gold_verdict": verdict,
        "multi_answer": len(gold_ids) > 1,
        "candidates": [
            (row.get(f"candidate_{i}") or "").strip() for i in (1, 2, 3)
        ],
        "candidate_1_reliable": (row.get("candidate_1_reliable") or "").strip(),
        "labelled_by": (row.get("labelled_by") or "").strip(),
        "notes": notes,
        "rationale": sections,
        "warnings": warnings,
    }
    return record, errors


def build_rationale_pairs(records: list[dict]) -> list[dict]:
    """Chat-format pairs teaching the reasoning, not just the answer."""
    pairs = []
    for rec in records:
        sections = rec.get("rationale") or {}
        if not sections.get("Decision") and not rec["gold_family_ids"]:
            continue
        parts = []
        for key in ("Intent", "Reasoning", "Decision", "Candidate assessment", "Constraints"):
            if sections.get(key):
                parts.append(f"{key}: {sections[key]}")
        if not parts:
            continue
        if rec["gold_family_ids"]:
            parts.append("Recommended family: " + ", ".join(rec["gold_family_ids"]))
        elif rec["gold_verdict"]:
            parts.append(f"Verdict: {rec['gold_verdict']}")
        pairs.append({
            "messages": [
                {"role": "system", "content": RATIONALE_SYSTEM},
                {"role": "user", "content": rec["enquiry_text"]},
                {"role": "assistant", "content": "\n".join(parts)},
            ],
            "record_id": rec["record_id"],
        })
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate-only", action="store_true",
                        help="check the CSV without writing outputs")
    parser.add_argument("--csv", type=Path, default=GOLD_CSV)
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"missing gold CSV: {args.csv}")

    valid_ids = load_family_ids()
    with open(args.csv, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    records: list[dict] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=1):
        record, row_errors = validate_row(row, i, valid_ids)
        errors.extend(row_errors)
        if record:
            records.append(record)

    labelled = len(records)
    with_fid = sum(1 for r in records if r["gold_family_ids"])
    verdicts = sum(1 for r in records if r["gold_verdict"])
    multi = sum(1 for r in records if r["multi_answer"])
    with_notes = sum(1 for r in records if r["rationale"])
    agree = sum(
        1 for r in records
        if r["gold_family_id"] and r["candidates"] and r["gold_family_id"] == r["candidates"][0]
    )

    print(f"rows: {len(rows)}  labelled: {labelled}  unlabelled: {len(rows) - labelled}")
    print(f"  with family_id: {with_fid}   verdicts: {verdicts}   multi-answer: {multi}")
    print(f"  with structured notes: {with_notes}")
    if with_fid:
        print(f"  gold == current candidate_1: {agree}/{with_fid} ({agree / with_fid:.1%})")
    counts = Counter(f for r in records for f in r["gold_family_ids"])
    if counts:
        top = ", ".join(f"{k}({v})" for k, v in counts.most_common(5))
        print(f"  most-labelled families: {top}")

    if errors:
        print(f"\n{len(errors)} problem(s):")
        for err in errors:
            print(f"  - {err}")

    warnings = [w for r in records for w in r.get("warnings", [])]
    if warnings:
        print(f"\n{len(warnings)} warning(s) - review, these do not block:")
        for warn in warnings:
            print(f"  - {warn}")

    report = {
        "rows": len(rows),
        "labelled": labelled,
        "with_family_id": with_fid,
        "verdicts": verdicts,
        "multi_answer": multi,
        "with_structured_notes": with_notes,
        "gold_matches_candidate_1": agree,
        "warnings": warnings,
        "family_distribution": dict(counts),
        "errors": errors,
    }

    if args.validate_only:
        print("\nvalidate-only: no files written")
        return 1 if errors else 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "gold_labels.validated.jsonl", "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")

    pairs = build_rationale_pairs(records)
    with open(OUT_DIR / "gold_labels_rationale.jsonl", "w", encoding="utf-8") as handle:
        for pair in pairs:
            handle.write(json.dumps(pair, ensure_ascii=False) + "\n")

    report["rationale_pairs"] = len(pairs)
    with open(OUT_DIR / "gold_labels_report.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    print(f"\nwrote {labelled} records, {len(pairs)} rationale pairs to {OUT_DIR}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
