"""Local rebuild/health dashboard for every ingested artefact.

This module answers one question honestly, for you: "if I re-run the
ingestion scripts, did everything actually rebuild, and does it look
right?" It never calls Ollama or any network resource - it only reads
files and SQLite tables that are already on disk, so it works whether
or not Ollama is running.

Usable two ways:
  1. As a library: ``python -m data_health`` prints a plain-text report.
  2. Imported into app.py to drive the "Data & rebuild status" Streamlit tab.

Each check returns a ``CheckResult`` with a status of "ok", "warn", or
"missing", plus a human note so failures are self-explanatory instead of
just a red dot.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@dataclass
class CheckResult:
    name: str
    status: str  # "ok" | "warn" | "missing"
    detail: str
    last_modified: str | None = None
    extra: dict = field(default_factory=dict)


def _mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _sqlite_table_counts(db_path: Path) -> dict[str, int]:
    """Row count per table. Empty dict if the file is missing or unreadable."""
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            )]
            return {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in tables}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"_error": str(exc)}


def check_family_catalogue(db_path: Path | None = None) -> CheckResult:
    """data/local/family_catalogue.sqlite3: families, variants, installation, SKUs."""
    path = db_path or ROOT / "data" / "local" / "family_catalogue.sqlite3"
    if not path.exists():
        return CheckResult("Family + SKU catalogue", "missing", "family_catalogue.sqlite3 not found - run scripts/build_family_sqlite.py then scripts/ingest_product_master.py.")
    counts = _sqlite_table_counts(path)
    if "_error" in counts:
        return CheckResult("Family + SKU catalogue", "warn", f"File exists but couldn't be read: {counts['_error']}", _mtime(path))
    families = counts.get("families", 0)
    skus = counts.get("product_skus", 0)
    if families == 0:
        return CheckResult("Family + SKU catalogue", "warn", "Table exists but 'families' is empty - rebuild likely failed partway.", _mtime(path), counts)
    status = "ok" if skus > 0 else "warn"
    detail = f"{families} families, {counts.get('family_variants', 0)} variants, {counts.get('family_installation', 0)} installation rows, {skus} SKUs."
    if skus == 0:
        detail += " No SKUs linked yet - run scripts/ingest_product_master.py."
    return CheckResult("Family + SKU catalogue", status, detail, _mtime(path), counts)


def check_postcode_db(db_path: Path | None = None) -> CheckResult:
    """data/construction_postcodes.db: postcode -> NCC climate zone lookups."""
    path = db_path or ROOT / "data" / "construction_postcodes.db"
    if not path.exists():
        return CheckResult("Postcode -> NCC climate zone DB", "missing", "construction_postcodes.db not found - run construction_ingest/db_setup.py.")
    counts = _sqlite_table_counts(path)
    if "_error" in counts:
        return CheckResult("Postcode -> NCC climate zone DB", "warn", f"File exists but couldn't be read: {counts['_error']}", _mtime(path))
    total_rows = sum(v for k, v in counts.items() if not k.startswith("_"))
    status = "ok" if total_rows > 0 else "warn"
    detail = ", ".join(f"{k}: {v}" for k, v in counts.items()) if counts else "No tables found."
    return CheckResult("Postcode -> NCC climate zone DB", status, detail, _mtime(path), counts)


def check_families_json() -> CheckResult:
    """knowledge/*/families.json - the source agent_core.load_families() globs."""
    paths = sorted((ROOT / "knowledge").glob("*/families.json"))
    if not paths:
        return CheckResult("Manufacturer families.json files", "missing", "No knowledge/*/families.json files found.")
    manufacturers = [p.parent.name for p in paths]
    latest = max((p.stat().st_mtime for p in paths), default=0)
    last_modified = datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M:%S") if latest else None
    return CheckResult(
        "Manufacturer families.json files", "ok",
        f"{len(paths)} manufacturer folders with families.json: {', '.join(manufacturers)}.",
        last_modified, {"count": len(paths)},
    )


def check_rag_chunks() -> CheckResult:
    """knowledge/industry/training/*_rag_chunks.jsonl - what the LLM actually retrieves from."""
    training_dir = ROOT / "knowledge" / "industry" / "training"
    paths = sorted(training_dir.glob("*_rag_chunks.jsonl")) if training_dir.exists() else []
    if not paths:
        return CheckResult("RAG retrieval chunks (LLM's live knowledge)", "missing", "No *_rag_chunks.jsonl files in knowledge/industry/training/ - the LLM has no compliance/expert corpus to retrieve from.")
    total_lines = 0
    for p in paths:
        try:
            total_lines += sum(1 for _ in p.open(encoding="utf-8"))
        except OSError:
            pass
    latest = max((p.stat().st_mtime for p in paths), default=0)
    last_modified = datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M:%S") if latest else None
    names = ", ".join(p.name for p in paths)
    return CheckResult(
        "RAG retrieval chunks (LLM's live knowledge)", "ok",
        f"{len(paths)} files ({names}), {total_lines} total chunk lines.",
        last_modified, {"files": len(paths), "chunks": total_lines},
    )


