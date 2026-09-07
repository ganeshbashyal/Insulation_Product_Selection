"""Integrate the external engine/knowledge sources into the bot's canonical repo.

This is intentionally conservative: it keeps the source material under the external
project as provenance, but mirrors the bot-relevant Markdown corpus into the repo's
`knowledge/industry/` area and records a manifest so future reads can trace what was
imported and from which source root.

Usage:
    python scripts/integrate_external_knowledge_sources.py
    python scripts/integrate_external_knowledge_sources.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = Path(r"C:\Users\ganes\OneDrive\Desktop\Insulation bot")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_engine_workspace() -> Path | None:
    if not BOT_ROOT.exists():
        return None
    engines_dir = BOT_ROOT / "Engines"
    if not engines_dir.exists():
        return None
    candidate = engines_dir / "workspace"
    if candidate.is_dir():
        return candidate
    for item in sorted(engines_dir.iterdir()):
        workspace = item / "workspace"
        if workspace.is_dir():
            return workspace
    return None


def discover_knowledge_dir() -> Path | None:
    if not BOT_ROOT.exists():
        return None
    knowledge_dir = BOT_ROOT / "Knowledge"
    if knowledge_dir.is_dir():
        return knowledge_dir
    return None


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def merge_root_files(source_dir: Path, dest_dir: Path, dry_run: bool) -> dict[str, list[str]]:
    files = [
        "README.md",
        "AU_Insulation_Expert_Knowledge_Base.md",
        "BOT_TRAINING_PACKAGE.md",
    ]
    results = {"copied": [], "updated": [], "unchanged": [], "missing": []}
    for name in files:
        src = source_dir / name
        if not src.exists():
            results["missing"].append(name)
            continue
        dst = dest_dir / name
        ensure_directory(dest_dir)
        if dst.exists():
            same = file_hash(src) == file_hash(dst)
            if same:
                results["unchanged"].append(name)
                continue
            if dry_run:
                results["updated"].append(name)
                continue
            shutil.copy2(src, dst)
            results["updated"].append(name)
        else:
            if dry_run:
                results["copied"].append(name)
                continue
            shutil.copy2(src, dst)
            results["copied"].append(name)
    return results


def merge_tree(source_dir: Path, dest_dir: Path, dry_run: bool) -> dict[str, list[str]]:
    results = {"copied": [], "updated": [], "unchanged": [], "missing": []}
    for rel in [
        "compliance",
        "customer_support",
        "principles",
        "product_intelligence",
        "training",
        "tools",
    ]:
        src_dir = source_dir / rel
        dst_dir = dest_dir / rel
        if not src_dir.exists():
            results["missing"].append(rel)
            continue
        ensure_directory(dst_dir)
        for src_file in sorted(src_dir.rglob("*")):
            if not src_file.is_file():
                continue
            rel_path = src_file.relative_to(src_dir)
            dst = dst_dir / rel_path
            if not dst.parent.exists():
                ensure_directory(dst.parent)
            if dst.exists():
                same = file_hash(src_file) == file_hash(dst)
                if same:
                    results["unchanged"].append(rel + "/" + rel_path.as_posix())
                    continue
                if dry_run:
                    results["updated"].append(rel + "/" + rel_path.as_posix())
                    continue
                shutil.copy2(src_file, dst)
                results["updated"].append(rel + "/" + rel_path.as_posix())
            else:
                if dry_run:
                    results["copied"].append(rel + "/" + rel_path.as_posix())
                    continue
                shutil.copy2(src_file, dst)
                results["copied"].append(rel + "/" + rel_path.as_posix())
    return results


def create_manifest(manifest_path: Path, source_engine: Path | None, source_knowledge: Path | None, root_results: dict, tree_results: dict, dry_run: bool) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "sources": {
            "engine_workspace": str(source_engine) if source_engine else None,
            "knowledge_dir": str(source_knowledge) if source_knowledge else None,
        },
        "root_files": root_results,
        "directories": tree_results,
        "status": "integrated" if not dry_run else "preview",
        "notes": [
            "This manifest records the bot-relevant external knowledge that was imported into the repo's canonical industry corpus.",
            "The external project remains the source archive; the repo is the active bot knowledge layer.",
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine_workspace = discover_engine_workspace()
    knowledge_dir = discover_knowledge_dir()
    target = ROOT / "knowledge" / "industry"
    ensure_directory(target)

    root_results = {"copied": [], "updated": [], "unchanged": [], "missing": []}
    tree_results = {"copied": [], "updated": [], "unchanged": [], "missing": []}

    if engine_workspace and engine_workspace.exists():
        root_results.update(merge_root_files(engine_workspace, target, args.dry_run))
        tree_results.update(merge_tree(engine_workspace, target, args.dry_run))
    else:
        root_results["missing"] = ["engine workspace not found"]
        tree_results["missing"] = ["engine workspace not found"]

    if knowledge_dir and knowledge_dir.exists():
        source_product_files = [
            "Australian Insulation Knowledge Bas.txt",
            "Breeze- dump.txt",
            "granular text.txt",
            "Thermal Acoustic BOt Training Dataset.txt",
            "Top Questions.txt",
            "nuwave-mass-loaded-vinyl.md",
        ]
        archive_dir = ROOT / "evidence" / "inbox" / "external-dump-2026-09-07"
        ensure_directory(archive_dir)
        for name in source_product_files:
            src = knowledge_dir / name
            if not src.exists():
                continue
            dst = archive_dir / name
            if dst.exists() and file_hash(src) == file_hash(dst):
                continue
            if not args.dry_run:
                shutil.copy2(src, dst)

    manifest_path = target / "external_source_manifest.json"
    create_manifest(manifest_path, engine_workspace, knowledge_dir, root_results, tree_results, args.dry_run)

    print(f"engine workspace: {engine_workspace}")
    print(f"knowledge dir: {knowledge_dir}")
    print(f"manifest: {manifest_path}")
    print(json.dumps({"root_files": root_results, "directories": tree_results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
