"""Read every page of existing local PDFs into an ignored review report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_source_review import AUDIT_PATH, build_review, retain_review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=AUDIT_PATH)
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.suffix.casefold() != ".json" or not output.is_relative_to((ROOT / "data" / "local").resolve()):
        parser.error("Review output must be JSON under data/local; source documents cannot be overwritten")
    report = build_review()
    if not args.confirm_write:
        print(f"Preview: {len(report['documents'])} local documents; no files written. Use --confirm-write to retain audit history.")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = retain_review(report, output)
    failed = [path for path, doc in report["documents"].items() if doc["status"] != "text_extracted"]
    print(f"{len(report['documents'])} local PDFs reviewed, {len(failed)} need OCR/read review; no claim approved.")
    print(output)
    print(receipt["receipt"])
    for path in failed:
        print(f"NEEDS REVIEW: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
