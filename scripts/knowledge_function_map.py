"""Static callable references; unresolved/indirect calls are not dead-code proof."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

CONTRACTS = {
    "family_knowledge.py": ("active", "shared explicit-ID readers", "read-only; retained is not approved"),
    "knowledge_service.py": ("active", "GUI/CLI application facade", "explicit stage; named field review"),
    "product_research.py": ("active", "authoring index and family dossier", "read-only; no inference of exact SKU values"),
    "local_source_review.py": ("active", "source integrity/extraction/audit receipts", "unreviewed full-page text"),
    "local_intake.py": ("active", "local owner-declared source intake", "exact preview confirmation; no approvals"),
    "research_api.py": ("active", "private HTTP adapters", "named roles, same-origin CSRF and revisions"),
    "research_workflow.py": ("active", "claim/SKU review and publication", "citations; explicit publisher; unknown dependencies globally held"),
    "research_store.py": ("active", "immutable authoring history", "named account roles and concurrency checks"),
    "authoring_backup.py": ("offline_utility", "private retention", "new destination; checksum verify; no active restored sessions"),
    "scripts/knowledge_workflow.py": ("active", "offline front door", "reads default; exact source-stage confirmation"),
    "scripts/knowledge_function_map.py": ("offline_utility", "static usage inventory", "no deletion or function execution"),
    "scripts/review_local_sources.py": ("offline_utility", "audit adapter", "preview default; confirm-write retains history"),
    "scripts/build_missing_tds_report.py": ("offline_utility", "canonical missing-source report", "preview; preserve manual columns and unresolved history"),
    "scripts/enrich_knowledge_docs.py": ("offline_utility", "draft guide projections", "preview; explicit write; manual marker boundary"),
    "scripts/generate_family_literature.py": ("offline_utility", "draft literature", "explicit write; not primary or public reviewed evidence"),
    "scripts/build_retrieval_cards.py": ("offline_utility", "draft retrieval or explicit legacy profile", "preview; not primary claim proof"),
    "scripts/tds_research_agent.py": ("legacy_network_capable", "optional research producer", "not in offline workflow; may download and invoke models"),
    "scripts/run_tds_pipeline.py": ("legacy_network_capable", "optional download pipeline", "no-llm is NOT no-network"),
    "scripts/research_next_family.py": ("legacy_network_capable", "optional research subprocess", "not a completion authority"),
    "scripts/ingest_tds_inbox.py": ("legacy_writer", "filename-match source suggestions", "not governed intake; explicit source review required"),
    "scripts/relink_shared_datasheets.py": ("legacy_writer", "hard-coded source associations", "retain history; no automatic execution"),
    "scripts/inject_range_data.py": ("retained_reference", "surviving supplied range tables", "not disposable; no automatic rewrite"),
    "scripts/ingest_knowledge_base_txt.py": ("legacy_writer", "supplied text parser", "not claim approval; preserve retained inputs"),
    "scripts/build_family_sqlite.py": ("legacy_projection", "raw authoring SQLite", "optional legacy store, not current release readiness"),
    "scripts/ingest_product_master.py": ("legacy_writer", "heuristic commercial importer", "new governed updates use catalogue_versions"),
    "catalogue_versions.py": ("active", "versioned commercial input", "exact mapping and activation; new eligibility held"),
    "knowledge_release.py": ("active", "immutable serving payload", "reviewed provenance, site visibility and explicit activation"),
    "release_exports.py": ("active", "current public projections", "activated reviewed release; site-filtered exports"),
    "scripts/build_aircall_pack.py": ("legacy_projection", "baseline voice export", "current public voice exports use release_exports"),
    "scripts/run_local_maintenance.py": ("offline_utility", "bounded local model drafts", "loopback only; proposal/verification/application separate"),
}


def inventory(root: Path = ROOT) -> dict:
    paths = sorted({*root.glob("*.py"), *root.glob("scripts/*.py"),
                    *root.glob("construction_ingest/*.py"), *root.glob("tests/test*.py")})
    trees = {path: ast.parse(path.read_text(encoding="utf-8-sig")) for path in paths}
    references = {}
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else None)
                if name:
                    references.setdefault(name, []).append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    functions = []
    for path, tree in trees.items():
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [ast.unparse(value) for value in node.decorator_list]
            classification, owner, gate = CONTRACTS.get(relative, (
                "test" if relative.startswith("tests/") else "review_required",
                "unresolved current/indirect usage", "do not delete or automatically wire"))
            functions.append({
                "module": relative, "callable": node.name, "line": node.lineno,
                "decorators": decorators, "syntactic_references": references.get(node.name, []),
                "entrypoint": "CLI" if node.name == "main" else "API" if any("router." in d for d in decorators)
                              else "test" if relative.startswith("tests/") else "function_or_indirect",
                "classification": classification, "workflow_owner": owner, "gate": gate,
                "capability_signals": sorted({ast.unparse(call.func) for call in ast.walk(node)
                                             if isinstance(call, ast.Call) and any(
                                                 token in ast.unparse(call.func).casefold()
                                                 for token in ("write", "download", "request", "generate", "subprocess", "publish"))}),
            })
    notebooks = []
    for path in sorted(root.glob("notebooks/*.ipynb")):
        for index, cell in enumerate(json.loads(path.read_text(encoding="utf-8"))["cells"]):
            if cell["cell_type"] == "code":
                text = "".join(cell["source"])
                if "ACTIONS" in text or "run_action" in text or "subprocess" in text:
                    notebooks.append({"path": path.relative_to(root).as_posix(), "cell": index,
                                      "source": text})
    return {"functions": functions, "notebook_entrypoints": notebooks,
            "limits": "Syntactic name matches are candidates, not resolved callers or dead-code evidence. "
                      "Dynamic dispatch, shell and notebook usage must be reviewed. Never deletes or runs functions."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inventory(args.root), indent=2))
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
