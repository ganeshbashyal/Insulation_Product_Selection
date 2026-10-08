"""Explicit local PDF intake with complete pages; candidates never approve facts."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from local_source_review import checked_pages, local_document
from family_knowledge import load_families

CANDIDATE_KINDS = {"identity", "material", "application", "performance", "dimension",
                   "standard", "limitation", "installation", "safety", "warranty", "reference"}


def checked_candidates(item: dict, extraction: dict) -> list[dict]:
    candidates = item.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("Candidates must be a list")
    result = []
    required = {"family_id", "kind", "field", "value", "unit", "variant", "scope",
                "page", "quote", "test_standard", "test_context"}
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != required:
            raise ValueError("Candidate fields must include exact family, typed value and source context")
        if not isinstance(candidate["family_id"], str) or not isinstance(candidate["kind"], str) or candidate["family_id"] not in item["family_ids"] or candidate["kind"] not in CANDIDATE_KINDS:
            raise ValueError("Candidate family/kind is not declared")
        if any(not isinstance(candidate[key], str) for key in
               ("field", "unit", "variant", "scope", "quote", "test_standard", "test_context")):
            raise ValueError("Candidate context must be explicit strings; unknown is not zero")
        if not candidate["field"].strip() or not candidate["quote"].strip():
            raise ValueError("Candidate needs a named field and literal source quotation")
        value = candidate["value"]
        if not isinstance(value, (str, int, float, bool)) or (
                isinstance(value, float) and not math.isfinite(value)):
            raise ValueError("Candidate value must be a finite typed scalar")
        if type(candidate["page"]) is not int or candidate["page"] < 1:
            raise ValueError("Candidate page must be a positive integer")
        text = next((page["text"] for page in extraction["pages"]
                     if page["page"] == candidate["page"]), "")
        if " ".join(candidate["quote"].split()).casefold() not in " ".join(text.split()).casefold():
            raise ValueError("Candidate quotation is not on the declared page")
        result.append({**candidate, "source_sha256": extraction["sha256"],
                       "review_status": "pending_human_review",
                       "source_role": item["role"],
                       "performance_source_gap": candidate["kind"] == "performance" and item["role"] != "tds"})
    return result


def preview(root: Path, manifest_path: Path) -> dict:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_relative_to(root):
        raise ValueError("Intake manifest must be inside this checkout")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if set(manifest) != {"documents"} or not isinstance(manifest["documents"], list) or not manifest["documents"]:
        raise ValueError("Manifest must contain a nonempty documents list")
    families = set(load_families(root))
    records = []
    seen = set()
    for item in manifest["documents"]:
        if not isinstance(item, dict) or not {"path", "family_ids", "role"}.issubset(item) or set(item) - {"path", "family_ids", "role", "candidates"}:
            raise ValueError("Each document needs path, family_ids and role; optional candidates only")
        if not isinstance(item["role"], str) or item["role"] not in {"tds", "sds", "installation", "other"}:
            raise ValueError("Explicit document role required")
        ids = item["family_ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(key, str) or key not in families for key in ids):
            raise ValueError("Every document needs known canonical family IDs")
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate family association")
        if not isinstance(item["path"], str):
            raise ValueError("Document path must be a relative string")
        path = local_document(root, item["path"])
        if path.suffix.casefold() != ".pdf" or not path.is_file():
            raise ValueError("Only existing PDF files in this checkout's source library are accepted")
        if path in seen:
            raise ValueError("Duplicate document path; list all family associations in one row")
        seen.add(path)
        extraction = checked_pages(path)
        candidates = checked_candidates(item, extraction)
        records.append({**item, "path": path.relative_to(root).as_posix(),
                        "association_status": "owner_declared_not_reviewed",
                        "extraction": extraction, "candidates": candidates,
                        "field_coverage": {kind: sum(row["kind"] == kind for row in candidates)
                                           for kind in sorted(CANDIDATE_KINDS)},
                        "coverage_note": "Zero candidates means not captured, never inapplicable or approved."})
    body = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "documents": records, "approval": False, "network_calls": 0, "model_calls": 0,
            "note": "Explicit associations and extracted text are candidates only. Originals and live catalogue unchanged."}
    body["preview_id"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def stage(root: Path, manifest: Path, confirm: str) -> Path:
    data = preview(root, manifest)
    if confirm != data["preview_id"]:
        raise ValueError("Manifest or sources changed, or exact preview ID not confirmed")
    directory = root.resolve() / "data" / "local" / "intake"
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("Intake directory escapes checkout")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (confirm[:16] + ".json")
    if target.exists():
        if json.loads(target.read_text(encoding="utf-8")) != data:
            raise ValueError("Intake receipt prefix collision or modified receipt")
        return target
    with target.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return target
