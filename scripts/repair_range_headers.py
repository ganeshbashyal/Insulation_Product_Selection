"""Repair research records whose column headers were stored as a data row.

A few knowledge_base_txt records ended up with spec.range[0] holding the column
names ("Thickness", "Width", ...) while spec.range_headers was left empty.
generate_family_literature.py keys off range_headers to choose its table layout,
so those families rendered a sizing table of blank cells - the data was present
but unreachable.

Promotes that first row to range_headers and drops it from range. Idempotent and
entirely local: reads and writes only files already in the repo.

    python scripts/repair_range_headers.py --dry-run
    python scripts/repair_range_headers.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Column names seen in the manufacturer sizing tables.
HEADER_TOKENS = {
    "variant", "thickness", "total thickness", "width", "length", "roll width",
    "roll length", "roll area", "size", "size / rating", "pack", "coverage",
    "structure", "product code", "historical product code", "r-value", "rvalue",
    "description", "replacement / current equivalent", "area", "sku",
}


def is_header_row(row: dict) -> bool:
    """True when a data row is really the table's column headings."""
    if not isinstance(row, dict) or len(row) < 3:
        return False
    values = [str(v).strip().lower() for v in row.values()]
    if any(not v for v in values):
        return False
    hits = sum(1 for v in values if v in HEADER_TOKENS)
    return hits >= max(3, len(values) // 2)


def repair(document: dict) -> bool:
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return False
    rows = spec.get("range")
    if not isinstance(rows, list) or not rows:
        return False
    if spec.get("range_headers"):
        return False  # already correct
    first = rows[0]
    if not is_header_row(first):
        return False

    ordered = sorted(first, key=lambda k: int(k[1:]) if k[1:].isdigit() else 0)
    spec["range_headers"] = [str(first[k]).strip() for k in ordered]
    spec["range"] = rows[1:]
    spec["range_extraction_status"] = "header_row_promoted"
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed = []
    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if repair(document):
            changed.append((path, document))

    for path, document in changed:
        rel = path.relative_to(ROOT)
        headers = document["spec"]["range_headers"]
        rows = len(document["spec"]["range"])
        print(f"  {document.get('family_id')}: {len(headers)} cols, {rows} rows  ({rel})")
        if not args.dry_run:
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    verb = "would repair" if args.dry_run else "repaired"
    print(f"{verb} {len(changed)} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
