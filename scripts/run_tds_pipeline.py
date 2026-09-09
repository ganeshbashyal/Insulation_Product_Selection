"""End-to-end TDS pipeline: download -> verify family match -> extract via Ollama.

Designed to run unattended, independent of any editor/session - launch it as a
detached background process and it keeps working even if VS Code is closed.
Every step writes its own status file to data/local/ or data/, so progress can
be checked at any time just by reading those files (see data_health.py for a
one-shot summary).

Steps
-----
1. Recompile the TDS URL review CSV from knowledge/*/families.json (cheap,
   keeps it in sync with any families.json edits).
2. Download every PDF matching --tier/--domain-type (default: primary tier,
   both manufacturer and third-party domains - i.e. every deduped, unique
   candidate URL). Already-downloaded files are skipped, not re-fetched.
3. Verify each downloaded PDF's text plausibly matches the family it was
   fetched for (construction_ingest.verify_family_match). PDFs that fail this
   check are EXCLUDED from extraction and listed separately for human review
   - a third-party host is not enough to trust a document, the content has to
   actually back up the family it claims to be.
4. Run the Ollama extraction pipeline (construction_ingest.local_pdf_parser)
   only over the confirmed-match PDFs, writing data/product_knowledge.json.

Usage
-----
    python -m scripts.run_tds_pipeline
    python -m scripts.run_tds_pipeline --domain-type manufacturer_domain
    python -m scripts.run_tds_pipeline --model llama3.2

Exit codes: 0 = clean (all confirmed PDFs extracted, nothing needs review),
2 = ran but some PDFs are excluded pending human review or had extraction
warnings, 1 = nothing to do / hard failure.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.compile_tds_url_list import main as compile_url_list  # noqa: E402
from scripts.download_tds_pdfs import run as download_pdfs  # noqa: E402
from construction_ingest.verify_family_match import verify_batch, write_report  # noqa: E402
from construction_ingest.local_pdf_parser import (  # noqa: E402
    OLLAMA_MODEL,
    ollama_available,
    parse_pdf,
    ProductKnowledge,
)

REVIEW_CSV = ROOT / "data" / "local" / "tds_url_review.csv"
VERIFICATION_REPORT = ROOT / "data" / "local" / "tds_family_verification.json"
PIPELINE_STATUS = ROOT / "data" / "local" / "tds_pipeline_status.json"
PRODUCT_KNOWLEDGE_OUTPUT = ROOT / "data" / "product_knowledge.json"
TDS_DIR = ROOT / "data" / "tds"


def _log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def run_pipeline(
    tier: str = "primary",
    domain_type: str = "all",
    model: str = OLLAMA_MODEL,
    use_llm: bool = True,
    delay: float = 1.5,
) -> int:
    _log("Step 1/4: recompiling TDS URL review CSV from knowledge/*/families.json ...")
    compile_url_list()

    _log(f"Step 2/4: downloading PDFs (tier={tier}, domain_type={domain_type}, existing files skipped) ...")
    download_pdfs(
        csv_path=REVIEW_CSV,
        out_dir=TDS_DIR,
        tier=tier,
        domain_type=domain_type,
        delay=delay,
        skip_existing=True,
    )

    _log("Step 3/4: verifying each downloaded PDF matches its expected family ...")
    with REVIEW_CSV.open(newline="", encoding="utf-8") as fh:
        rows_by_family = {row["family_id"]: row for row in csv.DictReader(fh)}

    items = []
    for pdf_path in sorted(TDS_DIR.rglob("*.pdf")):
        row = rows_by_family.get(pdf_path.stem)
        if row is None:
            continue
        items.append({
            "family_id": row["family_id"],
            "manufacturer": row["manufacturer"],
            "family_name": row["family_name"],
            "pdf_path": str(pdf_path),
        })

    verification_results = verify_batch(items)
    write_report(verification_results, VERIFICATION_REPORT)

    confirmed = [r for r in verification_results if r.match_status == "confirmed"]
    excluded = [r for r in verification_results if r.match_status != "confirmed"]
    _log(f"  {len(confirmed)} confirmed, {len(excluded)} excluded pending human review (see {VERIFICATION_REPORT.name}).")
    for r in excluded:
        _log(f"    [EXCLUDED] {r.family_id}: {r.detail}")

    if use_llm and not ollama_available():
        _log(f"  ! Ollama not reachable - falling back to regex-only extraction for all confirmed PDFs.")
        use_llm = False

    _log(f"Step 4/4: extracting {len(confirmed)} confirmed PDF(s) via {'Ollama ' + model if use_llm else 'regex only'} ...")
    records = []
    for index, r in enumerate(confirmed, start=1):
        try:
            record = parse_pdf(Path(r.pdf_path), model=model, use_llm=use_llm)
        except Exception as error:  # noqa: BLE001 - one bad PDF must never abort the whole batch
            from construction_ingest.local_pdf_parser import ProductRecord  # noqa: PLC0415
            record = ProductRecord(
                product_name=Path(r.pdf_path).stem.replace("_", " ").title(),
                source_pdf=r.pdf_path,
                extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                extraction_method="regex",
                extraction_warnings=[f"unexpected {type(error).__name__}: {error}"],
            )
        tag = "[OK]" if not record.extraction_warnings else "[WARN]"
        _log(f"  [{index}/{len(confirmed)}] {tag} {r.family_id} ({record.extraction_method})")
        records.append(record)

    document = ProductKnowledge(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=model if use_llm else "regex-only",
        source_directory=str(TDS_DIR),
        pdf_count=len(confirmed),
        products=records,
    )
    PRODUCT_KNOWLEDGE_OUTPUT.write_text(document.model_dump_json(indent=2), encoding="utf-8")

    extraction_warnings = sum(1 for rec in records if rec.extraction_warnings)
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": tier,
        "domain_type": domain_type,
        "model": model if use_llm else "regex-only",
        "pdfs_on_disk": len(items),
        "confirmed_match": len(confirmed),
        "excluded_pending_review": len(excluded),
        "extracted_ok": len(records) - extraction_warnings,
        "extracted_with_warnings": extraction_warnings,
        "excluded_family_ids": [r.family_id for r in excluded],
    }
    PIPELINE_STATUS.write_text(json.dumps(status, indent=2), encoding="utf-8")
    _log(f"Done. Wrote {PRODUCT_KNOWLEDGE_OUTPUT.relative_to(ROOT)} and {PIPELINE_STATUS.relative_to(ROOT)}.")

    if not items:
        return 1
    return 2 if excluded or extraction_warnings else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", default="primary", choices=["primary", "duplicate_link", "needs_human_url", "all"])
    parser.add_argument("--domain-type", default="all", choices=["manufacturer_domain", "third_party", "unknown", "all"])
    parser.add_argument("--model", default=OLLAMA_MODEL)
    parser.add_argument("--no-llm", action="store_true", help="regex extraction only, never call Ollama")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args(argv)

    try:
        return run_pipeline(
            tier=args.tier,
            domain_type=args.domain_type,
            model=args.model,
            use_llm=not args.no_llm,
            delay=args.delay,
        )
    except Exception as error:  # noqa: BLE001 - an unattended run must always leave a readable status file
        _log(f"FATAL: pipeline crashed with {type(error).__name__}: {error}")
        PIPELINE_STATUS.parent.mkdir(parents=True, exist_ok=True)
        PIPELINE_STATUS.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outcome": "crashed",
            "error": f"{type(error).__name__}: {error}",
        }, indent=2), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
