"""Compare structured family facts with hash-bound local source pages and literature."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from local_source_review import checked_pages, file_hash, local_document
from product_research import ResearchIndex
from research_store import canonical

OUTPUT = ROOT / "data" / "local" / "family_tds_transcription_check"
GAP_REPORT = ROOT / "data" / "local" / "family_data_gathering" / "literature_gap_triage.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_sha256(root: Path, relative: str | None) -> str | None:
    if not relative:
        return None
    path = Path(str(relative).replace("\\", "/"))
    if path.is_absolute():
        return None
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        return None
    return _sha256(resolved)


def _signature(families: list[dict], input_files: dict[str, str | None]) -> str:
    return hashlib.sha256(canonical({
        "families": [{key: row[key] for key in
                      ("family_id", "status", "facts_checked", "facts_exact_in_pdf",
                       "facts_exact_in_literature", "flags", "documents", "family_literature",
                       "authoring_inputs", "facts")} for row in families],
        "input_files": input_files,
    }).encode("utf-8")).hexdigest()


def read_current_report(root: Path = ROOT) -> dict:
    root = root.resolve()
    path = root / "data" / "local" / "family_tds_transcription_check.json"
    if not path.is_file():
        raise FileNotFoundError("Run scripts\\check_family_transcription.py to create the audit report")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("report_signature") != _signature(report.get("families", []), report.get("input_files", {})):
        raise ValueError("Transcription audit report signature is invalid; regenerate it")
    stale = []
    for relative, expected in report.get("input_files", {}).items():
        current = _input_sha256(root, relative)
        if current != expected:
            stale.append(relative)
    if stale:
        raise ValueError("Transcription audit inputs changed; regenerate the report: " + ", ".join(stale[:10]))
    return report


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in value if char.isalnum())


def _fact_values(research: dict) -> list[dict]:
    spec = research.get("spec") if isinstance(research, dict) else None
    if not isinstance(spec, dict):
        return []
    result = []

    def add(path: str, value):
        if isinstance(value, str):
            text = value.strip()
            if text and not re.search(r"(?:[$€£]\s*\d|\b(?:AUD|USD|NZD|EUR)\s*\d)", text, re.I):
                result.append({"field": path, "text": text})
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            result.append({"field": path, "text": str(value)})
        elif isinstance(value, list):
            for position, item in enumerate(value):
                add(f"{path}[{position}]", item)

    for key in (
        "description", "features", "applications", "fire", "sustainability",
        "install", "clearances", "limitations", "compliance", "warranty",
    ):
        add("spec." + key, spec.get(key))
    for position, row in enumerate(spec.get("technical", []) or []):
        if not isinstance(row, dict):
            continue
        for key in ("value", "standard"):
            add(f"spec.technical[{position}].{key}", row.get(key))
    return result


def _current_page_text(root: Path, doc: dict, extraction_cache: dict) -> dict:
    relative = doc.get("path")
    declared_hash = doc.get("sha256")
    if not relative:
        return {"state": "no_local_path", "pages": []}
    try:
        path = local_document(root, relative)
    except (ValueError, OSError):
        return {"state": "path_outside_local_library", "pages": []}
    if not path.is_file():
        return {"state": "missing_local_file", "pages": []}
    current_hash = file_hash(path)
    if not declared_hash or current_hash != declared_hash or doc.get("manifest_hash_matches") is False:
        return {"state": "source_hash_mismatch_or_missing", "current_sha256": current_hash, "pages": []}
    if path.suffix.casefold() != ".pdf":
        return {"state": "non_pdf_needs_locator_review", "current_sha256": current_hash, "pages": []}

    key = path.relative_to(root).as_posix()
    cached = extraction_cache.get(key)
    if isinstance(cached, dict) and cached.get("sha256") == current_hash:
        extraction = cached
    else:
        try:
            extraction = checked_pages(path, declared_hash)
        except (OSError, ValueError) as exc:
            return {"state": "page_extraction_failed", "current_sha256": current_hash,
                    "error": str(exc), "pages": []}
    pages = extraction.get("pages", [])
    if extraction.get("status") == "read_error" or not pages:
        return {"state": "page_extraction_failed", "current_sha256": current_hash,
                "error": extraction.get("error", "No pages extracted"), "pages": []}
    return {
        "state": "text_incomplete" if extraction.get("status") != "text_extracted" else "text_extracted",
        "current_sha256": current_hash,
        "pages": [{"page": page.get("page"), "text": page.get("text", ""),
                   "normalised": _normalise(page.get("text", ""))}
                  for page in pages],
    }


def _match_fact(text: str, usable_documents: list[dict]) -> list[dict]:
    needle = _normalise(text)
    if len(needle) < 4:
        return []
    matches = []
    for document in usable_documents:
        pages = [page["page"] for page in document["pages"]
                 if needle in page["normalised"]]
        if pages:
            matches.append({
                "path": document["path"],
                "sha256": document["sha256"],
                "pages": sorted(set(pages)),
            })
    return matches


def build_report(root: Path = ROOT) -> dict:
    root = root.resolve()
    index = ResearchIndex(root)
    extraction_cache_path = root / "data" / "local" / "source_review.json"
    extraction_cache = {}
    if extraction_cache_path.is_file():
        cached = json.loads(extraction_cache_path.read_text(encoding="utf-8-sig"))
        extraction_cache = cached.get("documents", {})

    gap_report = {}
    if GAP_REPORT.is_file():
        gap_report = json.loads(GAP_REPORT.read_text(encoding="utf-8-sig"))
    gap_by_family = {
        row.get("family_id"): row for row in gap_report.get("families", [])
        if isinstance(row, dict) and isinstance(row.get("family_id"), str)
    }
    families = []
    input_files: dict[str, str | None] = {}
    for path in (GAP_REPORT, extraction_cache_path):
        if path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
            input_files[relative] = _input_sha256(root, relative)
    for family_id, family in index.families.items():
        detail = index.detail(family_id)
        research = detail.get("research") or {}
        source_info = index.sources.family(family_id, include_compiled=False)
        authoring_inputs = []
        for relative in (source_info.get("research_path"), source_info.get("guide")):
            if not relative:
                continue
            digest = _input_sha256(root, relative)
            authoring_inputs.append({"path": relative, "sha256": digest})
            input_files[relative] = digest
        documents = []
        seen = set()
        for source in source_info.get("documents", []):
            key = (source.get("path") or "", source.get("sha256") or "")
            if key in seen:
                continue
            seen.add(key)
            extracted = _current_page_text(root, source, extraction_cache)
            doc = {
                "path": source.get("path"),
                "sha256": source.get("sha256"),
                "exists": bool(source.get("exists")),
                "manifest_hash_matches": source.get("manifest_hash_matches"),
                "extraction_state": extracted["state"],
                "current_sha256": extracted.get("current_sha256"),
                "error": extracted.get("error"),
                "pages": extracted.get("pages", []),
            }
            documents.append(doc)
            if source.get("path"):
                input_files[source["path"]] = extracted.get("current_sha256")

        literature = detail.get("derived_literature") or {}
        literature_files = []
        for relative, content in literature.items():
            path = root / relative
            if path.is_file():
                literature_files.append({
                    "path": relative,
                    "sha256": file_hash(path),
                    "normalised": _normalise(content),
                })
                input_files[relative] = literature_files[-1]["sha256"]
        hash_bound_pdfs = [doc for doc in documents
                           if str(doc.get("path") or "").casefold().endswith(".pdf")
                           and doc.get("current_sha256") == doc.get("sha256")
                           and doc.get("manifest_hash_matches") is not False
                           and doc.get("pages")]
        matchable_pdfs = [doc for doc in hash_bound_pdfs
                          if doc.get("extraction_state") == "text_extracted"]
        facts = []
        for candidate in _fact_values(research):
            literature_match = any(
                _normalise(candidate["text"]) in item["normalised"]
                for item in literature_files if len(_normalise(candidate["text"])) >= 4
            )
            matches = _match_fact(candidate["text"], matchable_pdfs)
            facts.append({
                **candidate,
                "exact_in_family_literature": literature_match,
                "exact_hash_bound_pdf_matches": matches,
                "status": ("provisional_internal_transcription_match" if literature_match and matches
                           else "literature_missing_exact_fact" if matches
                           else "source_exact_text_not_found"),
            })

        gap = gap_by_family.get(family_id, {})
        extraction_issues = sorted({doc["extraction_state"] for doc in documents
                                    if doc["extraction_state"] != "text_extracted"})
        family_flags = []
        if not hash_bound_pdfs and not documents:
            family_flags.append("no_hash_bound_local_pdf")
        if not hash_bound_pdfs and any(doc.get("exists") for doc in documents):
            family_flags.append("non_pdf_source_needs_manual_locator")
        if extraction_issues:
            family_flags.extend("source_" + issue for issue in extraction_issues)
        exact_matches = sum(row["status"] == "provisional_internal_transcription_match" for row in facts)
        needs_review = sum(row["status"] != "provisional_internal_transcription_match" for row in facts)
        absent_from_literature = sum(not row["exact_in_family_literature"] for row in facts)
        if needs_review:
            family_flags.append("facts_not_exactly_found_in_source_text")
        if absent_from_literature:
            family_flags.append("facts_not_found_in_generated_family_literature")
        if gap:
            family_flags.append("listed_in_literature_gap_triage")
        if facts and matchable_pdfs and needs_review == 0 and not extraction_issues:
            status = "provisional_transcription_match_candidate"
        elif exact_matches:
            status = "partial_exact_matches_flagged"
        elif not documents or not any(doc.get("exists") for doc in documents):
            status = "no_hash_bound_local_source"
        else:
            status = "flagged_for_review"
        families.append({
            "family_id": family_id,
            "family_name": family.get("name", family_id),
            "manufacturer": family.get("manufacturer", ""),
            "status": status,
            "facts_checked": len(facts),
            "facts_exact_in_pdf": sum(bool(row["exact_hash_bound_pdf_matches"]) for row in facts),
            "facts_exact_in_literature": sum(row["exact_in_family_literature"] for row in facts),
            "facts_provisional_internal_match": exact_matches,
            "facts_needing_review": needs_review,
            "linked_document_count": len(documents),
            "hash_bound_pdf_count": len(hash_bound_pdfs),
            "source_extraction_issues": extraction_issues,
            "literature_gap": {
                "status": gap.get("literature_status"),
                "source_review_status": gap.get("source_review_status"),
                "linked_documents": gap.get("linked_documents", []),
                "local_pdf_retrieval_leads": gap.get("local_pdf_retrieval_leads", []),
            } if gap else None,
            "flags": family_flags,
            "documents": [{key: value for key, value in doc.items() if key != "pages"}
                          for doc in documents],
            "family_literature": [
                {"path": row["path"], "sha256": row["sha256"]} for row in literature_files
            ],
            "authoring_inputs": authoring_inputs,
            "facts": facts,
        })

    state_counts = {}
    for family in families:
        state_counts[family["status"]] = state_counts.get(family["status"], 0) + 1
    fact_rows = sum(row["facts_checked"] for row in families)
    families.sort(key=lambda row: (
        row["status"] == "provisional_transcription_match_candidate",
        row["manufacturer"].casefold(), row["family_name"].casefold(), row["family_id"],
    ))
    signature = _signature(families, input_files)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_policy": "exact_text_transcription_check_only_provisional_internal_candidate",
        "auto_approval": False,
        "canonical_data_changed": False,
        "source_binding_changed": False,
        "claim_approval_changed": False,
        "publication_changed": False,
        "external_network_or_model_calls": False,
        "input_files": input_files,
        "report_signature": signature,
        "family_count": len(families),
        "family_status_counts": state_counts,
        "fact_count": fact_rows,
        "provisional_internal_transcription_match_count": sum(
            row["status"] == "provisional_internal_transcription_match"
            for family in families for row in family["facts"]),
        "fact_review_count": sum(
            row["status"] != "provisional_internal_transcription_match"
            for family in families for row in family["facts"]),
        "families_with_literature_gap": sum(row["literature_gap"] is not None for row in families),
        "families": families,
        "limitations": [
            "An exact text match checks transcription, not whether a source is authentic, current, complete, or applicable.",
            "Only family-linked local PDFs with matching recorded hashes are used for exact source matches.",
            "A text non-match is a review flag; paraphrase, table structure, OCR, or extraction gaps may explain it.",
            "No family is technically, commercially, compliance, customer-suitability, or publication approved by this report.",
            "Catalogue range and SKU-derived values are not treated as TDS facts in this check.",
        ],
    }


def write_report(report: dict, output_base: Path = OUTPUT) -> tuple[Path, Path]:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_base.with_suffix(".json")
    markdown_path = output_base.with_suffix(".md")
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    json_path.write_text(content, encoding="utf-8", newline="\n")

    lines = [
        "# Local TDS transcription check",
        "",
        "**PRIVATE INTERNAL TRIAGE — NOT TECHNICAL, COMPLIANCE, CUSTOMER OR PUBLIC APPROVAL.**",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Families checked: **{report['family_count']}**",
        f"- Family states: `{json.dumps(report['family_status_counts'], sort_keys=True)}`",
        f"- Structured fact fields checked: **{report['fact_count']}**",
        f"- Exact fact/source/literature matches (provisional internal transcription only): **{report['provisional_internal_transcription_match_count']}**",
        f"- Fact fields needing review: **{report['fact_review_count']}**",
        f"- Families present in the 40-gap triage: **{report['families_with_literature_gap']}**",
        f"- Report signature: `{report['report_signature']}`",
        "",
        "The check compares structured family research facts with generated family literature and exact text on hash-matched, family-linked local PDF pages. It makes no source-authenticity or applicability determination and changes no canonical data.",
        "",
        "| Family | Status | Exact / checked (PDF) | Exact / checked (literature) | Source PDFs | Flags |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report["families"]:
        lines.append(
            f"| {row['family_name']} (`{row['family_id']}`) | `{row['status']}` | "
            f"{row['facts_exact_in_pdf']} / {row['facts_checked']} | "
            f"{row['facts_exact_in_literature']} / {row['facts_checked']} "
            f"(provisional matches {row['facts_provisional_internal_match']}) | "
            f"{row['hash_bound_pdf_count']} | {', '.join(row['flags']) or 'none'} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {text}" for text in report["limitations"])
    lines.extend(["", "Full field-level results and exact page locators are in the adjacent JSON report.", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return json_path, markdown_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-base", type=Path, default=OUTPUT,
                        help="Private local output path without a file extension")
    args = parser.parse_args(argv)
    report = build_report()
    json_path, markdown_path = write_report(report, args.output_base)
    print(json.dumps({
        "state": "complete_with_flags",
        "family_count": report["family_count"],
        "family_status_counts": report["family_status_counts"],
        "fact_count": report["fact_count"],
        "provisional_internal_transcription_match_count": report["provisional_internal_transcription_match_count"],
        "fact_review_count": report["fact_review_count"],
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "report_signature": report["report_signature"],
        "auto_approval": False,
        "canonical_data_changed": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
