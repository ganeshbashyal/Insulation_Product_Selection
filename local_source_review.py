"""Local-only provenance and complete-page extraction; never approves evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from functools import lru_cache
import os
import uuid
from importlib.metadata import version

from family_knowledge import load_families, load_research

ROOT = Path(__file__).resolve().parent
AUDIT_PATH = ROOT / "data" / "local" / "source_review.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_document(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not any(
        path.is_relative_to((root / directory).resolve()) for directory in ("data", "evidence/raw")
    ):
        raise ValueError(f"Source document is outside the local source library: {value}")
    return path


def extract_pages(path: Path) -> dict:
    """Keep all pages and identify blank pages; no 12-page/16K cutoff."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    checksum = None
    try:
        checksum = file_hash(path)
        reader = PdfReader(path)
    except (PdfReadError, OSError, ValueError) as exc:
        return {"sha256": checksum, "status": "read_error", "error": str(exc), "pages": [], "review_status": "pending_human_review"}
    pages, errors = [], []
    for number, page in enumerate(reader.pages, 1):
        try:
            pages.append({"page": number, "text": page.extract_text() or ""})
        except (PdfReadError, ValueError, KeyError) as exc:
            pages.append({"page": number, "text": ""})
            errors.append({"page": number, "error": str(exc)})
    text = "\n".join(page["text"] for page in pages)
    roles = []
    for role, pattern in (
        ("safety_data", r"\b(?:safety data sheet|material safety data sheet|hazard identification)\b"),
        ("installation", r"\b(?:installation guide|installation instructions|fixing|air\s*space|clearance)\b"),
        ("technical_data", r"\b(?:technical data|product data|thermal resistance|conductivity)\b"),
    ):
        if re.search(pattern, text, re.I):
            roles.append(role)
    blank = [page["page"] for page in pages if not page["text"].strip()]
    return {
        "sha256": checksum, "status": "text_incomplete" if blank else "text_extracted",
        "page_count": len(pages), "blank_pages": blank, "pages": pages,
        "page_errors": errors,
        "detected_roles": roles, "role_status": "heuristic_requires_review",
        "review_status": "pending_human_review", "truncated": False,
    }


@lru_cache(maxsize=64)
def _cached_pages(path: str, checksum: str, parser: str) -> str:
    result = extract_pages(Path(path))
    result["parser"] = parser
    if result["sha256"] != checksum or file_hash(Path(path)) != checksum:
        raise ValueError("Source changed during extraction; refresh and retry")
    return json.dumps(result)


def checked_pages(path: Path, expected_hash: str | None = None) -> dict:
    checksum = file_hash(path)
    if expected_hash is not None and checksum != expected_hash:
        raise ValueError("Source hash changed; refresh before reading pages")
    parser = "full-pages-v1/pypdf-" + version("pypdf")
    result = json.loads(_cached_pages(str(path.resolve()), checksum, parser))
    if file_hash(path) != checksum:
        raise ValueError("Source changed while reading cached pages; refresh and retry")
    return result


def retain_review(report: dict, output: Path) -> dict:
    """Keep immutable audit receipts before updating the compatibility pointer."""
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    identifier = hashlib.sha256(content.encode("utf-8")).hexdigest()
    history = output.parent / "source_reviews"
    history.mkdir(parents=True, exist_ok=True)
    if output.is_file():
        previous = output.read_bytes()
        old = history / (hashlib.sha256(previous).hexdigest()[:16] + ".json")
        if old.exists() and old.read_bytes() != previous:
            raise ValueError("Source review receipt prefix collision")
        if not old.exists():
            with old.open("xb") as handle:
                handle.write(previous)
    receipt = history / (identifier[:16] + ".json")
    if receipt.exists() and receipt.read_text(encoding="utf-8") != content:
        raise ValueError("Source review receipt prefix collision")
    if not receipt.exists():
        with receipt.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    temporary = output.with_name("audit-" + uuid.uuid4().hex[:8] + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"review_id": identifier, "receipt": str(receipt), "output": str(output)}


