"""Family-first view over existing research, sources and child SKU records."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from local_source_review import ROOT, SourceReview, file_hash, read_json
from research_store import canonical
from family_knowledge import load_families, dossier, frontmatter
from openpyxl import load_workbook


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class ResearchIndex:
    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()
        for directory in ("knowledge", "schemas", "reports", "data", "evidence", "output"):
            if not (self.root / directory).resolve().is_relative_to(self.root):
                raise ValueError("Research library directory escapes this worktree")
        for pattern in ("knowledge/**/*.json", "data/processed/*", "reports/*", "data/local/*.json",
                        "data/raw/*.xlsx", "output/literature/**/*.md"):
            if any(not path.resolve().is_relative_to(self.root) for path in self.root.glob(pattern)):
                raise ValueError("Research input escapes this worktree")
        self.sources = SourceReview(self.root)
        self.families = load_families(self.root)
        self.errors = []
        from catalogue_versions import CatalogueLibrary
        self.catalogue_version = CatalogueLibrary(self.root).active_id()
        version_rows = CatalogueLibrary(self.root).active_rows()
        self.skus = version_rows if version_rows is not None else read_csv(self.root / "data" / "processed" / "product_catalogue_skus.csv")
        self.by_sku = {row["sku_record_id"]: row for row in self.skus}
        if len(self.by_sku) != len(self.skus):
            raise ValueError("SKU record IDs are not unique")
        self.manifest = {r["sku_record_id"]: r for r in read_csv(self.root / "data" / "processed" / "sku_evidence_manifest.csv")}
        self.code_counts = {field: Counter(row[field].casefold() for row in self.skus if row.get(field))
                            for field in ("our_sku", "supplier_sku")}
        evidence = read_json(self.root / "knowledge" / "performance_evidence.json")
        self.evidence = {row["family_id"]: row for row in evidence["families"]}
        self.reports = {}
        for name in ("reports/tds_accuracy.json", "data/local/tds_pipeline_status.json",
                     "data/local/tds_family_verification.json", "data/product_knowledge.json"):
            path = self.root / name
            if path.is_file():
                self.reports[name] = read_json(path)
        self.accuracy = {r["family_id"]: r for r in self.reports.get("reports/tds_accuracy.json", [])}
        self.missing = read_csv(self.root / "reports" / "missing_tds_products.csv")
        self.triage = read_csv(self.root / "reports" / "evidence_triage.csv")
        self.manual_rows = []
        self.literature = {}
        self.cards = {}
        self.unassigned = []
        for path in sorted((self.root / "output" / "literature").rglob("*.md")):
            text = path.read_text(encoding="utf-8-sig")
            key = frontmatter(text).get("family_id", "").strip('"\'')
            if key in self.families:
                self.literature.setdefault(key, {})[path.relative_to(self.root).as_posix()] = text
            else:
                self.unassigned.append({"path": path.relative_to(self.root).as_posix(),
                                        "reason": "Missing or unknown declared family_id"})
        card_file = self.root / "data" / "processed" / "retrieval_cards.jsonl"
        if card_file.is_file():
            for number, line in enumerate(card_file.read_text(encoding="utf-8-sig").splitlines(), 1):
                card = json.loads(line)
                key = card.get("family_id")
                if key in self.families:
                    self.cards.setdefault(key, []).append(card)
                else:
                    self.unassigned.append({"path": card_file.relative_to(self.root).as_posix(),
                                            "line": number, "reason": "Missing or unknown declared family_id"})
        workbook = self.root / "reports" / "missing_tds_products.xlsx"
        if workbook.is_file():
            book = load_workbook(workbook, read_only=True, data_only=False)
            try:
                for sheet in book:
                    values = sheet.values
                    headers = next(values, ())
                    if "family_id" not in headers:
                        self.errors.append(f"{workbook.name}/{sheet.title}: no family_id; rows not associated")
                        continue
                    for number, values_row in enumerate(values, 2):
                        row = dict(zip(headers, values_row))
                        if row.get("family_id"):
                            self.manual_rows.append({**row, "_workbook": workbook.relative_to(self.root).as_posix(),
                                                     "_sheet": sheet.title, "_row": number})
            finally:
                book.close()
        self._baseline_key = None
        self._baseline = None
        self._details = {}
        self._browse = None
        self.documents = {}
        for directory in ("data/tds", "data/tds_inbox", "evidence/raw"):
            for path in sorted((self.root / directory).rglob("*")):
                if path.is_file() and path.suffix.casefold() == ".pdf":
                    if not path.resolve().is_relative_to(self.root):
                        raise ValueError("Source library path escapes this worktree")
                    relative = path.relative_to(self.root).as_posix()
                    self.documents[hashlib.sha256(relative.encode()).hexdigest()[:24]] = {
                        "id": hashlib.sha256(relative.encode()).hexdigest()[:24],
                        "path": relative, "sha256": file_hash(path),
                    }
        for entries in self.sources.intake.values():
            for entry in entries:
                path = (self.root / entry["path"]).resolve()
                if not any(path.is_relative_to(self.root / directory) for directory in ("data", "evidence/raw")):
                    raise ValueError("Intake document escapes local source library")
                if path.is_file():
                    relative = path.relative_to(self.root).as_posix()
                    identifier = hashlib.sha256(relative.encode()).hexdigest()[:24]
                    self.documents[identifier] = {"id": identifier, "path": relative, "sha256": file_hash(path)}

    def _baseline_paths(self):
        paths = []
        for pattern in ("knowledge/*/families.json", "knowledge/*/research/*.json", "knowledge/*/*.md",
                        "data/processed/product_catalogue_skus.csv", "data/processed/sku_evidence_manifest.csv",
                        "knowledge/performance_evidence.json", "knowledge/_tds_manifest.json",
                        "reports/tds_accuracy.json", "reports/missing_tds_products.*", "reports/evidence_triage.csv",
                        "data/local/source_review.json"):
            paths.extend(self.root.glob(pattern))
        paths.extend((self.root / "data" / "local" / "intake").glob("*.json"))
        paths.extend(self.root / d["path"] for d in self.documents.values())
        paths.append(self.root / "schemas" / "performance-evidence.schema.json")
        if self.catalogue_version:
            from catalogue_versions import CatalogueLibrary
            paths.extend([self.root / "data" / "local" / "catalogue_versions" / "active.json",
                          CatalogueLibrary(self.root).version_path(self.catalogue_version)])
        existing = sorted({p for p in paths if p.is_file()})
        if any(not p.resolve().is_relative_to(self.root) for p in existing):
            raise ValueError("Research input escapes this worktree")
        return existing

    def source_bindings(self) -> dict[str, str]:
        return {doc["path"]: file_hash(self.root / doc["path"])
                for doc in self.documents.values() if (self.root / doc["path"]).is_file()}

    def non_source_baseline(self) -> str:
        """Only PDF-byte changes can currently be proven dependency-local."""
        source_paths = {self.root / doc["path"] for doc in self.documents.values()}
        entries = [(path.relative_to(self.root).as_posix(), file_hash(path))
                   for path in self._baseline_paths() if path not in source_paths]
        return hashlib.sha256(canonical(entries).encode()).hexdigest()

    def baseline(self) -> str:
        """Bind a review to actual inputs, not an in-memory counter."""
        existing = self._baseline_paths()
        key = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in existing)
        if key != self._baseline_key:
            if any(not p.resolve().is_relative_to(self.root) for p in existing):
                raise ValueError("Research input escapes this worktree")
            entries = [(p.relative_to(self.root).as_posix(), file_hash(p)) for p in existing]
            self._baseline = hashlib.sha256(canonical(entries).encode()).hexdigest()
            self._baseline_key = key
        return self._baseline

    def document(self, identifier: str) -> tuple[Path, dict]:
        doc = self.documents.get(identifier)
        if not doc:
            raise ValueError("Unknown local document ID")
        path = (self.root / doc["path"]).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("Local document unavailable")
        declared = {row["path"] for entries in self.sources.intake.values() for row in entries}
        if not any(path.is_relative_to((self.root / directory).resolve()) for directory in ("data/tds", "data/tds_inbox", "evidence/raw")) and doc["path"] not in declared:
            raise ValueError("Document escapes the local source library")
        if file_hash(path) != doc["sha256"]:
            raise ValueError("Document changed; refresh existing results")
        return path, doc

    def child_skus(self, family_id):
        return [{**row, "evidence_manifest": self.manifest.get(row["sku_record_id"]),
                 "duplicate_codes": [field for field in self.code_counts if row.get(field) and self.code_counts[field][row[field].casefold()] > 1],
                 "dimensions_status": "No dedicated dimensions in this CSV; family range is not an exact SKU specification",
                 "live_stock_status": "No live stock feed"}
                for row in self.skus if row["family_id"] == family_id]

    def detail(self, family_id: str) -> dict:
        if family_id not in self.families:
            raise ValueError("Unknown family")
        if family_id in self._details:
            return dict(self._details[family_id])
        family = self.families[family_id]
        source = self.sources.family(family_id)
        documents = [doc for doc in self.documents.values() if any(link["path"] == doc["path"] for link in source["documents"])]
        guide = self.sources.guides.get(family_id)
        research = dict(self.sources.research.get(family_id, {}))
        research.pop("_path", None)
        derived = self.literature.get(family_id, {})
        cards = self.cards.get(family_id, [])
        result = {
            "family": family, "skus": self.child_skus(family_id), "research": research,
            "guide_text": guide.read_text(encoding="utf-8-sig") if guide else None,
            "evidence": self.evidence.get(family_id, {"family_id": family_id, "evidence_items": []}),
            "sources": source, "documents": documents,
            "accuracy_audit": self.accuracy.get(family_id),
            "manual_requests": [r for r in self.missing if r.get("family_id") == family_id],
            "manual_workbook_rows": [r for r in self.manual_rows if r.get("family_id") == family_id],
            "evidence_triage": [r for r in self.triage if r.get("family_id") == family_id],
            "derived_literature": derived, "retrieval_cards": cards,
            "source_workbooks": [{"filename": name, "status": "present_hash_match" if any(
                p.name == name and file_hash(p) == expected
                for p in (self.root / "data" / "raw").glob("*.xlsx")) else "original_not_available_or_hash_mismatch"}
                for name, expected in sorted({(r["source_workbook"], r["source_sha256"]) for r in self.skus if r["family_id"] == family_id})],
        }
        result["dossier"] = dossier(result)
        self._details[family_id] = result
        return dict(result)

    def browse(self, query="", manufacturer="", category="", status="", offset=0, limit=50):
        if self._browse is None:
            self._browse = []
            for key, family in self.families.items():
                research = self.sources.research.get(key, {})
                docs = self.sources.documents(key)
                children = [s for s in self.skus if s["family_id"] == key]
                audit = self.accuracy.get(key, {})
                has_source = any(d["exists"] for d in docs)
                conflicts = any(s.get("validation_status", "").upper() != "PASS" for s in children)
                states = ["awaiting_input"] if not has_source else ["source_held"]
                if research.get("status") == "ok":
                    states.append("researched")
                if audit.get("status") == "validated":
                    states.append("model_audited")
                if conflicts:
                    states.append("sku_conflicts")
                self._browse.append({"family_id": key, "name": family["name"], "manufacturer": family["manufacturer"],
                                     "category": family.get("category", ""), "sku_count": len(children),
                                     "research_status": research.get("status", "missing"), "source_held": has_source,
                                     "audit_status": audit.get("status", "no_report"), "states": states,
                                     "_search": canonical([family, children]).casefold()})
        rows = []
        for row in self._browse:
            if query.casefold() not in row["_search"] or (manufacturer and row["manufacturer"] != manufacturer) or (category and row["category"] != category) or (status and status not in row["states"]):
                continue
            rows.append({k: v for k, v in row.items() if k != "_search"})
        rows.sort(key=lambda row: (row["manufacturer"], row["name"], row["family_id"]))
        return {"total": len(rows), "offset": offset, "limit": limit, "families": rows[offset:offset + limit]}

    def overview(self):
        return {
            "family_count": len(self.families), "sku_count": len(self.skus),
            "catalogue_version": self.catalogue_version or "baseline_csv",
            "families_without_skus": sum(not any(r["family_id"] == key for r in self.skus) for key in self.families),
            "research_status": dict(Counter(r.get("status", "missing") for r in self.sources.research.values())),
            "accuracy_status": dict(Counter(r.get("status", "missing") for r in self.accuracy.values())),
            "manufacturers": sorted({f["manufacturer"] for f in self.families.values()}),
            "categories": sorted({f.get("category", "") for f in self.families.values()}),
            "reports": {name: "present" if name in self.reports else "no_local_report_found" for name in
                        ("reports/tds_accuracy.json", "data/local/tds_pipeline_status.json", "data/local/tds_family_verification.json", "data/product_knowledge.json")},
            "manual_workbooks": [p.relative_to(self.root).as_posix() for directory in ("reports", "data/raw")
                                 for p in (self.root / directory).glob("*.xlsx")],
            "unlinked_skus": [r["sku_record_id"] for r in self.skus if r["family_id"] not in self.families],
            "errors": self.errors,
            "existing_optional_reports": {name: data for name, data in self.reports.items() if name != "reports/tds_accuracy.json"},
            "note": "Existing script outputs only. Model audit is not human approval. Refresh never starts research or modifies your manual work.",
        }
