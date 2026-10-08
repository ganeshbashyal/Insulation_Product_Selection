"""Export reviewed retrieval/voice/SQLite data locally; no network or models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge_release import ReleaseLibrary
from release_exports import export


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-id", required=True)
    args = parser.parse_args()
    try:
        destination = args.output.resolve()
        local = (ROOT / "data" / "local" / "exports").resolve()
        if not local.is_relative_to(ROOT) or not destination.is_relative_to(local) or destination == local:
            raise ValueError("Use a new named directory under data/local/exports")
        result = export(ReleaseLibrary(args.releases), destination, args.site_id)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Export blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