class SourceReview:
    def __init__(self, root: Path = ROOT):
        self.root = root
        audit_path = root / "data" / "local" / "source_review.json"
        self.audit = read_json(audit_path).get("documents", {}) if audit_path.is_file() else {}
        self.intake = {}
        for path in sorted((root / "data" / "local" / "intake").glob("*.json")):
            staged = read_json(path)
            for document in staged["documents"]:
                for key in document["family_ids"]:
                    self.intake.setdefault(key, []).append(document)
                self.audit.setdefault(document["path"], document["extraction"])
        self.manifest = read_json(root / "knowledge" / "_tds_manifest.json")
        self.research = load_research(root)
        self.guides = {}
        for path in root.glob("knowledge/*/families.json"):
            for family in read_json(path)["families"]:
                name = family.get("knowledge_file")
                if name:
                    guide = (path.parent / name).resolve()
                    if not guide.is_relative_to(path.parent.resolve()):
                        raise ValueError("Family guide escapes manufacturer directory")
                    if guide.is_file():
                        self.guides[family["family_id"]] = guide

    def documents(self, family_id: str) -> list[dict]:
        record = self.research.get(family_id, {})
        manifest = self.manifest.get(family_id, {})
        paths = [manifest.get("path"), record.get("datasheet_local_path")]
        paths.extend(item["path"] for item in self.intake.get(family_id, []))
        documents = []
        for value in dict.fromkeys(value for value in paths if value):
            path = local_document(self.root, value)
            item = {"path": path.relative_to(self.root).as_posix(), "exists": path.is_file()}
            declared = [row for row in self.intake.get(family_id, []) if row["path"] == item["path"]]
            if declared:
                item["association_status"] = "owner_declared_not_reviewed"
                item["declared_roles"] = sorted({row["role"] for row in declared})
            if path.is_file():
                item["sha256"] = file_hash(path)
                item["manifest_hash_matches"] = item["sha256"] == manifest.get("sha256") if manifest.get("path") == value else None
                review = self.audit.get(item["path"], {})
                if review.get("sha256") != item["sha256"]:
                    review = next((row["extraction"] for row in declared
                                   if row["extraction"]["sha256"] == item["sha256"]), review)
                if review.get("sha256") == item["sha256"]:
                    item["extraction"] = {key: review.get(key) for key in ("status", "page_count", "blank_pages", "page_errors", "detected_roles", "review_status")}
                    item["text_locator"] = {"report": "data/local/source_review.json", "document": item["path"], "pages": "all"}
                else:
                    item["extraction"] = {"status": "not_audited_or_changed"}
            if declared:
                item["candidate_fields"] = [
                    {**candidate, "source_current": item.get("sha256") == candidate["source_sha256"]}
                    for row in declared for candidate in row.get("candidates", [])
                    if candidate["family_id"] == family_id
                ]
            documents.append(item)
        return documents

    def family(self, family_id: str, *, include_compiled: bool = False) -> dict:
        record = self.research.get(family_id, {})
        spec = record.get("spec") or {}
        guide = self.guides.get(family_id)
        checks = []
        if guide:
            text = guide.read_text(encoding="utf-8-sig")
            for block in re.findall(r"```json\s*(.*?)```", text, re.S):
                parsed = json.loads(block)
                checks.extend(parsed.get("required_inputs", []))
                checks.extend(parsed.get("human_gates", []))
        documents = self.documents(family_id)
        from tds_register import compiled_sources
        compiled = (compiled_sources(self.root, family_id) if include_compiled
                    else {"state": "not_compiled", "sources": []})
        cached_primary = (compiled["state"] == "compiled" and
                          any(row.get("file_current") for row in compiled["sources"]))
        gaps = []
        if not any(doc["exists"] for doc in documents) and not cached_primary:
            gaps.append("No family-linked local primary PDF; a URL is not ingested evidence.")
        if any(doc.get("manifest_hash_matches") is False for doc in documents):
            gaps.append("Primary file hash differs from its provenance manifest; source integrity requires review.")
        if any(doc.get("extraction", {}).get("status") != "text_extracted" for doc in documents if doc["exists"]):
            gaps.append("Full-page extraction is missing, incomplete or unreadable; review source pages before use.")
        if any(doc["extraction_status"] != "text_extracted" for doc in compiled.get("documents", [])):
            gaps.append("Cached primary extraction has gaps; original document remains retained for review.")
        if compiled["state"] == "stale":
            gaps.append("Compiled cache source snapshot is stale; refresh before relying on its provenance.")
        for key in ("install", "clearances", "limitations"):
            if not spec.get(key):
                gaps.append(f"No extracted {key} information; absence is not proof of no requirements.")
        if not any("safety_data" in (doc.get("extraction", {}).get("detected_roles") or []) for doc in documents):
            gaps.append("No family-linked local document identified as safety data; an SDS URL does not establish ingestion.")
        result = {
            "research_path": record.get("_path"), "research_status": record.get("status", "missing"),
            "engine": record.get("engine", "unspecified"),
            "review_status": "pending_human_review",
            "documents": documents, "source_gaps": gaps,
            "guide": guide.relative_to(self.root).as_posix() if guide else None,
            "guide_checks": sorted(set(checks)),
            "extracted_checks": {
                key: [{"text": str(value), "source": record.get("_path"), "locator": "spec." + key,
                       "status": "unreviewed_extraction_not_installation_advice"} for value in spec.get(key, [])]
                for key in ("install", "clearances", "limitations")
            },
        }
        if include_compiled:
            result["compiled_sources"] = compiled
        return result


def build_review(root: Path = ROOT) -> dict:
    sources = SourceReview(root)
    documents = {}
    paths = {path for directory in ("data/tds", "data/tds_inbox", "evidence/raw")
             for path in (root / directory).rglob("*.pdf")}
    paths.update(root / row["path"] for entries in sources.intake.values() for row in entries)
    for path in sorted(paths):
        if path.is_file():
            path = local_document(root, str(path.relative_to(root)))
            documents[path.relative_to(root).as_posix()] = checked_pages(path)
    sources.audit = documents
    return {
        "review_status": "pending_human_review", "auto_approval": False,
        "documents": documents,
        "families": {key: sources.family(key) for key in load_families(root)},
        "note": "Full-page text is unreviewed; scans need OCR/manual review. Document roles are content heuristics, not certification.",
    }
