"""Normalize research JSON files to one stable local contract.

Existing values and non-canonical fields are preserved. Missing canonical fields
are added with neutral defaults so downstream Markdown, SQLite and retrieval code
can consume every research file consistently.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_DEFAULTS = {
    "schema_version": "1.0",
    "datasheet_pdf_url": "",
    "sds_url": "",
    "status": "",
    "researched_at": "",
    "engine": "local",
    "source_excerpt": None,
    "retrieval": {},
    "range_source": "",
}
SPEC_DEFAULTS = {
    "description": "",
    "features": [],
    "applications": [],
    "technical": [],
    "range_headers": [],
    "range": [],
    "fire": "",
    "sustainability": "",
    "install": [],
    "clearances": [],
    "limitations": [],
    "selection_checklist": [],
    "compliance": "",
    "warranty": "",
    "accessories": [],
    "accessories_upsell": [],
}


def normalize_document(document: dict) -> dict:
    normalized = dict(document)
    normalized["schema_version"] = "1.0"
    for key, default in TOP_LEVEL_DEFAULTS.items():
        if key not in normalized or normalized[key] is None:
            normalized[key] = default.copy() if isinstance(default, dict) else default

    spec = normalized.get("spec")
    if not isinstance(spec, dict):
        spec = {}
    normalized_spec = dict(spec)
    for key, default in SPEC_DEFAULTS.items():
        if key not in normalized_spec or normalized_spec[key] is None:
            normalized_spec[key] = default.copy() if isinstance(default, list) else default
    normalized["spec"] = normalized_spec
    return normalized


def normalize_tree(root: Path = ROOT, dry_run: bool = False) -> tuple[int, int]:
    changed = skipped = 0
    for path in sorted((root / "knowledge").glob("*/research/*.json")):
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped += 1
            continue
        if not isinstance(original, dict):
            skipped += 1
            continue
        normalized = normalize_document(original)
        if normalized == original:
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
