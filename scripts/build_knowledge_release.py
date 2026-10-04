"""Build/preview local reviewed serving data; activate only with exact release approval."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge_service import service
from knowledge_release import ReleaseLibrary, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "data" / "local" / "releases")
    parser.add_argument("--activate")
    parser.add_argument("--confirm")
    parser.add_argument("--expected-active")
    parser.add_argument("--visibility", type=Path, help="Explicit local JSON site-to-family-ID mapping")
    args = parser.parse_args()
    try:
        library = ReleaseLibrary(args.directory)
        visibility = None
        if args.visibility:
            if not args.visibility.resolve().is_relative_to(ROOT):
                raise ValueError("Visibility manifest must be inside this checkout")
            visibility = json.loads(args.visibility.read_text(encoding="utf-8-sig"))
        if args.activate:
            candidate = library.read(args.activate)
            current = build(service(), visibility)
            if current["release_id"] != candidate["release_id"]:
                raise ValueError("Sources/publication changed since release build; rebuild")
            library.activate(args.activate, args.confirm, args.expected_active)
            print(json.dumps({"active": args.activate}))
        else:
            data = build(service(), visibility)
            path = library.save(data)
            print(json.dumps({"release_id": data["release_id"], "file": str(path),
                              "expected_active": library.active_id(),
                              "family_count": len(data["payload"]["families"]),
                              "verified_claims": sum(len(rows) for rows in data["payload"]["evidence"].values()),
                              "site_visibility": data["payload"]["site_visibility"],
                              "activated": False}, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Release blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
