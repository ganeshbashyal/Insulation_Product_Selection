"""Explicit local authoring backup and new-directory restore."""
import argparse
from pathlib import Path
import sys
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from authoring_backup import backup, restore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore-preview", "restore"])
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action != "restore-preview" and not args.confirm:
            raise ValueError("Writes require --confirm; stop authoring edits first")
        result = backup(args.source, args.target) if args.action == "backup" else restore(
            args.source, args.target, confirm=args.action == "restore")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
