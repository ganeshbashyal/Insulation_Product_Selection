"""Private authoring snapshots, separate from customer/runtime state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

LIBRARIES = ("knowledge", "schemas", "data/tds", "data/tds_inbox", "evidence/raw",
             "data/raw", "data/processed", "reports", "output/literature",
             "data/local/intake", "data/local/catalogue_versions", "data/local/competitors",
             "data/local/source_reviews", "data/local/releases",
             "data/local/family_knowledge_drafts")
RECEIPTS = ("data/local/source_review.json", "data/local/fresh_tds_cache.json",
            "data/local/family_completion.md", "data/local/tds_register.json")
REVIEW_DB = "data/local/product_research.sqlite3"


def permitted(name: str) -> bool:
    if not isinstance(name, str) or "\\" in name or ":" in name:
        return False
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return name in RECEIPTS or name == REVIEW_DB or any(
        name.startswith(directory + "/") for directory in LIBRARIES
    )


def confined(root: Path, name: str) -> Path:
    if not permitted(name):
        raise ValueError(f"Unknown authoring backup path: {name}")
    path = root.joinpath(*name.split("/"))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Authoring path escapes root: {name}")
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError(f"Symlink authoring path rejected: {name}")
    return path


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inventory(root: Path) -> dict[str, str]:
    root = root.resolve()
    paths = []
    for directory in LIBRARIES:
        base = confined(root, directory + "/placeholder").parent
        paths.extend(path for path in base.rglob("*")
                     if path.is_file() and not path.name.startswith("~$"))
    paths.extend(root / name for name in RECEIPTS if (root / name).is_file())
    return {path.relative_to(root).as_posix(): digest(confined(root, path.relative_to(root).as_posix()))
            for path in sorted(set(paths))}


def checked_manifest(source: Path) -> dict:
    """Validate every declared file before restore creates a destination."""
    data = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("files"), dict):
        raise ValueError("Invalid authoring backup manifest")
    for name, checksum in data["files"].items():
        path = confined(source, name)
        if not isinstance(checksum, str) or len(checksum) != 64 or not path.is_file() or digest(path) != checksum:
            raise ValueError(f"Authoring backup checksum mismatch: {name}")
    return data


def backup(root: Path, target: Path) -> dict:
    root, target = root.resolve(), target.absolute()
    if target.exists() or target.resolve().is_relative_to(root) or root.is_relative_to(target.resolve()):
        raise ValueError("Backup requires a new directory outside the authoring checkout")
    before = inventory(root)
    target.mkdir(parents=True)
    for name, checksum in before.items():
        source, destination = confined(root, name), confined(target, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if digest(destination) != checksum:
            raise ValueError(f"Source changed during backup: {name}")
    db = confined(root, REVIEW_DB)
    files = dict(before)
    if db.is_file():
        destination = confined(target, REVIEW_DB)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True) as original:
            with sqlite3.connect(destination) as copy:
                original.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Authoring database backup integrity failure")
        files[REVIEW_DB] = digest(destination)
    if inventory(root) != before:
        raise ValueError("Authoring files changed during backup; snapshot is incomplete")
    manifest = {"schema_version": 1, "files": files,
                "privacy": "Private authoring data including accounts; no customer/runtime databases.",
                "restore": "New directory only; sessions cleared and publication held until reviewed."}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    checked_manifest(target)
    return {"file_count": len(files), "backup": str(target), "verified": True}


def restore(source: Path, target: Path, *, confirm: bool = False) -> dict:
    source, target = source.resolve(), target.absolute()
    data = checked_manifest(source)
    if target.exists() or target.resolve().is_relative_to(source) or source.is_relative_to(target.resolve()):
        raise ValueError("Restore requires a new directory outside the snapshot")
    result = {"file_count": len(data["files"]), "target": str(target),
              "sessions": "cleared", "publication": "held_until_explicit_review", "writes": confirm}
    if not confirm:
        return result
    target.mkdir(parents=True)
    for name, checksum in data["files"].items():
        destination = confined(target, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(confined(source, name), destination)
        if digest(destination) != checksum:
            raise ValueError(f"Restore checksum mismatch: {name}")
    db = target / REVIEW_DB
    if db.is_file():
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM active_publication")
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Restored authoring database integrity failure")
    return result
