"""Durable, external library of every technical datasheet we hold.

The repo cannot keep these documents: data/tds/ and data/local/tds_cache/ are
gitignored because they are third-party manufacturer files, so a fresh
worktree starts with none of them and the research has to be re-downloaded.
That is exactly how 118 families ended up with a spec and no retained source.

This copies everything we already hold into one folder outside the repo, so
re-downloading is never necessary again:

    <library>/<manufacturer>/<family_slug>.pdf     attributed to a family
    <library>/_unattributed/<sha256>.pdf           held but not yet matched
    <library>/_library_manifest.json               sha256 -> where it came from

Files are addressed by content hash, so running this repeatedly is safe and
the same document downloaded twice is stored once.

Set AURORA_TDS_LIBRARY to change the location.

Usage:
    python scripts/sync_tds_library.py                 # dry run
    python scripts/sync_tds_library.py --apply
    python scripts/sync_tds_library.py --apply --restore   # copy back into the repo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_LIBRARY = Path(os.getenv(
    "AURORA_TDS_LIBRARY", r"C:\Users\ganes\Desktop\Data Gathering\data\TDS"))

ARCHIVE = ROOT / "data" / "tds"
CACHE = ROOT / "data" / "local" / "tds_cache"
DOC_SUFFIXES = {".pdf", ".docx"}
MANIFEST_NAME = "_library_manifest.json"
UNATTRIBUTED = "_unattributed"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(library: Path) -> dict:
    path = library / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"warning: {path} unreadable, rebuilding", file=sys.stderr)
        return {}


def write_manifest(library: Path, manifest: dict) -> None:
    library.mkdir(parents=True, exist_ok=True)
    ordered = {k: manifest[k] for k in sorted(manifest)}
    (library / MANIFEST_NAME).write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")


def family_index() -> dict[str, dict]:
    """Map repo-relative archived path -> family details, so copies into the
    library are named after the family rather than an opaque hash."""
    index = {}
    for path in sorted(ROOT.glob("knowledge/*/research/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        local = data.get("datasheet_local_path")
        if not local:
            continue
        index[str(Path(local)).replace("\\", "/")] = {
            "family_id": data.get("family_id", path.stem),
            "manufacturer": path.parent.parent.name,
            "slug": path.stem,
        }
    return index


def store(library: Path, source: Path, manifest: dict, apply: bool,
          family: dict | None) -> str:
    """Copy one document into the library, addressed by content hash."""
    digest = sha256_of(source)
    entry = manifest.get(digest)

    if family:
        rel = f"{family['manufacturer']}/{family['slug']}{source.suffix.casefold()}"
    else:
        rel = f"{UNATTRIBUTED}/{digest[:16]}{source.suffix.casefold()}"

    # Already held, and now attributable when it previously was not.
    if entry:
        if family and entry.get("family_id") is None:
            if apply:
                dest = library / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                old = library / entry["path"]
                if old.exists() and old != dest:
                    old.unlink()
                entry.update({"path": rel, "family_id": family["family_id"],
                              "manufacturer": family["manufacturer"]})
            return "attributed"
        return "already_held"

    if apply:
        dest = library / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    manifest[digest] = {
        "path": rel,
        "bytes": source.stat().st_size,
        "family_id": family["family_id"] if family else None,
        "manufacturer": family["manufacturer"] if family else None,
        "origin": str(source.relative_to(ROOT)).replace("\\", "/"),
    }
    return "stored"


def restore(library: Path, manifest: dict, apply: bool) -> int:
    """Copy attributed documents from the library back into data/tds/, which is
    what makes a fresh worktree usable without downloading anything."""
    restored = 0
    for entry in manifest.values():
        if not entry.get("family_id") or not entry.get("manufacturer"):
            continue
        source = library / entry["path"]
        if not source.exists():
            continue
        dest = ARCHIVE / Path(entry["path"])
        if dest.exists() and dest.stat().st_size == source.stat().st_size:
            continue
        restored += 1
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
    return restored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    parser.add_argument("--restore", action="store_true",
                        help="also copy attributed documents back into data/tds/")
    args = parser.parse_args()

    library = args.library
    print(f"library: {library}")
    if args.apply:
        library.mkdir(parents=True, exist_ok=True)
    elif not library.exists():
        print("  (does not exist yet; --apply will create it)")

    manifest = load_manifest(library)
    index = family_index()
    tally: dict[str, int] = {}

    sources = [p for p in sorted(ARCHIVE.rglob("*")) if p.is_file() and p.suffix.casefold() in DOC_SUFFIXES]
    sources += [p for p in sorted(CACHE.glob("*")) if p.is_file() and p.suffix.casefold() in DOC_SUFFIXES]

    for source in sources:
        rel = str(source.relative_to(ROOT)).replace("\\", "/")
        outcome = store(library, source, manifest, args.apply, index.get(rel))
        tally[outcome] = tally.get(outcome, 0) + 1

    if args.apply:
        write_manifest(library, manifest)

    attributed = sum(1 for e in manifest.values() if e.get("family_id"))
    print(f"\n{dict(sorted(tally.items()))}")
    print(f"library holds {len(manifest)} distinct document(s); "
          f"{attributed} attributed to a family, {len(manifest) - attributed} unattributed")

    if args.restore:
        count = restore(library, manifest, args.apply)
        print(f"restored {count} document(s) into data/tds/")

    if not args.apply:
        print("\nDRY RUN - re-run with --apply to write")


if __name__ == "__main__":
    main()
