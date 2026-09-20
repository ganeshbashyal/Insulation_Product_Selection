"""Relink product variants to a datasheet we already hold.

Some manufacturers publish one datasheet per product *range* and sell many
variants from it (Autex is the clearest case: the Horizon datasheet covers every
Horizon shape). Those variants look unsourced even though the correct document is
already in ``data/tds``.

This assigns the held document to the variant. It never downloads anything and it
never invents a range: a rule only fires when we genuinely hold a datasheet for
that range, and the variant name must carry the range's own words.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "knowledge" / "_tds_manifest.json"
ACCURACY = ROOT / "reports" / "tds_accuracy.json"

# range key -> (family we already hold it for, required words in the variant name)
# Each rule is deliberately narrow. If a variant needs judgement, leave it out and
# let it stay on the "please supply a link" list.
RULES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "autex": [
        ("AUTEX_HORIZON_CIRCLE", ("horizon",)),
        ("AUTEX_GRID_CEILING_TILES_VAULT_SQUARE_UNCAPPED", ("grid", "ceiling", "tiles")),
        ("AUTEX_CUBE", ("cube",)),
        ("AUTEX_FRONTIER_RAFT_BEAM", ("frontier",)),
        ("AUTEX_COMPOSITION_VELOUR_ROLL", ("composition",)),
        ("AUTEX_COVE_ACOUSTIC_DESK_DIVIDER_ARC", ("cove",)),
        ("AUTEX_GROOVE", ("groove",)),
    ],
}


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def research_files() -> list[Path]:
    return sorted(ROOT.glob("knowledge/*/research/*.json"))


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def invalidate_accuracy(family_ids: set[str]) -> int:
    """Drop stale audit scores so the next sweep re-reads the new document."""
    if not ACCURACY.exists() or not family_ids:
        return 0
    report = json.loads(ACCURACY.read_text(encoding="utf-8"))
    rows = report if isinstance(report, list) else report.get("families", [])
    kept = [r for r in rows if r.get("family_id") not in family_ids]
    dropped = len(rows) - len(kept)
    if dropped:
        if isinstance(report, list):
            report = kept
        else:
            report["families"] = kept
        ACCURACY.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return dropped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument("--manufacturer", help="limit to one manufacturer key")
    args = parser.parse_args()

    manifest = load_manifest()
    families = {}
    for path in research_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        families[data["family_id"]] = (path, data)

    relinked: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []

    for maker, rules in RULES.items():
        if args.manufacturer and args.manufacturer != maker:
            continue

        usable = []
        for source_id, required in rules:
            entry = manifest.get(source_id)
            if not entry:
                skipped.append((source_id, "no held datasheet for this range"))
                continue
            if not (ROOT / entry["path"]).exists():
                skipped.append((source_id, f"missing file {entry['path']}"))
                continue
            usable.append((source_id, required, entry))

        for family_id, (path, data) in families.items():
            if family_id in manifest:
                continue
            if path.parts[-3] != maker:
                continue
            name = words(data.get("family_name") or "")
            matches = [u for u in usable if set(u[1]) <= name]
            if not matches:
                skipped.append((family_id, "no range datasheet held"))
                continue
            if len(matches) > 1:
                names = ", ".join(m[0] for m in matches)
                skipped.append((family_id, f"ambiguous range ({names})"))
                continue

            source_id, _, entry = matches[0]
            source_data = families[source_id][1]
            relinked.append((family_id, source_id, entry["path"]))

            if args.apply:
                data["datasheet_local_path"] = entry["path"]
                data["datasheet_pdf_url"] = source_data.get("datasheet_pdf_url")
                data["datasheet_source"] = f"shared_range:{source_id}"
                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                manifest[family_id] = {
                    **entry,
                    "origin": "shared_range",
                    "shared_with": source_id,
                }

    for family_id, source_id, doc in relinked:
        print(f"RELINK  {family_id:<52} <- {source_id} ({doc})")
    for family_id, reason in sorted(set(skipped)):
        print(f"skip    {family_id:<52} {reason}")
    print(f"\nrelinked {len(relinked)}, skipped {len(set(skipped))}")

    if args.apply and relinked:
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        dropped = invalidate_accuracy({r[0] for r in relinked})
        print(f"manifest updated; {dropped} stale accuracy rows dropped")
    elif relinked:
        print("dry run - re-run with --apply to write")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
