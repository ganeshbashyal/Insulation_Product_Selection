"""Clean the retrieval fields of every research JSON in place.

Applies the shared rules in ``retrieval_hygiene`` to
``knowledge/*/research/*.json`` and writes a full audit trail of every change
to ``data/processed/retrieval_cleaning_report.csv`` (file, field, action,
original, result). Dry-run by default; pass ``--apply`` to write.

Usage:
    python scripts/clean_retrieval_fields.py            # dry run + report
    python scripts/clean_retrieval_fields.py --apply    # write the files
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrieval_hygiene import LIST_FIELDS, clean_term

REPORT_PATH = ROOT / "data" / "processed" / "retrieval_cleaning_report.csv"


def clean_file(path: Path, rows: list[dict]) -> tuple[dict | None, int, int]:
    """Return (updated data or None, kept count, dropped count) for one file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, 0, 0
    retrieval = data.get("retrieval")
    if not isinstance(retrieval, dict) or not retrieval:
        return None, 0, 0

    changed = False
    kept = dropped = 0
    rel = path.relative_to(ROOT).as_posix()
    for field in LIST_FIELDS:
        terms = retrieval.get(field)
        if not isinstance(terms, list):
            continue
        seen: set[str] = set()
        out: list[str] = []
        for term in terms:
            cleaned = clean_term(term, field)
            if cleaned is None:
                dropped += 1
                rows.append({"file": rel, "field": field, "action": "dropped", "original": term, "result": ""})
                continue
            key = cleaned.casefold()
            if key in seen:
                dropped += 1
                rows.append({"file": rel, "field": field, "action": "deduped", "original": term, "result": cleaned})
                continue
            seen.add(key)
            out.append(cleaned)
            kept += 1
            if cleaned != term:
                rows.append({"file": rel, "field": field, "action": "cleaned", "original": term, "result": cleaned})
        out.sort(key=str.casefold)
        if out != terms:
            retrieval[field] = out
            changed = True

    return (data if changed else None), kept, dropped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write cleaned files (default: dry run)")
    args = parser.parse_args()

    rows: list[dict] = []
    files_changed = total_kept = total_dropped = 0
    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        updated, kept, dropped = clean_file(path, rows)
        total_kept += kept
        total_dropped += dropped
        if updated is not None:
            files_changed += 1
            if args.apply:
                path.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "field", "action", "original", "result"])
        writer.writeheader()
        writer.writerows(rows)

    mode = "APPLIED" if args.apply else "DRY RUN (use --apply to write)"
    print(f"{mode}: {files_changed} files changed, {total_kept} terms kept, {total_dropped} dropped/deduped")
    print(f"report: {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
