"""Apply hand-sourced TDS links from data/processed/tds_links_to_source.csv.

Fill the `new_tds_url` column in that CSV (one row per family), then run this
script. For every row with a non-empty, https URL it:
  - sets the family's source_url to the new link
  - changes source_url_status from "manufacturer_site_root_tds_pending" to
    "manufacturer_tds_confirmed" (schema updated accordingly)
  - patches the family's markdown doc (front matter + Tier 1 datasheet line)

Rows left blank are skipped and stay flagged as pending.

Usage:
    python scripts/apply_tds_links.py --dry-run
    python scripts/apply_tds_links.py
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_datasheet_links import OFFICIAL_DOMAINS, domain_matches, domain_of

CSV_PATH = ROOT / "data" / "processed" / "tds_links_to_source.csv"
CONFIRMED_STATUS = "manufacturer_tds_confirmed"


def patch_markdown(md_path: Path, new_url: str, dry_run: bool) -> bool:
    if not md_path.exists():
        return False
    text = md_path.read_text(encoding="utf-8")
    original = text
    text = re.sub(r"(?m)^official_datasheet_url: \S+$", f"official_datasheet_url: {new_url}", text)
    text = re.sub(r"(?m)^Technical Data Sheet: \S+$", f"Technical Data Sheet: {new_url}", text)
    text = re.sub(
        r"(?m)^> Datasheet link audited 2026-09-05:.*$",
        f"> Datasheet link confirmed {new_url}",
        text,
    )
    if text != original and not dry_run:
        md_path.write_text(text, encoding="utf-8")
    return text != original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with CSV_PATH.open(newline="", encoding="utf-8-sig") as fh:
        rows = [row for row in csv.DictReader(fh) if (row.get("new_tds_url") or "").strip()]
    if not rows:
        print("no new_tds_url values filled in", CSV_PATH.relative_to(ROOT))
        return

    updates = {}
    problems = []
    for row in rows:
        url = row["new_tds_url"].strip()
        if not url.startswith("https://"):
            problems.append(f"{row['family_id']}: not an https URL: {url}")
            continue
        official = OFFICIAL_DOMAINS.get(row["manufacturer"]) or []
        if official and not domain_matches(domain_of(url), official):
            problems.append(f"{row['family_id']}: {url} is not on the official {row['manufacturer']} domain")
            continue
        updates[row["family_id"]] = url
    for problem in problems:
        print("SKIP -", problem)

    applied = patched_docs = 0
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for family in data["families"]:
            new_url = updates.get(family["family_id"])
            if not new_url:
                continue
            applied += 1
            print(f"{path.parent.name:<22} {family['name'][:55]:<57} -> {new_url[:70]}")
            if args.dry_run:
                continue
            family["source_url"] = new_url
            family["source_url_status"] = CONFIRMED_STATUS
            if patch_markdown(path.parent / family.get("knowledge_file", ""), new_url, args.dry_run):
                patched_docs += 1
            dirty = True
        if dirty and not args.dry_run:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"links applied: {applied} (skipped: {len(problems)})")
    print(f"markdown docs patched: {patched_docs}")
    if args.dry_run:
        print("dry run - no files written")


if __name__ == "__main__":
    main()