def check_tds_pdfs() -> CheckResult:
    """data/tds/ - raw manufacturer TDS PDFs, the source for local_pdf_parser.py."""
    tds_dir = ROOT / "data" / "tds"
    if not tds_dir.exists():
        return CheckResult("Raw TDS PDFs (data/tds/)", "missing", "data/tds/ folder does not exist.")
    pdfs = list(tds_dir.glob("*.pdf"))
    if not pdfs:
        return CheckResult("Raw TDS PDFs (data/tds/)", "warn", "Folder exists but has no PDFs - local_pdf_parser.py has nothing to parse. This is expected if you're relying on the structured xlsx/JSON path instead.")
    return CheckResult("Raw TDS PDFs (data/tds/)", "ok", f"{len(pdfs)} PDF(s) present.", _mtime(tds_dir), {"count": len(pdfs)})


def check_product_knowledge_json() -> CheckResult:
    """data/product_knowledge.json - output of local_pdf_parser.py's Ollama extraction."""
    path = ROOT / "data" / "product_knowledge.json"
    status_path = ROOT / "data" / "product_knowledge_status.json"
    if not path.exists():
        return CheckResult("product_knowledge.json (PDF extraction output)", "missing", "Not created yet - run: python -m construction_ingest.local_pdf_parser --pdf-dir data/tds")
    size = path.stat().st_size
    extra = {"size_bytes": size}
    if status_path.exists():
        try:
            summary = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = None
        if summary:
            extra.update(summary)
            detail = (
                f"Last run: {summary.get('pdf_count', 0)} PDF(s) -> "
                f"{summary.get('ok', 0)} ok (llm), {summary.get('regex_only', 0)} regex-only, "
                f"{summary.get('warnings', 0)} with warnings (model: {summary.get('model', '?')})."
            )
            status = "warn" if summary.get("warnings") or not summary.get("pdf_count") else "ok"
            return CheckResult("product_knowledge.json (PDF extraction output)", status, detail, _mtime(path), extra)
    if size < 2048:
        return CheckResult("product_knowledge.json (PDF extraction output)", "warn", f"File exists but is only {size} bytes - looks like a stub/placeholder, not a real extraction run.", _mtime(path), extra)
    return CheckResult("product_knowledge.json (PDF extraction output)", "ok", f"{size} bytes.", _mtime(path), extra)


def check_master_workbook() -> CheckResult:
    """data/raw/*.xlsx - the source MYOB SKU workbook that feeds ingest_product_master.py."""
    raw_dir = ROOT / "data" / "raw"
    xlsx = list(raw_dir.glob("*.xlsx")) if raw_dir.exists() else []
    if not xlsx:
        return CheckResult("Master SKU workbook (data/raw/*.xlsx)", "missing", "No .xlsx source file in data/raw/ - ingest_product_master.py has nothing to ingest.")
    latest = max(xlsx, key=lambda p: p.stat().st_mtime)
    return CheckResult("Master SKU workbook (data/raw/*.xlsx)", "ok", f"Found: {latest.name}", _mtime(latest), {"count": len(xlsx)})


def check_gold_labels() -> CheckResult:
    """data/local/gold_labels_todo.csv - blocks the hybrid-wiring todo until labelled."""
    path = ROOT / "data" / "local" / "gold_labels_todo.csv"
    if not path.exists():
        return CheckResult("Gold label CSV (hybrid ranker validation)", "missing", "Not created yet - run scripts/build_gold_label_template.py.")
    try:
        lines = sum(1 for _ in path.open(encoding="utf-8")) - 1  # minus header
    except OSError:
        lines = -1
    return CheckResult("Gold label CSV (hybrid ranker validation)", "warn", f"{max(lines, 0)} rows present. hybrid-wiring stays off until you confirm these are labelled.", _mtime(path), {"rows": lines})


ALL_CHECKS = [
    check_master_workbook,
    check_family_catalogue,
    check_families_json,
    check_rag_chunks,
    check_postcode_db,
    check_tds_pdfs,
    check_product_knowledge_json,
    check_gold_labels,
]


def run_all() -> list[CheckResult]:
    return [check() for check in ALL_CHECKS]


def _status_icon(status: str) -> str:
    return {"ok": "OK", "warn": "WARN", "missing": "MISSING"}.get(status, "?")


def print_report() -> None:
    for result in run_all():
        print(f"[{_status_icon(result.status)}] {result.name}")
        print(f"    {result.detail}")
        if result.last_modified:
            print(f"    last modified: {result.last_modified}")
        print()


if __name__ == "__main__":
    print_report()
