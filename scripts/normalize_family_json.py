"""Normalize manufacturer family metadata to one stable local contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DEFAULTS = {
    "manufacturer": "",
    "product_count": 0,
    "datasheet_url": None,
    "detailed_knowledge_status": "",
    "source_url_status": None,
    "legacy_source_url": None,
}


def normalize_family(family: dict, manufacturer_dir: str) -> dict:
    normalized = dict(family)
    normalized.setdefault("manufacturer", manufacturer_dir.replace("_", " ").title())
    for key, default in FAMILY_DEFAULTS.items():
        if key not in normalized:
            normalized[key] = default
    return normalized


def normalize_tree(root: Path = ROOT, dry_run: bool = False) -> tuple[int, int]:
    changed = skipped = 0
    for path in sorted((root / "knowledge").glob("*/families.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped += 1
            continue
        manufacturer_dir = path.parent.name
        families = document.get("families")
        if not isinstance(families, list):
            skipped += 1
            continue
        normalized_families = [normalize_family(family, manufacturer_dir) for family in families]
        normalized = dict(document)
        normalized["families"] = normalized_families
        if normalized == document:
            skipped += 1
            continue
        changed += 1
        if not dry_run:
            path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    changed, skipped = normalize_tree(dry_run=args.dry_run)
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}normalized: {changed}  unchanged/skipped: {skipped}")


if __name__ == "__main__":
    main()
