"""Read-only local deployment inventory; no network, models, migrations or builds."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_service import knowledge_validation
from product_research import ResearchIndex


def inventory(root: Path = ROOT) -> dict:
    idx = ResearchIndex(root)
    coverage = knowledge_validation(idx)
    modules = []
    paths = list(root.glob("*.py"))
    for directory in ("scripts", "tools", "construction_ingest", "improvements"):
        paths.extend((root / directory).rglob("*.py"))
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        modules.append({"path": path.relative_to(root).as_posix(), "imports": sorted(imports)})
    return {
        "read_only": True, "model_calls": 0, "network_calls": 0,
        "baseline_hash": idx.baseline(),
        "coverage_scope": "baseline files only; active private review overlay not opened",
        "coverage": {key: value for key, value in coverage.items() if key != "families"},
        "research_states": dict(Counter(row["research_status"] for row in coverage["families"])),
        "family_gaps": [{"family_id": row["family_id"], "gaps": row["gaps"]} for row in coverage["families"]],
        "modules": modules,
        "note": "Static imports are not proof of reachability or dead code. No source document contents, "
                "credentials or customer records are included. No files are written.",
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(inventory(), indent=2))
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        print(f"Inventory failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
