"""Build local review workbooks for families still missing a held TDS.

Pure local operation. It reads tracked knowledge JSON plus the local TDS
manifest and writes:

    reports/missing_tds.csv
    reports/missing_tds.xlsx
    reports/missing_tds_products.csv
    reports/missing_tds_products.xlsx

The products report excludes obvious accessories and includes a blank
``supplied_tds_url`` column for manual link collection.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
MANIFEST = KNOWLEDGE / "_tds_manifest.json"
REPORTS = ROOT / "reports"
sys.path.insert(0, str(ROOT))

ACCESSORY_WORDS = {
    "accessories",
    "accessory",
    "adhesive",
    "anchor",
    "angle",
    "batten",
    "biscuit",
    "bracket",
    "channel",
    "clip",
    "damper",
    "drainage",
    "fastene",
    "fixing",
    "flashing",
    "filter",
    "filler",
    "glue",
    "hanger",
    "joiner",
    "kit",
    "nail",
    "pack",
    "pin",
    "plate",
    "plug",
    "polystrapping",
    "rail",
    "saddle",
    "screw",
    "sealant",
    "strap",
    "strapping",
    "strip",
    "tape",
    "tensorgrip",
    "vent",
    "ventilation",
    "washer",
}

# Product names containing these words are still real insulation/acoustic
# products and must not be excluded merely because they contain a generic word.
PRODUCT_WORD_EXCEPTIONS = {
    "batt",
    "blanket",
    "board",
    "panel",
    "pipe",
    "roll",
    "slab",
    "wrap",
}


def _words(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", text.casefold()))
    # Treat simple plurals/truncated catalogue labels as their base accessory
    # word so "fasteners", "washers", "clips" and "screws" classify cleanly.
    words.update(word[:-1] for word in list(words) if len(word) > 3 and word.endswith("s"))
    words.update("fastene" for word in list(words) if word.startswith("fasten"))
    return words


def _is_accessory(name: str) -> bool:
    words = _words(name)
    if words & PRODUCT_WORD_EXCEPTIONS:
        return False
    return bool(words & ACCESSORY_WORDS)


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _manifest_has_file(entry: dict) -> bool:
    path = entry.get("path")
    return bool(path and (ROOT / path).exists())


def _research_rows() -> list[dict]:
    from family_knowledge import load_families
    from local_source_review import SourceReview
    sources = SourceReview(ROOT)
    rows: list[dict] = []

    for family_id, family in load_families(ROOT).items():
        data = sources.research.get(family_id, {})
        family_name = family["name"]
        manufacturer = family["manufacturer"]
        manifest_entry = sources.manifest.get(family_id)
        if any(document["exists"] for document in sources.documents(family_id)):
            continue

        accessory = _is_accessory(family_name)
        rows.append({
            "manufacturer": manufacturer,
            "family_id": family_id,
            "family_name": family_name,
            "research_status": data.get("status") or "",
            "missing_reason": (
                "manifest_entry_without_file"
                if manifest_entry
                else "no_held_datasheet"
            ),
            "accessory": "yes" if accessory else "no",
            "current_datasheet_pdf_url": data.get("datasheet_pdf_url") or "",
            "supplied_tds_url": "",
        })

    rows.sort(key=lambda r: (r["accessory"], r["manufacturer"], r["family_name"]))
    return rows


def _preserve_manual(path: Path, rows: list[dict]) -> list[dict]:
    """Keep user columns and resolved historical requests, keyed by family ID."""
    if not path.exists():
        return rows
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            previous = list(csv.DictReader(handle))
    else:
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            if len(book.worksheets) != 1:
                raise ValueError(f"{path.name}: multiple manual sheets; refusing automatic replacement")
            values = book.active.values
            headers = next(values, ())
            if "family_id" not in headers:
                raise ValueError(f"{path.name}: no family_id; cannot preserve manual work")
            previous = [dict(zip(headers, row)) for row in values if any(value is not None for value in row)]
        finally:
            book.close()
    old = {}
    for row in previous:
        key = row.get("family_id")
        if not key or key in old:
            raise ValueError(f"{path.name}: missing/duplicate family ID; cannot preserve manual work")
        old[key] = row
    result = []
    generated = set(rows[0]) - {"supplied_tds_url"} if rows else set()
    for row in rows:
        manual = {key: value for key, value in old.pop(row["family_id"], {}).items() if key not in generated}
        result.append({**row, **manual})
    result.extend({**row, "missing_reason": "historical_request_retained"} for row in old.values())
    return result


def _write_csv(path: Path, rows: list[dict]) -> None:
    rows = _preserve_manual(path, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_xlsx(path: Path, rows: list[dict]) -> bool:
    try:
        import pandas as pd
    except ImportError:
        return False
    rows = _preserve_manual(path, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False)
    return True


def _summarise(label: str, rows: list[dict]) -> None:
    print(f"{label}: {len(rows)}")
    by_maker: dict[str, int] = {}
    for row in rows:
        by_maker[row["manufacturer"]] = by_maker.get(row["manufacturer"], 0) + 1
    for maker, count in sorted(by_maker.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {maker:<16} {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-xlsx", action="store_true", help="write CSV only")
    parser.add_argument("--confirm-write", action="store_true",
                        help="regenerate reports preserving manual fields; back up authoring data first")
    args = parser.parse_args()

    all_missing = _research_rows()
    products = [row for row in all_missing if row["accessory"] == "no"]
    if not args.confirm_write:
        _summarise("preview missing including accessories", all_missing)
        _summarise("preview missing products only", products)
        print("Read-only preview. --confirm-write is required; authoring backup first.")
        return

    _write_csv(REPORTS / "missing_tds.csv", all_missing)
    _write_csv(REPORTS / "missing_tds_products.csv", products)
    wrote_xlsx = False
    if not args.no_xlsx:
        wrote_xlsx = _write_xlsx(REPORTS / "missing_tds.xlsx", all_missing)
        wrote_xlsx = _write_xlsx(REPORTS / "missing_tds_products.xlsx", products) or wrote_xlsx

    _summarise("missing including accessories", all_missing)
    _summarise("missing products only", products)
    print(f"xlsx: {'written' if wrote_xlsx else 'skipped'}")


if __name__ == "__main__":
    main()
