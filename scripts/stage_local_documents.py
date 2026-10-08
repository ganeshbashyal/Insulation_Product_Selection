"""Preview or explicitly stage owner-mapped local PDFs; no URL fetching or models."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_intake import preview, stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--confirm", help="Exact preview ID to stage; omission is read-only")
    args = parser.parse_args()
    try:
        result = {"staged": str(stage(ROOT, args.manifest, args.confirm))} if args.confirm else preview(ROOT, args.manifest)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Intake blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
