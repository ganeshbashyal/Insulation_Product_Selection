"""Create a private, hash-verified map from Vault PDFs to family Markdown and SKUs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vault_product_files import LOCAL_OUTPUT, build_reconciliation, write_reconciliation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-files", type=Path, required=True,
                        help="Local folder containing product_files_manifest.csv and PDFs")
    parser.add_argument("--write-local-reports", action="store_true",
                        help="Write the report and per-family Markdown pages under data/local")
    parser.add_argument("--confirm-local-only", action="store_true",
                        help="Confirm report output is private and machine-local")
    parser.add_argument("--output", type=Path, default=LOCAL_OUTPUT,
                        help="Private output directory under this repository's data/local")
    args = parser.parse_args()
    if args.write_local_reports and not args.confirm_local_only:
        parser.error("--write-local-reports requires --confirm-local-only")

    try:
        report = build_reconciliation(args.product_files)
        print(json.dumps(report["summary"], indent=2))
        if report["validation_errors"]:
            print("PDF validation errors:")
            for error in report["validation_errors"]:
                print(f"- {error}")
            return 2
        if args.write_local_reports:
            written = write_reconciliation(report, args.output)
            print(f"Generated {len(written)} private local review files under {args.output.resolve()}")
        else:
            print("Read-only preview; no files were written.")
        if report["unassigned_files"]:
            print(f"{len(report['unassigned_files'])} PDF(s) remain unassigned; no family was guessed.")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Reconciliation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
