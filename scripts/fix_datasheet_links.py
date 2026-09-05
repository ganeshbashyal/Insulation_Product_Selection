"""Repoint wrong-domain/missing datasheet links to verified manufacturer sites.

Companion to scripts/audit_datasheet_links.py. For every family whose
source_url fails the official-domain check (and whose manufacturer HAS a
verified domain), this script:
  - preserves the old URL as "legacy_source_url" (the reseller-hosted PDF may
    still be a genuine manufacturer document, useful when sourcing the real TDS)
  - sets "source_url" to the verified manufacturer site root
  - marks "source_url_status": "manufacturer_site_root_tds_pending" so the team
    knows the exact product TDS deep link still has to be sourced
  - patches the family's markdown doc (front matter official_datasheet_url and
    the "Technical Data Sheet:" body line)

Manufacturers without a live-verified domain (ecowool, hushtec, misc) are left
untouched and stay flagged as UNVERIFIED_MFR in the audit.

Usage:
    python scripts/fix_datasheet_links.py --dry-run
    python scripts/fix_datasheet_links.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_datasheet_links import OFFICIAL_DOMAINS, UNVERIFIED_MANUFACTURERS, classify

SITE_ROOTS = {
    "acoustica": "https://acoustica.com.au/",
    "aircell": "https://www.kingspan.com/au/",
    "ametalin": "https://www.ametalin.com/",
    "autex": "https://www.autexacoustics.com.au/",
    "bradford": "https://www.csrbradford.com.au/",
    "dctech": "https://dctech.com.au/",
    "fletcher": "https://insulation.com.au/",
    "foilboard": "https://www.foilboard.com.au/",
    "higgins insulation": "https://higginsinsulation.com.au/",
    "james hardie": "https://www.jameshardie.com.au/",
    "kingspan": "https://www.kingspan.com/au/",
    "knauf": "https://knauf.com/en-AU/knauf-insulation",
    "martini": "https://martini.com.au/",
    "metecno": "https://metecno.com/",
    "paroc": "https://www.paroc.com/en",
    "polyair": "https://www.polyair.com.au/",
    "polyester solutions": "https://www.polyestersolutions.com.au/",
    "proctor": "https://proctorgroup.com.au/",
    "rockwool": "https://www.rockwool.com/group/",
    "sonata acoustic panels": "https://sonataacousticpanels.com.au/",
    "stinger": "https://insulation.com.au/",
    "thermotec": "https://thermotec.com.au/",
    "trade select": "https://tradeselect.com.au/",
}
PENDING_STATUS = "manufacturer_site_root_tds_pending"


def patch_markdown(md_path: Path, old_url: str, new_url: str, dry_run: bool) -> bool:
    if not md_path.exists() or not old_url:
        return False
    text = md_path.read_text(encoding="utf-8")
    if old_url not in text:
        return False
    updated = text.replace(old_url, new_url)
    note = (
        f"\n> Datasheet link audited 2026-09-05: repointed to the verified manufacturer site. "
        f"Exact product TDS deep link still to be sourced; legacy reference: {old_url}\n"
    )
    marker = "Use this source for the canonical product identity"
    if marker in updated and note.strip() not in updated:
        updated = updated.replace(marker, note + "\n" + marker, 1)
    if not dry_run:
        md_path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fixed = patched_docs = skipped_unverified = already_ok = 0
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        manufacturer = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for family in data["families"]:
            url = (family.get("source_url") or "").strip()
            status = classify(manufacturer, url)
            if status == "OK_OFFICIAL":
                already_ok += 1
                continue
            if manufacturer in UNVERIFIED_MANUFACTURERS or manufacturer not in SITE_ROOTS:
                skipped_unverified += 1
                continue
            new_url = SITE_ROOTS[manufacturer]
            fixed += 1
            print(f"{manufacturer:<22} {family['name'][:50]:<52} {url[:60] or '(missing)':<62} -> {new_url}")
            if args.dry_run:
                continue
            if url and url != "[To be sourced]":
                family["legacy_source_url"] = url
            family["source_url"] = new_url
            family["source_url_status"] = PENDING_STATUS
            md_path = path.parent / family.get("knowledge_file", "")
            if patch_markdown(md_path, url, new_url, dry_run=args.dry_run):
                patched_docs += 1
            dirty = True
        if dirty and not args.dry_run:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"families repointed: {fixed}")
    print(f"markdown docs patched: {patched_docs}")
    print(f"already official: {already_ok}")
    print(f"skipped (unverified manufacturer domain): {skipped_unverified}")
    if args.dry_run:
        print("dry run - no files written")


if __name__ == "__main__":
    main()
