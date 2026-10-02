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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
MANIFEST = KNOWLEDGE / "_tds_manifest.json"
REPORTS = ROOT / "reports"

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
    manifest = _load_manifest()
    rows: list[dict] = []

    for path in sorted(KNOWLEDGE.glob("*/research/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        family_id = data.get("family_id") or path.stem.upper()
        family_name = data.get("family_name") or data.get("name") or path.stem
        manufacturer = path.parent.parent.name
        manifest_entry = manifest.get(family_id)
        has_manifest_file = bool(manifest_entry and _manifest_has_file(manifest_entry))
        local_path = data.get("datasheet_local_path")
        has_local_path = bool(local_path and (ROOT / local_path).exists())

        if has_manifest_file or has_local_path:
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


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_xlsx(path: Path, rows: list[dict]) -> bool:
    try:
        import pandas as pd
    except ImportError:
        return False
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
    args = parser.parse_args()

    all_missing = _research_rows()
    products = [row for row in all_missing if row["accessory"] == "no"]

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
