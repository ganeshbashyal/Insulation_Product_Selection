"""Explicit offline backup/restore of named serving SQLite stores. Stop server first."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

NAMES = {"sessions.sqlite3", "interactions.sqlite3", "audit.sqlite3",
         "rate_limits.sqlite3", "widget_tokens.sqlite3"}


def backup(state: Path, target: Path):
    if target.exists() or target.resolve().is_relative_to(state.resolve()):
        raise ValueError("Use a new backup directory outside the serving state directory")
    target.mkdir(parents=True)
    hashes = {}
    for name in sorted(NAMES):
        source = state / name
        if not source.is_file():
            continue
        with sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True) as src:
            with sqlite3.connect(target / name) as dest:
                src.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed: "+name)
        hashes[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps({"databases":hashes}, indent=2), encoding="utf-8")
    return hashes


def restore(source: Path, state: Path):
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    rows = manifest["databases"]
    if not isinstance(rows,dict) or not set(rows).issubset(NAMES):
        raise ValueError("Unknown backup database paths")
    for name, expected in rows.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Backup checksum mismatch: "+name)
    state.mkdir(parents=True,exist_ok=True)
    if any((state / name).exists() for name in NAMES):
        raise ValueError("Restore into an empty state directory; never overwrite live databases")
    for name in sorted(rows):
        with sqlite3.connect(f"{(source/name).resolve().as_uri()}?mode=ro",uri=True) as src:
            with sqlite3.connect(state / name) as dest:
                src.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Restore integrity check failed: "+name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["backup","restore"])
    parser.add_argument("--state",type=Path,required=True)
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--confirm-server-stopped",action="store_true",required=True)
    args=parser.parse_args()
    try:
        if args.action=="backup":
            result=backup(args.state,args.backup)
            print(json.dumps({"backed_up":sorted(result),"private_data":"keep backup private"}))
        else:
            restore(args.backup,args.state)
            print(json.dumps({"restored":True}))
        return 0
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(f"Backup/restore blocked: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
