"""Framework-independent access to governed local knowledge and coverage gaps."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import threading

from product_research import ResearchIndex, ROOT
from research_store import ResearchStore
from research_workflow import effective_evidence, latest_reviews


class KnowledgeService:
    def __init__(self, root: Path = ROOT, db_path: Path | None = None):
        self.root = root.resolve()
        self.db_path = db_path or self.root / "data" / "local" / "product_research.sqlite3"
        self._store = None
        self._index = None
        self._fingerprint = None
        self._lock = threading.RLock()

    def store(self) -> ResearchStore:
        with self._lock:
            if self._store is None:
                self._store = ResearchStore(self.db_path)
            return self._store

    def index(self, refresh: bool = False) -> ResearchIndex:
        paths = []
        for directory in ("knowledge", "schemas", "data/tds", "data/tds_inbox", "evidence/raw",
                          "data/processed", "reports", "output/literature", "data/raw"):
            paths.extend(p for p in (self.root / directory).rglob("*") if p.is_file())
        paths.extend(p for p in (self.root / "data" / "local").glob("*.json") if p.is_file())
        paths.extend(p for p in (self.root / "data" / "local" / "catalogue_versions").glob("*.json") if p.is_file())
        paths.extend(p for p in (self.root / "data" / "local" / "intake").glob("*.json") if p.is_file())
        fingerprint = tuple((str(p.relative_to(self.root)), p.stat().st_size, p.stat().st_mtime_ns)
                            for p in sorted(paths))
        with self._lock:
            if refresh or self._index is None or fingerprint != self._fingerprint:
                self._index = ResearchIndex(self.root)
                self._fingerprint = fingerprint
            return self._index

    def evidence(self) -> tuple[dict, dict]:
        idx = self.index()
        if not self.db_path.is_file():
            return ({key: list(record["evidence_items"]) for key, record in idx.evidence.items()},
                    {"state": "baseline_only", "publication_id": None,
                     "claims": [], "revoked": [], "eligibility": {}})
        return effective_evidence(idx, self.store())

    def validation(self) -> dict:
        return knowledge_validation(self.index(), self.store() if self.db_path.is_file() else None)

    def draft_preview(self):
        from family_drafts import build_preview
        manifest, _ = build_preview(self.index(refresh=True))
        return {key: value for key, value in manifest.items() if key != "inputs"}

    def draft_write(self, confirmation):
        from family_drafts import write_batch
        return write_batch(self.index(refresh=True), confirmation)

    def draft_family(self, family_id):
        external = self.root / "data" / "local" / "fresh_tds_cache.json"
        if external.is_file():
            from tds_build import Build
            cache = Path(json.loads(external.read_text(encoding="utf-8"))["cache"])
            return Build(self.root, cache).family(family_id, self.index())
        from family_drafts import inspect_family
        return inspect_family(self.index(), family_id)

    def draft_annotations(self, batch, limit, retry=False):
        from family_drafts import annotate
        return annotate(self.root, batch, limit, retry=retry)

    def draft_status(self, batch):
        from family_drafts import annotation_status
        return annotation_status(self.root, batch)

    def family(self, family_id: str) -> dict:
        """Private retained dossier plus effective claims; reads never create a DB."""
        idx = self.index()
        record = idx.detail(family_id)
        record["sources"] = idx.sources.family(family_id, include_compiled=True)
        record["compiled_sources"] = record["sources"]["compiled_sources"]
        evidence, state = self.evidence()
        record["effective_evidence"] = evidence.get(family_id, [])
        record["publication_state"] = state["state"]
        record["publication_holds"] = [hold for hold in state.get("holds", []) if hold["family_id"] == family_id]
        if state["state"] == "published_with_scoped_holds" and not record["publication_holds"]:
            record["publication_state"] = "published"
        record["published_sku_eligibility"] = {
            row["sku_record_id"]: state["eligibility"].get(row["sku_record_id"], {"eligible": False})
            for row in record["skus"]
        }
        record["baseline"] = idx.baseline()
        record["history"] = [
            row for row in self.store().history()
            if row["target"] == "family:" + family_id or row["payload"].get("family_id") == family_id
        ] if self.db_path.is_file() else []
        from source_review_queue import review_view
        record["source_review_queue"] = review_view(record["compiled_sources"], family_id, record["history"])
        record["workflow"] = [
            {"action": "inspect_retained", "input": family_id, "output": "private family dossier",
             "gate": "local OS access or named GUI reader", "writes": False},
            {"action": "source_preview", "input": "explicit checkout-local PDF manifest",
             "output": "hash-bound extraction and candidate preview", "gate": "no automatic stage", "writes": False},
            {"action": "source_stage", "input": "same manifest and exact preview ID",
             "output": "data/local/intake immutable receipt", "gate": "explicit confirmation; GUI reviewer + CSRF", "writes": True},
            {"action": "retained_field_review", "input": "exact dossier ID, group and occurrence",
             "output": "immutable private review revision", "gate": "named reviewer; not public claim approval", "writes": True},
            {"action": "public_claim_review", "input": "source-cited claim and exact SKU applicability",
             "output": "review draft then publication preview", "gate": "named reviewer then publisher; original-unavailable attestation is not a PDF citation", "writes": True},
            {"action": "release_export", "input": "published claims, reviewed rows and explicit site visibility",
             "output": "immutable serving release and site-filtered exports", "gate": "explicit build/activation; no model-generated approvals", "writes": True},
        ]
        record["claim_candidates"] = []
        schema = json.loads((self.root / "schemas" / "performance-evidence.schema.json").read_text(encoding="utf-8"))
        metrics = schema["$defs"]["evidence"]["properties"]["metric_type"]["enum"]
        for doc in record["sources"]["documents"]:
            for candidate in doc.get("candidate_fields", []):
                if candidate["field"] not in metrics or isinstance(candidate["value"], bool):
                    continue
                identifier = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16].upper()
                document = next((row for row in record["documents"] if row["path"] == doc["path"]), None)
                record["claim_candidates"].append({
                    "candidate": candidate, "source_current": candidate["source_current"],
                    "citation": {"document_id": document["id"] if document else "",
                                 "sha256": candidate["source_sha256"], "page": candidate["page"],
                                 "quote": candidate["quote"], "locator": ""},
                    "claim": {"evidence_id": "CANDIDATE-" + identifier, "metric_type": candidate["field"],
                              "value": candidate["value"], "value_type": "scalar" if isinstance(candidate["value"], (int, float)) else "text_classification",
                              "unit": candidate["unit"], "scope": candidate["scope"], "variant": candidate["variant"],
                              "test_standard": candidate["test_standard"], "test_context": candidate["test_context"],
                              "source_url": record["family"].get("source_url", ""), "source_type": "owned_secondary_source",
                              "source_locator": "", "extraction_method": "manual_transcription",
                              "extractor_confidence": 0, "ocr_confidence": None,
                              "evidence_status": "pending_human_review", "verified_by": None, "verified_at": None,
                              "notes": "Transferred owner-declared candidate; reviewer must confirm source type, URL, exact locator, context and applicability. Not approved."},
                })
        return record

    def source_preview(self, manifest: Path) -> dict:
        from local_intake import preview
        if not manifest.is_absolute():
            manifest = self.root / manifest
        return preview(self.root, manifest)

    def source_stage(self, manifest: Path, confirmation: str) -> dict:
        from local_intake import stage
        if not manifest.is_absolute():
            manifest = self.root / manifest
        path = stage(self.root, manifest, confirmation)
        self.index(refresh=True)
        return {"receipt": path.relative_to(self.root).as_posix(),
                "state": "staged_pending_human_review", "claims_approved": False}

    def review_source_identity(self, family_id: str, data: dict, actor: str, expected: int) -> dict:
        record = self.family(family_id)
        queue = record["source_review_queue"]
        if queue["state"] != "compiled":
            raise ValueError("Compile current source evidence before reviewing")
        item = next((item for item in queue["items"] if item["id"] == data.get("item_id")), None)
        if not item or data.get("source_hash") != item.get("source_hash", ""):
            raise ValueError("Source review input changed; refresh")
        decision = data.get("decision")
        if decision not in {"accepted", "needs_information", "rejected"}:
            raise ValueError("Identity decision cannot approve technical claims")
        rationale = data.get("rationale")
        if not isinstance(rationale, str) or not 10 <= len(rationale.strip()) <= 10000:
            raise ValueError("Meaningful rationale of 10 to 10000 characters required")
        payload = {"family_id": family_id, "item": item, "decision": decision,
                   "source_hash": item.get("source_hash", ""), "rationale": rationale.strip(),
                   "public_approval": False, "bindings_changed": False}
        target = "source-review:" + family_id + ":" + item["id"]
        revision = self.store().save_revision(target, "source_identity_review", payload, actor, expected)
        return {"revision": revision, "public_approval": False, "bindings_changed": False}

    def review_retained(self, family_id: str, data: dict, actor: str, expected: int) -> dict:
        from retained_review import validate_decision
        record = self.family(family_id)
        dossier = record["dossier"]
        if data.get("dossier_id") != dossier["dossier_id"]:
            raise ValueError("Retained inputs changed; refresh the dossier before reviewing")
        group, position = data.get("group"), data.get("position")
        if not isinstance(group, str) or group not in dossier["groups"]:
            raise ValueError("Choose an exact retained field group")
        rows = dossier["groups"][group]
        if type(position) is not int or not 0 <= position < len(rows):
            raise ValueError("Choose an exact retained occurrence")
        decision = validate_decision(data.get("decision"), data.get("rationale"))
        payload = {"family_id": family_id, "dossier_id": dossier["dossier_id"],
                   "group": group, "position": position, "occurrence": rows[position],
                   "decision": decision, "rationale": data["rationale"].strip(),
                   "provenance_state": dossier["provenance_state"],
                   "public_approval": False, "reviewer": actor}
        target = f"retained:{family_id}:{group}:{position}"
        revision = self.store().save_revision(target, "retained_review", payload, actor, expected)
        return {"revision": revision, "public_approval": False, "runtime_changed": False}

    def review_claim_or_sku(self, family_id: str, data: dict, actor: str, expected: int) -> dict:
        from research_workflow import validate_review
        if len(json.dumps(data)) > 100000:
            raise ValueError("Review payload is too large")
        validated = validate_review(self.index(), family_id, data, actor)
        revision = self.store().save_revision(validated["target"], "review", validated, actor, expected)
        return {"revision": revision, "review": validated, "runtime_changed": False}

    def publication_preview(self, actor: str, *, scoped: bool = False) -> dict:
        from research_workflow import publication_preview
        with self.store().connection() as conn:
            user = conn.execute("SELECT roles,disabled FROM users WHERE username=?", (actor,)).fetchone()
        if not user or user["disabled"] or "publisher" not in json.loads(user["roles"]):
            raise ValueError("An enabled publisher account is required")
        return publication_preview(self.index(refresh=True), self.store(), actor, scoped=scoped)

    def publish(self, proposal_id: int, actor: str) -> dict:
        idx = self.index(refresh=True)
        current = self.publication_preview(actor)
        if current["blockers"]:
            raise ValueError("; ".join(current["blockers"]))
        payload = self.store().publish(proposal_id, idx.baseline(), actor)
        return {"publication_id": proposal_id, "impact": payload["impact"]}

    def catalogue_overview(self) -> dict:
        from catalogue_versions import CatalogueLibrary
        library = CatalogueLibrary(self.root)
        return {"active_id": library.active_id(), "versions": library.staged()}

    def catalogue_preview(self, source: Path, mapping: dict, sheet: str | None) -> dict:
        from catalogue_versions import preview
        if not source.is_absolute():
            source = self.root / source
        return preview(self.root, source, mapping, sheet)

    def catalogue_stage(self, data: dict) -> dict:
        from catalogue_versions import CatalogueLibrary
        target = CatalogueLibrary(self.root).stage(data)
        self.index(refresh=True)
        return {"receipt": target.relative_to(self.root).as_posix(),
                "version_id": data["version_id"], "state": "staged_pending_human_review"}

    def catalogue_activate(self, identifier: str, confirm: str, expected) -> dict:
        from catalogue_versions import CatalogueLibrary
        CatalogueLibrary(self.root).activate(identifier, confirm, expected)
        self.index(refresh=True)
        return {"version_id": identifier, "state": "activated"}


_services: dict[tuple[Path, Path], KnowledgeService] = {}
_services_lock = threading.RLock()


def service() -> KnowledgeService:
    import research_store

    key = (ROOT.resolve(), research_store.DEFAULT_DB.resolve())
    with _services_lock:
        if key not in _services:
            _services[key] = KnowledgeService(*key)
        return _services[key]


def knowledge_validation(idx: ResearchIndex, store: ResearchStore | None = None) -> dict:
    """Independent status dimensions; no extraction, model call or publication."""
    if store is None:
        evidence = {key: record["evidence_items"] for key, record in idx.evidence.items()}
        publication = {"state": "baseline_only", "publication_id": None,
                       "claims": [], "revoked": [], "eligibility": {}}
        reviews = []
    else:
        evidence, publication = effective_evidence(idx, store)
        reviews = [row["payload"] for row in latest_reviews(store).values()]
    families = []
    for row in idx.browse(limit=len(idx.families))["families"]:
        key = row["family_id"]
        sources = idx.sources.family(key)
        documents = sources["documents"]
        held = [doc for doc in documents if doc["exists"]]
        integrity = ("hash_mismatch" if any(doc.get("manifest_hash_matches") is False for doc in held)
                     else "hash_matches" if held and all(doc.get("manifest_hash_matches") is True for doc in held)
                     else "not_verified" if held else "no_linked_source")
        extraction = Counter(doc.get("extraction", {}).get("status", "not_audited_or_changed") for doc in held)
        decisions = Counter(r["decision"] for r in reviews if r["family_id"] == key)
        claims = evidence.get(key, [])
        verified = sum(c.get("evidence_status") == "verified" for c in claims)
        eligibility = sum(v["family_id"] == key and v["eligible"] for v in publication["eligibility"].values())
        family_publication = publication["state"]
        scoped_holds = [hold for hold in publication.get("holds", []) if hold["family_id"] == key]
        if family_publication == "published_with_scoped_holds" and not scoped_holds:
            family_publication = "published"
        gaps = list(sources["source_gaps"])
        if not sources["guide"]:
            gaps.append("Family guide is missing.")
        if not verified:
            gaps.append("No current verified performance claim; technical values remain unknown.")
        if not row["sku_count"]:
            gaps.append("No current commercial SKU rows; family metadata cannot supply exact variants.")
        if family_publication not in {"published", "baseline_only"}:
            gaps.append("Published additions are held: " + family_publication + ".")
        families.append({
            **row,
            "identity_state": idx.families[key].get("confidence", "unknown"),
            "guide": {"state": "present_not_approval" if sources["guide"] else "missing",
                      "path": sources["guide"]},
            "source": {"linked_count": len(documents), "held_count": len(held),
                       "integrity": integrity, "documents": documents},
            "extraction": {"states": dict(extraction), "status": "no_linked_source" if not held
                           else "all_pages_extracted_not_approval" if all(
                               doc.get("extraction", {}).get("status") == "text_extracted" for doc in held)
                           else "needs_extraction_or_page_review"},
            "review": {"decisions": dict(decisions),
                       "status": "draft_reviews_present" if decisions else "no_human_review"},
            "publication": {"state": family_publication, "id": publication["publication_id"],
                            "holds": scoped_holds,
                            "verified_claims": verified, "eligible_skus": eligibility},
            "gaps": gaps,
            "next_action": gaps[0] if gaps else "Inspect field and variant applicability; no completeness certification.",
        })
    return {
        "family_count": len(families), "sku_count": len(idx.skus),
        "families_with_linked_sources": sum(r["source"]["held_count"] > 0 for r in families),
        "families_without_skus": sum(r["sku_count"] == 0 for r in families),
        "families_with_verified_claims": sum(r["publication"]["verified_claims"] > 0 for r in families),
        "document_count": len(idx.documents), "publication_state": publication["state"],
        "manufacturers": sorted({r["manufacturer"] for r in families}),
        "families": families, "errors": list(idx.errors),
        "note": "Guide presence, source text, research ok and model audit are not approval. "
                "This read-only view starts no ingestion or model and does not certify complete documentation.",
    }
