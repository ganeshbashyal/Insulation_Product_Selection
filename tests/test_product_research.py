"""Synthetic research reviews: never approve or publish real product evidence."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import research_api as api
import knowledge_service
from product_research import ResearchIndex
from research_store import Conflict, ResearchStore, canonical
from research_workflow import active_effective, effective_evidence, publication_preview, validate_review

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def research(tmp_path, monkeypatch):
    family = {"family_id": "TEST_FAMILY", "name": "Synthetic family", "manufacturer": "Test",
              "category": "Batt", "confidence": "manufacturer_supported", "source_url": "https://example.invalid/tds"}
    write_json(tmp_path / "knowledge" / "test" / "families.json",
               {"families": [family, {**family, "family_id": "NO_SKU", "name": "No child family"}]})
    write_json(tmp_path / "knowledge" / "_tds_manifest.json", {})
    write_json(tmp_path / "knowledge" / "performance_evidence.json",
               {"schema_version": "2.0", "families": [{"family_id": "TEST_FAMILY", "evidence_items": []}]})
    (tmp_path / "schemas").mkdir()
    shutil.copyfile(ROOT / "schemas" / "performance-evidence.schema.json", tmp_path / "schemas" / "performance-evidence.schema.json")
    pdf = tmp_path / "data" / "tds" / "synthetic.pdf"
    pdf.parent.mkdir(parents=True)
    writer = PdfWriter()
    page = writer.add_blank_page(300, 300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 200 Td (Test grade 50 mm R2.0 AS TEST) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    with pdf.open("wb") as handle:
        writer.write(handle)
    data = tmp_path / "data" / "processed" / "product_catalogue_skus.csv"
    data.parent.mkdir()
    row = {"sku_record_id": "SKU-ONE", "family_id": "TEST_FAMILY", "our_sku": "SHARED", "supplier_sku": "CODE",
           "product_name": "50 mm grade", "validation_status": "REVIEW", "validation_notes": "wrong material",
           "active": "Yes", "bot_content_status": "READY", "source_workbook": "missing.xlsx", "source_sha256": "0" * 64}
    with data.open("w", newline="") as handle:
        out = csv.DictWriter(handle, fieldnames=row)
        out.writeheader()
        out.writerows([row, {**row, "sku_record_id": "SKU-TWO", "product_name": "Different grade"}])
    idx = ResearchIndex(tmp_path)
    store = ResearchStore(tmp_path / "reviews.sqlite3")
    for name, roles in (("reader", ["reader"]), ("reviewer", ["reviewer"]), ("publisher", ["publisher"])):
        store.create_user(name, "Synthetic password only!", roles)
    reader = knowledge_service.KnowledgeService(tmp_path, store.path)
    reader._store = store
    monkeypatch.setattr(reader, "index", lambda refresh=False: ResearchIndex(tmp_path) if refresh else idx)
    monkeypatch.setattr(api, "service", lambda: reader)
    monkeypatch.setattr(knowledge_service, "service", lambda: reader)
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    return idx, store, client


def claim_review(idx):
    doc = next(iter(idx.documents.values()))
    return {"kind": "claim", "decision": "approved", "rationale": "Exact grade checked against synthetic test source.",
            "citation": {"document_id": doc["id"], "sha256": doc["sha256"], "page": 1,
                         "locator": "Grade line", "quote": "Test grade 50 mm R2.0"},
            "applicable_skus": ["SKU-ONE"],
            "claim": {"evidence_id": "TEST-R-50", "metric_type": "thermal_r", "value": 2.0, "value_type": "scalar",
                      "unit": "m2.K/W", "scope": "product", "variant": "50 mm test grade", "test_standard": "AS TEST",
                      "test_context": "Product-only synthetic laboratory test", "source_url": "https://example.invalid/tds",
                      "source_type": "manufacturer_tds", "source_locator": "", "extraction_method": "manual_transcription",
                      "extractor_confidence": 1, "ocr_confidence": None, "evidence_status": "pending_human_review",
                      "verified_by": None, "verified_at": None, "notes": "Synthetic only"}}


def test_literature_uses_declared_identity_not_substring(research):
    idx, _, _ = research
    directory = idx.root / "output" / "literature"
    directory.mkdir(parents=True)
    (directory / "wrong.md").write_text("---\nfamily_id: NO_SKU\n---\nMentions TEST_FAMILY")
    (directory / "unknown.md").write_text("Mentions TEST_FAMILY without identity")
    fresh = ResearchIndex(idx.root)
    assert fresh.detail("TEST_FAMILY")["derived_literature"] == {}
    assert list(fresh.detail("NO_SKU")["derived_literature"]) == ["output/literature/wrong.md"]
    assert fresh.unassigned[0]["path"] == "output/literature/unknown.md"


def test_private_draft_pack_endpoint_requires_named_reader(research):
    idx, store, client = research
    path = "/api/research/families/TEST_FAMILY/draft-pack"
    assert client.get(path).status_code == 401
    login = client.post("/api/research/login", json={"username": "reader", "password": "Synthetic password only!"},
                        headers={"Origin": "http://testserver"})
    assert login.status_code == 200
    assert client.get(path).json()["state"] == "not_generated"
    service = knowledge_service.service()
    preview = service.draft_preview()
    result = service.draft_write(preview["preview_id"])
    assert result["families"] == 2
    assert client.get(path).json()["state"] == "current_private_draft_not_approved"
    assert not store.history()
    client.post("/api/research/logout", headers={"Origin": "http://testserver",
                                               "X-Research-CSRF": login.json()["csrf"]})
    assert client.get(path).status_code == 401


def save_claim(idx, store, decision="approved", expected=0):
    data = claim_review(idx)
    data["decision"] = decision
    validated = validate_review(idx, "TEST_FAMILY", data, "reviewer")
    return store.save_revision(validated["target"], "review", validated, "reviewer", expected)


def login(client, name):
    result = client.post("/api/research/login", json={"username": name, "password": "Synthetic password only!"},
                         headers={"Origin": "http://testserver"})
    assert result.status_code == 200, result.text
    cookie = result.headers["set-cookie"].casefold()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=28800" in cookie
    return {"Origin": "http://testserver", "X-Research-CSRF": result.json()["csrf"]}


def test_source_identity_route_preserves_reader_csrf_and_conflict_gates(research, monkeypatch):
    _, _, client = research
    called = []
    monkeypatch.setattr(api.service(), "review_source_identity",
                        lambda *args: called.append(args) or {
                            "revision": 1, "public_approval": False, "bindings_changed": False})
    path = "/api/research/families/TEST_FAMILY/source-review"
    body = {"expected_version": 0, "data": {"item_id": "source", "decision": "accepted"}}
    assert client.post(path, json=body).status_code == 401
    headers = login(client, "reader")
    assert client.post(path, json=body, headers=headers).status_code == 403
    headers = login(client, "reviewer")
    assert client.post(path, json=body).status_code == 403
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 200 and not response.json()["public_approval"]
    assert called[0][2] == "reviewer"
    def conflict(*args):
        raise Conflict("Refresh")
    monkeypatch.setattr(api.service(), "review_source_identity", conflict)
    assert client.post(path, json=body, headers=headers).status_code == 409


def test_all_real_families_and_child_record_ids_preserved():
    idx = ResearchIndex()
    assert len(idx.families) == 283
    assert len(idx.by_sku) == len(idx.skus) == 414
    assert idx.overview()["families_without_skus"] == 253
    assert idx.browse(query="SKU-")["total"] > 0
    assert idx.browse(limit=300)["total"] == 283
    assert idx.manual_rows and all("_row" in row for row in idx.manual_rows)


def test_every_real_dossier_preserves_raw_inputs_and_child_record_ids():
    idx = ResearchIndex()
    seen = set()
    for key in idx.families:
        detail = idx.detail(key)
        retained = detail["dossier"]["retained"]
        assert retained["family"] == detail["family"]
        assert retained["research"] == detail["research"]
        assert retained["guide_text"] == detail["guide_text"]
        assert retained["manual_workbook_rows"] == detail["manual_workbook_rows"]
        for row in retained["commercial_rows"]:
            assert row["sku_record_id"] not in seen
            seen.add(row["sku_record_id"])
        if not any(doc["exists"] for doc in detail["sources"]["documents"]):
            assert detail["dossier"]["provenance_state"] == "legacy_supplied_original_unavailable"
    assert len(idx.families) == 283 and seen == set(idx.by_sku)


def test_family_without_skus_and_duplicates_are_not_collapsed(research):
    idx, _, _ = research
    assert idx.browse()["total"] == 2
    assert len(idx.child_skus("TEST_FAMILY")) == 2
    assert idx.detail("NO_SKU")["skus"] == []
    assert idx.child_skus("TEST_FAMILY")[0]["duplicate_codes"] == ["our_sku", "supplier_sku"]
    assert idx.overview()["reports"]["data/local/tds_pipeline_status.json"] == "no_local_report_found"


def test_shared_family_read_keeps_legacy_prose_unknown_fields_and_no_database(research):
    idx, _, _ = research
    root = idx.root
    path = root / "knowledge" / "test" / "families.json"
    families = json.loads(path.read_text())
    families["families"][1]["knowledge_file"] = "legacy.md"
    families["families"][1]["applications"] = ["Historical wall use"]
    write_json(path, families)
    guide = root / "knowledge" / "test" / "legacy.md"
    guide.write_text("Preface kept verbatim.\n\n## Approved\nHistorical heading, not approval.\n", encoding="utf-8")
    original_research = {"family_id": "NO_SKU", "status": "ok",
                        "spec": {"applications": ["Different supplied use"], "unknown_key": {"old": [1, 2]}},
                        "manual_extra": "Keep this too"}
    write_json(root / "knowledge" / "test" / "research" / "legacy.json", original_research)
    service = knowledge_service.KnowledgeService(root)
    result = service.family("NO_SKU")
    dossier = result["dossier"]
    assert dossier["provenance_state"] == "legacy_supplied_original_unavailable"
    assert dossier["retained"]["guide_text"] == guide.read_text()
    assert dossier["retained"]["research"] == original_research
    assert dossier["alternatives"][0]["field"] == "applications"
    assert dossier["groups"]["unparsed"]
    assert dossier["groups"]["retained_sections"][0]["status"] == "historical_heading_not_current_approval"
    assert result["publication_state"] == "baseline_only"
    assert result["effective_evidence"] == [] and result["history"] == []
    assert not service.db_path.exists()
    assert service.family("NO_SKU")["dossier"]["dossier_id"] == dossier["dossier_id"]
    guide.write_text(guide.read_text() + "Another retained sentence.\n")
    assert service.family("NO_SKU")["dossier"]["dossier_id"] != dossier["dossier_id"]


def test_shared_family_service_and_authenticated_api_return_same_dossier(research):
    idx, store, client = research
    login(client, "reader")
    response = client.get("/api/research/families/TEST_FAMILY")
    assert response.status_code == 200
    reader = knowledge_service.KnowledgeService(idx.root, store.path)
    assert response.json()["dossier"] == reader.family("TEST_FAMILY")["dossier"]
    assert client.get("/api/research/families/UNKNOWN").status_code == 404


def test_page_cache_is_hash_bound_and_does_not_share_mutable_results(research, monkeypatch):
    import local_source_review as source
    idx, _, _ = research
    path, doc = idx.document(next(iter(idx.documents)))
    source._cached_pages.cache_clear()
    original = source.extract_pages
    calls = []
    def extract(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(source, "extract_pages", extract)
    first = source.checked_pages(path, doc["sha256"])
    first["pages"][0]["text"] = "Mutated"
    second = source.checked_pages(path, doc["sha256"])
    assert second["pages"][0]["text"] != "Mutated" and len(calls) == 1
    path.write_bytes(path.read_bytes() + b"\nchanged")
    with pytest.raises(ValueError, match="hash changed"):
        source.checked_pages(path, doc["sha256"])


def test_source_audit_includes_evidence_library_and_families_without_research(research):
    from local_source_review import build_review
    idx, _, _ = research
    pdf = idx.root / "data" / "tds" / "synthetic.pdf"
    extra = idx.root / "evidence" / "raw" / "retained.pdf"
    extra.parent.mkdir(parents=True)
    extra.write_bytes(pdf.read_bytes())
    result = build_review(idx.root)
    assert "evidence/raw/retained.pdf" in result["documents"]
    assert set(result["families"]) == set(idx.families)
    assert result["auto_approval"] is False


def test_source_preview_stage_share_service_and_preserve_approval_gate(research):
    idx, _, client = research
    manifest = idx.root / "data" / "input.json"
    write_json(manifest, {"documents": [{"path": "data/tds/synthetic.pdf", "family_ids": ["TEST_FAMILY"], "role": "tds"}]})
    body = {"data": {"manifest": "data/input.json"}}
    assert client.post("/api/research/source-preview", json=body).status_code == 401
    headers = login(client, "reader")
    assert client.post("/api/research/source-preview", json=body, headers=headers).status_code == 403
    headers = login(client, "reviewer")
    assert client.post("/api/research/source-preview", json=body).status_code == 403
    preview = client.post("/api/research/source-preview", json=body, headers=headers)
    assert preview.status_code == 200, preview.text
    stage = client.post("/api/research/source-stage", json={"data": {
        "manifest": "data/input.json", "confirmation": preview.json()["preview_id"]}}, headers=headers)
    assert stage.status_code == 200, stage.text
    assert stage.json()["claims_approved"] is False
    second = client.post("/api/research/source-stage", json={"data": {
        "manifest": "data/input.json", "confirmation": preview.json()["preview_id"]}}, headers=headers)
    assert second.json() == stage.json()
    manifest.write_text('{"documents":[]}')
    assert client.post("/api/research/source-stage", json={"data": {
        "manifest": "data/input.json", "confirmation": preview.json()["preview_id"]}}, headers=headers).status_code == 400


def test_typed_candidate_transfer_is_exact_and_never_an_approval(research):
    from local_intake import preview, stage
    idx, _, _ = research
    candidate = {"family_id": "TEST_FAMILY", "kind": "performance", "field": "thermal_r",
                 "value": 2.0, "unit": "m2.K/W", "variant": "50 mm test grade",
                 "scope": "product", "page": 1, "quote": "Test grade 50 mm R2.0",
                 "test_standard": "AS TEST", "test_context": "Synthetic test only"}
    manifest = idx.root / "manifest.json"
    write_json(manifest, {"documents": [{"path": "data/tds/synthetic.pdf",
                "family_ids": ["TEST_FAMILY"], "role": "tds", "candidates": [candidate]}]})
    draft = preview(idx.root, manifest)
    reader = knowledge_service.KnowledgeService(idx.root)
    assert reader.source_preview(Path("manifest.json"))["preview_id"] == draft["preview_id"]
    stage(idx.root, manifest, draft["preview_id"])
    record = knowledge_service.KnowledgeService(idx.root).family("TEST_FAMILY")
    row = record["claim_candidates"][0]
    assert row["claim"]["value"] == candidate["value"]
    assert row["claim"]["variant"] == candidate["variant"]
    assert row["citation"]["quote"] == candidate["quote"]
    assert row["citation"]["locator"] == ""
    assert row["claim"]["evidence_status"] == "pending_human_review"
    assert row["claim"]["verified_by"] is None
    assert record["effective_evidence"] == []
    assert row["source_current"] is True


def test_retained_review_preserves_occurrence_without_public_approval(research):
    _, store, client = research
    headers = login(client, "reviewer")
    record = client.get("/api/research/families/NO_SKU").json()
    data = {"dossier_id": record["dossier"]["dossier_id"], "group": "identity", "position": 0,
            "decision": "retained_confirmed", "rationale": "Identity checked in surviving supplied records."}
    url = "/api/research/families/NO_SKU/retained-review"
    assert client.post(url, json={"data": data}).status_code == 403
    saved = client.post(url, json={"data": data}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["public_approval"] is False and saved.json()["runtime_changed"] is False
    assert store.history()[-1]["payload"]["occurrence"] == record["dossier"]["groups"]["identity"][0]
    assert client.get("/api/research/families/NO_SKU").json()["effective_evidence"] == []
    assert client.post(url, json={"data": data}, headers=headers).status_code == 409
    data["decision"] = "approved"
    assert client.post(url, json={"data": data}, headers=headers).status_code == 400
    data["decision"] = "retained_confirmed"
    data["dossier_id"] = "stale"
    assert client.post(url, json={"data": data}, headers=headers).status_code == 400


def scoped_fixture(research):
    idx, store, _ = research
    original = idx.root / "data" / "tds" / "synthetic.pdf"
    second = original.with_name("second.pdf")
    second.write_bytes(original.read_bytes())
    idx = ResearchIndex(idx.root)
    store.create_user("other", "Synthetic password only!", ["reviewer"])
    documents = sorted(idx.documents.values(), key=lambda row: row["path"])
    for number, (doc, reviewer) in enumerate(zip(documents, ("other", "reviewer"))):
        data = claim_review(idx)
        data["claim"]["evidence_id"] = f"SCOPED-{number}"
        data["citation"]["document_id"], data["citation"]["sha256"] = doc["id"], doc["sha256"]
        data["applicable_skus"] = []
        value = validate_review(idx, "TEST_FAMILY", data, reviewer)
        store.save_revision(value["target"], "review", value, reviewer, 0)
    proposal = publication_preview(idx, store, "publisher", scoped=True)
    assert proposal["dependency_mode"] == "source_scoped_v1"
    assert not proposal["blockers"]
    store.publish(proposal["proposal_id"], idx.baseline(), "publisher")
    return idx, store, documents


def test_scoped_pdf_change_holds_only_explicitly_bound_claim(research):
    idx, store, documents = scoped_fixture(research)
    changed = idx.root / documents[0]["path"]
    changed.write_bytes(changed.read_bytes() + b"\nchanged")
    state = active_effective(ResearchIndex(idx.root), store)
    assert state["state"] == "published_with_scoped_holds"
    assert [row["claim"]["evidence_id"] for row in state["claims"]] == ["SCOPED-1"]
    assert state["holds"][0]["evidence_id"] == "SCOPED-0"


def test_scoped_unauthorised_reviewer_holds_only_their_claim(research):
    idx, store, _ = scoped_fixture(research)
    store.set_disabled("other", True)
    state = active_effective(idx, store)
    assert state["state"] == "published_with_scoped_holds"
    assert [row["claim"]["evidence_id"] for row in state["claims"]] == ["SCOPED-1"]
    assert state["holds"][0]["reason"] == "reviewer_unauthorised"


def test_scoped_removed_reviewer_role_is_also_held(research):
    idx, store, _ = scoped_fixture(research)
    with store.connection() as conn:
        conn.execute("UPDATE users SET roles=? WHERE username='other'", ('["reader"]',))
    state = active_effective(idx, store)
    assert state["state"] == "published_with_scoped_holds"
    assert [row["claim"]["evidence_id"] for row in state["claims"]] == ["SCOPED-1"]


def test_scoped_unknown_non_source_change_still_holds_everything(research):
    idx, store, _ = scoped_fixture(research)
    write_json(idx.root / "knowledge" / "test" / "research" / "unknown.json",
               {"family_id": "NO_SKU", "new_unknown_dependency": "requires review"})
    state = active_effective(ResearchIndex(idx.root), store)
    assert state["state"] == "stale_sources_review_required" and not state["claims"]
    assert state["hold_scope"] == "global_unknown_dependency"


def test_scoped_unrelated_pdf_is_not_a_global_hold(research):
    idx, store, documents = scoped_fixture(research)
    original = idx.root / documents[0]["path"]
    original.with_name("unlinked-new.pdf").write_bytes(original.read_bytes())
    state = active_effective(ResearchIndex(idx.root), store)
    assert state["state"] == "published" and len(state["claims"]) == 2
    assert state["changed_sources"] == ["data/tds/unlinked-new.pdf"]


def test_offline_cli_named_review_uses_shared_rules_and_closes_session(research, monkeypatch, capsys):
    from scripts import knowledge_workflow as cli
    idx, store, _ = research
    reader = knowledge_service.KnowledgeService(idx.root, store.path)
    monkeypatch.setattr(cli, "KnowledgeService", lambda root: reader)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "Synthetic password only!")
    data = claim_review(idx)
    data["decision"] = "needs_information"
    input_file = idx.root / "review-input.json"
    write_json(input_file, data)
    assert cli.main(["review", "TEST_FAMILY", str(input_file), "--username", "reviewer"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["runtime_changed"] is False and result["review"]["reviewer"] == "reviewer"
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert cli.main(["publication-preview", "--username", "reviewer"]) == 1
    assert "publisher" in capsys.readouterr().err
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_knowledge_view_protects_data_and_keeps_independent_statuses(research):
    _, store, client = research
    assert client.get("/admin/knowledge").status_code == 200
    assert client.get("/api/research/knowledge").status_code == 401
    login(client, "reader")
    result = client.get("/api/research/knowledge")
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    data = result.json()
    assert data["family_count"] == data["total"] == 2
    assert data["families_without_skus"] == 1
    assert {row["family_id"] for row in data["families"]} == {"TEST_FAMILY", "NO_SKU"}
    family = next(row for row in data["families"] if row["family_id"] == "TEST_FAMILY")
    assert family["sku_count"] == 2
    assert family["review"]["status"] == "no_human_review"
    assert family["publication"]["state"] == "baseline_only"
    assert family["publication"]["verified_claims"] == 0
    assert "complete" not in family
    assert family["gaps"]
    assert store.active() is None
    assert client.get("/api/research/knowledge?q=No%20child").json()["total"] == 1
    assert client.get("/api/research/knowledge?gap=No%20current%20commercial").json()["total"] == 1
    assert client.get("/api/research/knowledge?manufacturer=Unknown").json()["total"] == 0
    assert client.get("/api/research/knowledge?offset=1&limit=1").json()["total"] == 2
    assert len(client.get("/api/research/knowledge?offset=1&limit=1").json()["families"]) == 1
    assert client.get("/api/research/knowledge?limit=101").status_code == 422


def test_knowledge_view_draft_publish_and_stale_hold_are_distinct(research):
    idx, store, client = research
    login(client, "reader")
    save_claim(idx, store)
    family = lambda: next(row for row in client.get("/api/research/knowledge").json()["families"]
                          if row["family_id"] == "TEST_FAMILY")
    assert family()["review"]["decisions"] == {"approved": 1}
    assert family()["publication"]["verified_claims"] == 0
    preview = publication_preview(idx, store, "publisher")
    store.publish(preview["proposal_id"], idx.baseline(), "publisher")
    assert family()["publication"]["verified_claims"] == 1
    path = idx.root / next(iter(idx.documents.values()))["path"]
    with path.open("ab") as handle:
        handle.write(b"\n% changed\n")
    assert family()["publication"]["state"] == "stale_sources_review_required"
    assert family()["publication"]["verified_claims"] == 0


def test_shared_service_inventory_does_not_create_database_or_use_model(research, monkeypatch):
    idx, _, _ = research
    from scripts.deployment_inventory import inventory
    reader = knowledge_service.KnowledgeService(idx.root, idx.root / "absent.sqlite3")
    monkeypatch.setattr(reader, "store", lambda: pytest.fail("Read-only inventory must not open or migrate a store"))
    report = reader.validation()
    assert report["family_count"] == 2
    assert not reader.db_path.exists()
    data = inventory(idx.root)
    assert data["read_only"] and data["network_calls"] == data["model_calls"] == 0
    assert data["coverage"]["family_count"] == 2
    assert not reader.db_path.exists()


def test_shared_index_refreshes_on_source_change(research):
    idx, _, _ = research
    reader = knowledge_service.KnowledgeService(idx.root, idx.root / "absent.sqlite3")
    original = reader.index()
    assert reader.index() is original
    path = idx.root / next(iter(idx.documents.values()))["path"]
    with path.open("ab") as handle:
        handle.write(b"\n% changed\n")
    assert reader.index() is not original


def test_versioned_catalogue_preserves_rows_and_holds_previous_publication(research):
    from catalogue_versions import CatalogueLibrary, preview
    idx, store, _ = research
    save_claim(idx, store)
    proposal = publication_preview(idx, store, "publisher")
    store.publish(proposal["proposal_id"], idx.baseline(), "publisher")
    source = idx.root / "data" / "new.csv"
    source.write_text("Family,Internal,Code,Name\nTEST_FAMILY,NEW,SAME,First\nTEST_FAMILY,,SAME,Second\n", encoding="utf-8")
    original = source.read_bytes()
    mapping = {"family_id":"Family","our_sku":"Internal","supplier_sku":"Code","product_name":"Name"}
    data = preview(idx.root, source, mapping)
    assert len(data["payload"]["rows"]) == 2
    assert len({r["sku_record_id"] for r in data["payload"]["rows"]}) == 2
    assert data["payload"]["duplicate_codes"] and data["payload"]["blank_code_rows"]
    assert data["payload"]["approval_transfer"] is False
    library = CatalogueLibrary(idx.root)
    library.stage(data)
    assert (library.directory / (data["version_id"][:16]+".source.csv")).read_bytes() == original
    assert ResearchIndex(idx.root).by_sku.keys() == idx.by_sku.keys()
    library.activate(data["version_id"], data["version_id"], None)
    fresh = ResearchIndex(idx.root)
    assert len(fresh.skus) == 2
    assert all(row["bot_content_status"] == "HOLD" and row["recommendation_eligible"] == "False" for row in fresh.skus)
    assert active_effective(fresh, store)["state"] == "stale_sources_review_required"
    assert source.read_bytes() == original
    with pytest.raises(ValueError, match="changed"):
        library.activate(data["version_id"], data["version_id"], None)
    source.write_text("Family,Internal,Code,Name\nUNKNOWN,NEW,X,Unknown\n")
    bad = preview(idx.root, source, mapping)
    library.stage(bad)
    with pytest.raises(ValueError, match="resolved"):
        library.activate(bad["version_id"], bad["version_id"], data["version_id"])


def test_catalogue_admin_auth_preview_stage_and_activation(research):
    import hashlib
    from catalogue_versions import CatalogueLibrary
    idx, store, client = research
    assert client.get("/admin/catalogue").status_code == 200
    assert client.get("/api/research/catalogue").status_code == 401
    source = idx.root / "data" / "admin.csv"
    source.write_text("family_id,our_sku,supplier_sku,product_name\nTEST_FAMILY,NEW,CODE,New row\n")
    payload = {"source": str(source), "mapping": {key: key for key in
               ("family_id", "our_sku", "supplier_sku", "product_name")}, "sheet": None}
    login = client.post("/api/research/login", json={"username": "reviewer", "password": "Synthetic password only!"},
                        headers={"Origin": "http://testserver"}).json()
    headers = {"Origin": "http://testserver", "X-Research-CSRF": login["csrf"]}
    assert client.post("/api/research/catalogue/preview", json={"data": payload}).status_code == 403
    assert client.post("/api/research/catalogue/preview", json={"data": payload},
                       headers={**headers, "Origin": "http://elsewhere"}).status_code == 403
    assert client.post("/api/research/catalogue/preview", json={"data": {
        **payload, "mapping": {**payload["mapping"], "active": []}}}, headers=headers).status_code == 400
    data = client.post("/api/research/catalogue/preview", json={"data": payload}, headers=headers).json()
    library = CatalogueLibrary(idx.root)
    assert library.active_id() is None and not library.directory.exists()
    forged = json.loads(json.dumps(data))
    forged["payload"]["rows"][0]["bot_content_status"] = "READY"
    forged["payload"]["rows"][0]["recommendation_eligible"] = "True"
    forged["version_id"] = hashlib.sha256(canonical(forged["payload"]).encode()).hexdigest()
    assert client.post("/api/research/catalogue/stage", json={"data": {"preview": forged}},
                       headers=headers).status_code == 400
    assert not library.directory.exists()
    original = source.read_text()
    source.write_text(original + "TEST_FAMILY,SECOND,OTHER,Second row\n")
    assert client.post("/api/research/catalogue/stage", json={"data": {"preview": data}},
                       headers=headers).status_code == 400
    source.write_text(original)
    assert client.post("/api/research/catalogue/stage", json={"data": {"preview": data}},
                       headers=headers).status_code == 200
    overview = client.get("/api/research/catalogue").json()
    assert overview["active_id"] is None and overview["versions"][0]["version_id"] == data["version_id"]
    activation = {"version_id": data["version_id"], "confirm": data["version_id"], "expected_active_id": None}
    assert client.post("/api/research/catalogue/activate", json={"data": activation}, headers=headers).status_code == 403
    client.post("/api/research/logout", headers=headers)
    login = client.post("/api/research/login", json={"username": "publisher", "password": "Synthetic password only!"},
                        headers={"Origin": "http://testserver"}).json()
    headers["X-Research-CSRF"] = login["csrf"]
    assert client.get("/api/research/catalogue").status_code == 200
    assert client.post("/api/research/catalogue/preview", json={"data": payload}, headers=headers).status_code == 403
    assert client.post("/api/research/catalogue/activate", json={"data": {
        "version_id": data["version_id"], "confirm": data["version_id"]}}, headers=headers).status_code == 400
    assert client.post("/api/research/catalogue/activate", json={"data": {
        **activation, "confirm": "wrong"}}, headers=headers).status_code == 400
    assert client.post("/api/research/catalogue/activate", json={"data": activation}, headers=headers).status_code == 200
    assert client.post("/api/research/catalogue/activate", json={"data": activation}, headers=headers).status_code == 409
    assert all(row["bot_content_status"] == "HOLD" for row in ResearchIndex(idx.root).skus)
    assert store.active() is None


@pytest.mark.parametrize("corruption", ["json", "checksum", "filename", "shape"])
def test_catalogue_overview_surfaces_invalid_record(research, corruption):
    idx, _, client = research
    from catalogue_versions import CatalogueLibrary, preview
    source = idx.root / "data" / "admin.csv"
    source.write_text("family_id,our_sku,supplier_sku,product_name\nTEST_FAMILY,NEW,CODE,New row\n")
    data = preview(idx.root, source, {key: key for key in ("family_id", "our_sku", "supplier_sku", "product_name")})
    path = CatalogueLibrary(idx.root).stage(data)
    if corruption == "json":
        path.write_text("{invalid")
    elif corruption == "shape":
        path.write_text("[]")
    elif corruption == "filename":
        path.rename(path.with_name("wrong.json"))
    else:
        data["payload"]["rows"][0]["product_name"] = "tampered"
        path.write_text(json.dumps(data))
    client.post("/api/research/login", json={"username": "reader", "password": "Synthetic password only!"},
                headers={"Origin": "http://testserver"})
    result = client.get("/api/research/catalogue")
    assert result.status_code == 422
    assert "Local catalogue data invalid" in result.json()["detail"]


def test_knowledge_validation_reports_filesystem_time_not_publication(research):
    from datetime import datetime, timezone
    idx, _, _ = research
    path = idx.root / next(iter(idx.documents.values()))["path"]
    os.utime(path, (1700000000, 1700000000))
    for row in knowledge_service.knowledge_validation(ResearchIndex(idx.root))["families"]:
        for doc in row["source"]["documents"]:
            if doc["exists"]:
                assert doc["last_modified"] == datetime.fromtimestamp(1700000000, timezone.utc).isoformat()
                assert "publication_date" not in doc


def test_catalogue_admin_edge_end_to_end_and_preview_cleanup(research, tmp_path):
    import socket
    import threading
    import uvicorn
    websocket = pytest.importorskip("websocket")
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not edge.is_file():
        pytest.skip("Installed Edge unavailable")
    idx, store, client = research
    store.create_user("catalogue-admin", "Synthetic password only!", ["reviewer", "publisher"])
    source = idx.root / "data" / "browser.csv"
    source.write_text("family_id,our_sku,supplier_sku,product_name\nTEST_FAMILY,NEW,CODE,Browser row\n")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        debug_port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    process = None
    connection = None
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if time.monotonic() > deadline:
                pytest.fail("Synthetic catalogue server failed to start")
            time.sleep(.05)
        process = subprocess.Popen([
            str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
            "--remote-allow-origins=http://localhost", f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={tmp_path / 'catalogue-edge'}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 20
        while True:
            try:
                with opener.open(f"http://127.0.0.1:{debug_port}/json/list", timeout=1) as response:
                    page = next(p for p in json.load(response) if p["type"] == "page")
                break
            except (OSError, StopIteration):
                if time.monotonic() > deadline:
                    raise
                time.sleep(.1)
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30,
                                                 origin="http://localhost", http_proxy_host=None)
        sequence = 0

        def command(method, params):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params}))
            while True:
                result = json.loads(connection.recv())
                if result.get("id") == sequence:
                    assert "error" not in result, result
                    return result.get("result", {})

        command("Runtime.enable", {})
        command("Page.navigate", {"url": f"http://127.0.0.1:{port}/admin/catalogue"})
        deadline = time.monotonic() + 20
        while True:
            ready = command("Runtime.evaluate", {"expression": "typeof browse==='function' && !!document.getElementById('previewForm')",
                                                 "returnByValue": True})
            if ready.get("result", {}).get("value"):
                break
            if time.monotonic() > deadline:
                pytest.fail("Catalogue page script did not load")
            time.sleep(.05)
        script = """
(async()=>{
 const assert=(ok,text)=>{if(!ok)throw new Error(text);};
 const wait=async()=>{for(let i=0;i<100&&controllers.size;i++)await new Promise(r=>setTimeout(r,20));};
 await wait();
 window.confirm=()=>true;
 $('username').value='catalogue-admin';$('password').value='Synthetic password only!';
 await $('loginForm').onsubmit();
 assert(account?.roles.includes('publisher')&&!$('workspace').hidden,'Sign-in failed');
 $('source').value='data/browser.csv';
 await $('previewForm').onsubmit();
 assert(previewResult&&previewResult.payload.rows[0].bot_content_status==='HOLD','Preview lost HOLD');
 const oldStage=$('previewArea').querySelector('button');
 $('source').dispatchEvent(new Event('input',{bubbles:true}));
 assert(!previewResult&&!$('previewArea').children.length,'Input retained stale preview');
 await oldStage.onclick();
 assert(!(await api('/catalogue')).versions.length,'Detached button staged stale preview');
 await $('previewForm').onsubmit();
 const identifier=previewResult.version_id;
 await $('previewArea').querySelector('button').onclick();
 assert(!previewResult&&$('versions').textContent.includes(identifier),'Stage/full confirmation ID missing');
 const confirmInput=$('versions').querySelector('input');
 confirmInput.value=identifier;
 await $('versions').querySelector('button').onclick();
 assert((await api('/catalogue')).active_id===identifier,'Activation failed');
 $('source').value='data/browser.csv';
 await $('previewForm').onsubmit();
 assert(previewResult,'Second preview missing');
 $('source').value='data/missing.csv';
 await $('previewForm').onsubmit();
 assert(!previewResult&&!$('previewArea').children.length,'Failed request retained previous preview');
 assert($('message').className==='warning','Failure not surfaced');
 $('source').value='data/browser.csv';await $('previewForm').onsubmit();
 await $('logout').onclick();
 assert(!previewResult&&!account&&$('workspace').hidden&&!$('versions').children.length,'Logout retained private data');
 $('username').value='reader';$('password').value='Synthetic password only!';
 await $('loginForm').onsubmit();
 assert(!account.roles.includes('reviewer')&&$('previewForm').querySelector('button').disabled,'Reader controls enabled');
 assert($('versions').textContent.includes('Currently active'),'Reader cannot list active version');
 const realFetch=window.fetch;
 account={username:'synthetic',roles:['reviewer'],csrf:'synthetic'};
 let release;window.fetch=()=>new Promise(resolve=>release=resolve);
 $('source').value='data/browser.csv';
 const pending=$('previewForm').onsubmit();
 clear();release({ok:true,json:async()=>({version_id:'a'.repeat(64),payload:{rows:[],blockers:[],changes:{added_codes:[],removed_codes:[]}}})});
 await pending;window.fetch=realFetch;
 assert(!previewResult&&!$('previewArea').children.length,'Locked page repopulated');
 return true;
})()
"""
        result = command("Runtime.evaluate", {"expression": script, "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in result, result
        assert result["result"]["value"] is True
        from catalogue_versions import CatalogueLibrary
        assert all(row["bot_content_status"] == "HOLD" for row in CatalogueLibrary(idx.root).active_rows())
        assert store.active() is None
    finally:
        if connection:
            connection.close()
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_explicit_local_intake_reaches_family_index_without_approval(research):
    from local_intake import preview, stage
    idx, store, _ = research
    doc = next(iter(idx.documents.values()))
    manifest = idx.root / "manifest.json"
    manifest.write_text(json.dumps({"documents":[{"path":doc["path"],"family_ids":["TEST_FAMILY","NO_SKU"],"role":"tds"}]}))
    data = preview(idx.root, manifest)
    stage(idx.root, manifest, data["preview_id"])
    fresh = ResearchIndex(idx.root)
    source = fresh.sources.family("NO_SKU")
    assert source["documents"][0]["exists"]
    assert source["documents"][0]["association_status"] == "owner_declared_not_reviewed"
    assert source["documents"][0]["extraction"]["status"] == "text_extracted"
    assert fresh.detail("NO_SKU")["documents"]
    assert store.active() is None
    assert knowledge_service.knowledge_validation(fresh, store)["families_with_verified_claims"] == 0


def test_private_competitor_view_empty_stale_and_scope_mismatch(research):
    idx, store, client = research
    assert client.get("/api/research/competitors").status_code == 401
    login(client, "reader")
    assert client.get("/api/research/competitors").json()["competitors"] == []
    doc = next(iter(idx.documents.values()))
    directory = idx.root / "data" / "local" / "competitors"
    directory.mkdir(parents=True, exist_ok=True)
    candidate = {"competitor_id":"OTHER","name":"<script>literal</script>","our_family_id":"TEST_FAMILY",
                 "claims":[{"metric":"thermal_r","value":2,"unit":"m2.K/W","variant":"50 mm test grade",
                            "scope":"system","test_standard":"AS TEST","test_context":"Different system",
                            "citation":{"path":doc["path"],"sha256":doc["sha256"],"page":1,"quote":"Test grade 50 mm R2.0"}}]}
    (directory / "other.json").write_text(json.dumps(candidate))
    save_claim(idx, store)
    proposal = publication_preview(idx, store, "publisher")
    store.publish(proposal["proposal_id"], idx.baseline(), "publisher")
    result = client.get("/api/research/competitors").json()
    row = result["competitors"][0]
    assert result["public_use"] is False and result["automatic_winner"] is False
    assert row["claims"][0]["review_status"] == "pending_human_review"
    assert row["comparisons"][0]["status"] == "not_equivalent"
    assert "scope" in row["comparisons"][0]["mismatched_fields"]
    assert row["comparisons"][0]["winner"] is None
    assert "<script>" in row["name"]
    body = {"expected_version":0,"data":{"decision":"not_comparable",
            "notes":"System and product test contexts are different.","evidence_hash":row["evidence_hash"]}}
    assert client.post("/api/research/competitors/OTHER/reviews",json=body).status_code == 403
    headers = login(client, "reviewer")
    assert client.post("/api/research/competitors/OTHER/reviews",json=body).status_code == 403
    comparable = {**body,"data":{**body["data"],"decision":"comparable"}}
    assert client.post("/api/research/competitors/OTHER/reviews",json=comparable,headers=headers).status_code == 422
    saved = client.post("/api/research/competitors/OTHER/reviews",json=body,headers=headers)
    assert saved.status_code == 200 and saved.json()["runtime_changed"] is False
    assert client.post("/api/research/competitors/OTHER/reviews",json=body,headers=headers).status_code == 409
    login(client, "reader")
    assert client.get("/api/research/competitors").json()["competitors"][0]["review_state"] == "not_comparable"
    exported = client.get("/api/research/competitors/export")
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    readable = client.get("/api/research/competitors/export?format=text")
    assert readable.status_code == 200 and "not_comparable" in readable.text
    ours = row["our_reviewed_claims"][0]
    for field in ("scope", "test_context"):
        candidate["claims"][0][field] = ours[field]
    (directory / "other.json").write_text(json.dumps(candidate))
    refreshed = client.get("/api/research/competitors").json()["competitors"][0]
    headers = login(client, "reviewer")
    reviewed = client.post("/api/research/competitors/OTHER/reviews",headers=headers,json={
        "expected_version":saved.json()["revision"],"data":{"decision":"comparable",
        "notes":"Exact variant and laboratory fields checked against both current sources.",
        "evidence_hash":refreshed["evidence_hash"]}})
    assert reviewed.status_code == 200
    login(client, "reader")
    assert client.get("/api/research/competitors").json()["competitors"][0]["review_state"] == "comparable"
    candidate["claims"][0]["citation"]["sha256"] = "bad"
    (directory / "other.json").write_text(json.dumps(candidate))
    changed = client.get("/api/research/competitors").json()
    assert changed["errors"] and changed["competitors"][0]["review_state"] == "stale_evidence"
    store.set_disabled("reviewer", True)
    assert client.get("/api/research/competitors").json()["competitors"][0]["review_state"] == "reviewer_disabled"


def test_real_knowledge_report_represents_every_family_without_claiming_approval():
    report = knowledge_service.knowledge_validation(ResearchIndex())
    assert report["family_count"] == 283
    assert report["sku_count"] == 414
    assert report["families_without_skus"] == 253
    assert len({r["family_id"] for r in report["families"]}) == 283
    assert all("complete" not in row for row in report["families"])


def test_auth_permissions_csrf_disabled_users_and_logout(research):
    _, store, client = research
    assert client.get("/api/research/overview").status_code == 401
    assert client.get("/admin/products").status_code == 200
    headers = login(client, "reader")
    assert client.get("/api/research/me").status_code == 200
    assert client.get("/api/research/families").status_code == 200
    assert client.post("/api/research/families/TEST_FAMILY/notes", json={"data": {"text": "note"}}, headers=headers).status_code == 403
    headers = login(client, "reviewer")
    assert client.post("/api/research/refresh", headers={"Origin": "http://evil.invalid", "X-Research-CSRF": headers["X-Research-CSRF"]}).status_code == 403
    assert client.post("/api/research/refresh", headers={"Origin": "http://testserver"}).status_code == 403
    assert client.post("/api/research/publication/preview", headers=headers).status_code == 403
    store.set_disabled("reviewer", True)
    assert client.get("/api/research/me").status_code == 401
    headers = login(client, "reader")
    assert client.post("/api/research/logout", headers=headers).status_code == 200
    assert client.get("/api/research/me").status_code == 401


def test_login_throttle_and_password_never_in_events(research):
    _, store, client = research
    for _ in range(10):
        assert client.post("/api/research/login", json={"username": "reader", "password": "wrong"},
                           headers={"Origin": "http://testserver"}).status_code == 401
    assert client.post("/api/research/login", json={"username": "reader", "password": "wrong"},
                       headers={"Origin": "http://testserver"}).status_code == 429
    with store.connection() as conn:
        assert all("password" not in r["payload"] for r in conn.execute("SELECT payload FROM events"))


def test_notes_optimistic_concurrency_and_immutable_history(research):
    _, store, client = research
    headers = login(client, "reviewer")
    path = "/api/research/families/TEST_FAMILY/notes"
    result = client.post(path, json={"data": {"text": "<script>literal research note</script>"}}, headers=headers)
    assert result.status_code == 200
    assert client.post(path, json={"data": {"text": "stale edit"}}, headers=headers).status_code == 409
    second = client.post(path, json={"expected_version": result.json()["revision"], "data": {"text": "second note"}}, headers=headers)
    assert second.status_code == 200
    assert len(store.history("family:TEST_FAMILY")) == 2
    assert store.active() is None


@pytest.mark.parametrize("field,value", [("page", 2), ("page", True), ("sha256", "bad"), ("quote", "not actually in source text"), ("locator", "pending")])
def test_exact_source_citation_required(research, field, value):
    idx, _, _ = research
    data = claim_review(idx)
    data["citation"][field] = value
    with pytest.raises(ValueError):
        validate_review(idx, "TEST_FAMILY", data, "reviewer")


def test_approval_alone_publish_revoke_and_disabled_reviewer(research):
    idx, store, _ = research
    revision = save_claim(idx, store)
    assert effective_evidence(idx, store)[0]["TEST_FAMILY"] == []
    preview = publication_preview(idx, store, "publisher")
    assert not preview["blockers"]
    assert store.active() is None
    store.publish(preview["proposal_id"], idx.baseline(), "publisher")
    assert effective_evidence(idx, store)[0]["TEST_FAMILY"][0]["value"] == 2
    store.set_disabled("reviewer", True)
    assert active_effective(idx, store)["state"] == "reviewer_disabled_review_required"
    store.set_disabled("reviewer", False)
    save_claim(idx, store, "revoked", revision)
    revocation = publication_preview(idx, store, "publisher")
    store.publish(revocation["proposal_id"], idx.baseline(), "publisher")
    assert effective_evidence(idx, store)[0]["TEST_FAMILY"] == []


@pytest.mark.parametrize("scoped", [False, True])
def test_exact_sku_approval_does_not_unlock_other_shared_code_rows(research, scoped):
    idx, store, _ = research
    save_claim(idx, store)
    data = {"kind": "sku", "sku_record_id": "SKU-ONE", "decision": "approved",
            "rationale": "Exact grade linked and conflicting material corrected.",
            "citation": claim_review(idx)["citation"], "corrections": {"material_type": "Test material"},
            "resolutions": {"wrong material": "Checked and corrected exact material."},
            "duplicate_resolution": "Separate rows retained; citation is only for SKU-ONE test grade.",
            "variant_confirmed": True, "eligibility_requested": True, "evidence_ids": ["TEST-R-50"]}
    validated = validate_review(idx, "TEST_FAMILY", data, "reviewer")
    store.save_revision(validated["target"], "review", validated, "reviewer", 0)
    preview = publication_preview(idx, store, "publisher", scoped=scoped)
    assert not preview["blockers"]
    store.publish(preview["proposal_id"], idx.baseline(), "publisher")
    assert active_effective(idx, store)["eligibility"]["SKU-ONE"]["eligible"]
    assert "SKU-TWO" not in active_effective(idx, store)["eligibility"]
    data["duplicate_resolution"] = ""
    with pytest.raises(ValueError, match="Shared SKU"):
        validate_review(idx, "TEST_FAMILY", data, "reviewer")
    if scoped:
        pdf = idx.root / "data" / "tds" / "synthetic.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"\nchanged source")
        state = active_effective(ResearchIndex(idx.root), store)
        assert state["state"] == "published_with_scoped_holds" and state["eligibility"] == {}
        assert any(row.get("sku_record_id") == "SKU-ONE" for row in state["holds"])


def test_stale_sources_or_reviews_block_publish_and_invalidate_runtime(research):
    idx, store, _ = research
    save_claim(idx, store)
    preview = publication_preview(idx, store, "publisher")
    store.save_revision("family:TEST_FAMILY", "note", {"text": "another note"}, "reviewer", 0)
    with pytest.raises(Conflict):
        store.publish(preview["proposal_id"], idx.baseline(), "publisher")
    preview = publication_preview(idx, store, "publisher")
    store.publish(preview["proposal_id"], idx.baseline(), "publisher")
    path = idx.root / next(iter(idx.documents.values()))["path"]
    with path.open("ab") as handle:
        handle.write(b"\n% source changed\n")
    assert active_effective(idx, store)["state"] == "stale_sources_review_required"
    assert effective_evidence(idx, store)[0]["TEST_FAMILY"] == []
    with pytest.raises(ValueError, match="changed"):
        idx.document(next(iter(idx.documents)))
    fresh = ResearchIndex(idx.root)
    assert publication_preview(fresh, store, "publisher")["blockers"]


def test_api_documents_review_and_explicit_preview_publish(research):
    idx, store, client = research
    doc = next(iter(idx.documents.values()))
    assert client.get("/api/research/documents/"+doc["id"]+"/file").status_code == 401
    headers = login(client, "reviewer")
    assert client.get("/api/research/documents/../secret/file").status_code == 404
    page = client.get("/api/research/documents/"+doc["id"]+"/pages?page=1")
    assert page.status_code == 200 and "R2.0" in page.json()["page"]["text"]
    assert client.get("/api/research/documents/"+doc["id"]+"/pages?page=99").status_code == 404
    result = client.post("/api/research/families/TEST_FAMILY/reviews", json={"data": claim_review(idx)}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["runtime_changed"] is False and store.active() is None
    headers = login(client, "publisher")
    result = client.post("/api/research/publication/preview", headers=headers)
    assert result.status_code == 200, result.text
    proposal = result.json()["proposal_id"]
    assert client.post(f"/api/research/publication/{proposal}/publish", headers=headers).status_code == 200
    assert client.get("/api/research/audit").status_code == 200


def test_runtime_facts_refresh_on_publish_and_revoke(research, monkeypatch):
    idx, store, _ = research
    from product_answers import ProductAnswers
    import research_store
    monkeypatch.setattr(research_store, "DEFAULT_DB", store.path)
    answers = ProductAnswers(list(idx.families.values()))
    family = idx.families["TEST_FAMILY"]
    revision = save_claim(idx, store)
    assert "don't have a verified" in answers.metrics(family, "R-value")
    proposal = publication_preview(idx, store, "publisher")
    store.publish(proposal["proposal_id"], idx.baseline(), "publisher")
    assert "thermal_r 2.0" in answers.metrics(family, "R-value")
    save_claim(idx, store, "revoked", revision)
    proposal = publication_preview(idx, store, "publisher")
    store.publish(proposal["proposal_id"], idx.baseline(), "publisher")
    assert "don't have a verified" in answers.metrics(family, "R-value")


@pytest.mark.parametrize("bad", [{"rationale": 5}, {"citation": None}, {"claim": []}, {"kind": ["claim"]},
                               {"applicable_skus": [None]}, {"variant_confirmed": "yes"}])
def test_malformed_review_input_has_explicit_error(research, bad):
    idx, _, client = research
    headers = login(client, "reviewer")
    data = {**claim_review(idx), **bad}
    result = client.post("/api/research/families/TEST_FAMILY/reviews", headers=headers, json={"data": data})
    assert result.status_code == 400


def test_staged_audit_accepts_annotation_only_without_overwriting_reports(research):
    idx, store, client = research
    headers = login(client, "reviewer")
    payload = {"baseline": idx.baseline(), "status": "validated", "accuracy_score": 99, "human_approval": False}
    with store.connection() as conn:
        job = conn.execute("INSERT INTO jobs(actor,family_id,kind,state,occurred,payload) VALUES(?,?,?,?,?,?)",
                           ("reviewer", "TEST_FAMILY", "test", "staged", "now", json.dumps(payload))).lastrowid
    result = client.post(f"/api/research/jobs/{job}/accept", json={"data": {}}, headers=headers)
    assert result.status_code == 200
    assert store.active() is None
    assert store.history("family:TEST_FAMILY")[0]["payload"]["human_approval"] is False
    assert not (idx.root / "reports" / "tds_accuracy.json").exists()


def test_template_no_browser_secret_storage_or_unescaped_html():
    page = (ROOT / "templates" / "product_research.html").read_text()
    for forbidden in ("innerHTML", "localStorage", "sessionStorage"):
        assert forbidden not in page
    assert "Family-first" in page and "X-Research-CSRF" in page
    knowledge = (ROOT / "templates" / "knowledge_validation.html").read_text()
    for forbidden in ("innerHTML", "localStorage", "sessionStorage"):
        assert forbidden not in knowledge
    assert "X-Research-CSRF" in knowledge and "controllers" in knowledge
    assert 'link.href="/admin/products#"' in knowledge


@pytest.mark.skipif(not os.getenv("AURORA_TEST_EDGE"), reason="Opt-in installed local Edge UI")
def test_actual_research_browser_family_detail_comparison_and_lock(tmp_path):
    websocket = pytest.importorskip("websocket")
    profile = tmp_path / "edge-profile"
    process = subprocess.Popen([os.environ["AURORA_TEST_EDGE"], "--headless=new", "--disable-gpu",
                               "--no-first-run", "--disable-background-networking", "--disable-component-update",
                               "--disable-sync", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                               f"--user-data-dir={profile}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    connection = None
    try:
        port_file = profile / "DevToolsActivePort"
        for _ in range(100):
            if port_file.exists():
                break
            time.sleep(.1)
        assert port_file.exists()
        port = int(port_file.read_text().splitlines()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
            target = next(p for p in json.load(response) if p["type"] == "page")
        connection = websocket.create_connection(target["webSocketDebuggerUrl"], suppress_origin=True, timeout=20)
        count = 0
        def command(method, params):
            nonlocal count
            count += 1
            connection.send(json.dumps({"id": count, "method": method, "params": params}))
            while True:
                data = json.loads(connection.recv())
                if data.get("id") == count:
                    assert "error" not in data, data
                    return data["result"]
        command("Page.navigate", {"url": (ROOT / "templates" / "product_research.html").as_uri()})
        for _ in range(100):
            if command("Runtime.evaluate", {"expression": "typeof openFamily", "returnByValue": True})["result"].get("value") == "function":
                break
            time.sleep(.1)
        script = """(async()=>{
 const assert=(c,m)=>{if(!c)throw Error(m);};
 account={username:'synthetic',roles:['reader','reviewer'],csrf:'test'};
 const family={family_id:'TEST',name:'<img src=x onerror=alert(1)>',manufacturer:'Test',confidence:'manufacturer_supported'};
 const detail={family,history:[],skus:[],documents:[],evidence:{evidence_items:[]},effective_evidence:[],sources:{source_gaps:['No safety source']},research:{limitations:['Test warning']},published_sku_eligibility:{},publication_state:'baseline_only'};
 detail.dossier={provenance_state:'legacy_supplied_original_unavailable',groups:{installation:[{value:'<img src=x> retained installation',origin:'legacy.md',status:'retained_not_reviewed'}]},alternatives:[]};
 window.fetch=async(url,opts)=>({ok:true,json:async()=>url.includes('/draft-pack')?{
   state:'private_draft_not_approved',readable:'<img src=x> full retained draft',
   processing_coverage:{validated_chunks:1,total_chunks:3,pending_chunks:2},authoring_stale:true
 }:url.includes('/documents')?{documents:[]}:url.includes('/compare')?{families:[detail,detail]}:detail});
 await openFamily('TEST');
 assert($('detail').textContent.includes('<img src=x'),'Raw text missing');
 assert(!$('detail').querySelector('img'),'Untrusted text created HTML');
 assert($('detail').textContent.includes('Child SKUs (0)'),'No-SKU family absent');
 assert($('detail').textContent.includes('Test warning'),'Research details absent');
 assert($('detail').textContent.includes('Combined retained family knowledge'),'Dossier absent');
 assert($('detail').textContent.includes('legacy_supplied_original_unavailable'),'Legacy provenance absent');
 assert($('detail').textContent.includes('retained installation'),'Retained field absent');
 await [...$('detail').querySelectorAll('button')].find(b=>b.textContent==='Read stored draft').onclick();
 assert($('detail').textContent.includes('<img src=x> full retained draft'),'Stored readable draft missing');
 assert(!$('detail').querySelector('img'),'Stored draft created HTML');
 assert($('detail').textContent.includes('1/3 validated; 2 pending'),'Processing coverage missing');
 assert($('detail').textContent.includes('STALE'),'Stale draft warning missing');
 assert($('reviewFamily').textContent===family.name,'Family-first review missing');
 compareIDs.add('TEST');compareIDs.add('SECOND');await $('compare').onclick();
 assert($('compareContent').children.length===2,'Family comparison failed');
 let release;window.fetch=()=>new Promise(r=>release=r);
 const pending=openFamily('TEST');clear();release({ok:true,json:async()=>detail});
 try{await pending;}catch(e){assert(e.name==='AbortError','Unexpected lock error');}
 assert(!selected&&$('detail').children.length===0&&$('workspace').hidden,'Locked page repopulated');
 assert(!account&&$('quote').value==='','Sensitive state retained');
 return 'passed';
})()"""
        result = command("Runtime.evaluate", {"expression": script, "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in result, result
        assert result["result"]["value"] == "passed"
        command("Page.navigate", {"url": (ROOT / "templates" / "storefront_chat.html").as_uri()+"?site_id=synthetic"})
        for _ in range(100):
            if command("Runtime.evaluate", {"expression":"typeof start","returnByValue":True})["result"].get("value")=="function":
                break
            time.sleep(.1)
        script="""(async()=>{
 const assert=(c,m)=>{if(!c)throw Error(m);};
 const calls=[];
 window.fetch=async(url,options)=>{
  calls.push({url,options});
  return {ok:true,json:async()=>url.includes('/messages')?{reply:'<img src=x> literal answer',done:false}:
   {conversation_id:'synthetic',token:'scoped-public-token',reply:'Synthetic opening',branding:{display_name:'Store One',privacy_text:'Synthetic privacy'}}};
 };
 await start();
 assert(document.getElementById('title').textContent==='Store One','Branding missing');
 input.value='What is this product?';
 document.getElementById('form').dispatchEvent(new Event('submit',{cancelable:true}));
 await new Promise(r=>setTimeout(r,50));
 assert(log.textContent.includes('<img src=x> literal answer'),'Reply missing');
 assert(!log.querySelector('img'),'Reply created untrusted HTML');
 assert(calls.at(-1).options.headers['X-Chat-Token']==='scoped-public-token','Scoped token absent');
 assert(!calls.at(-1).options.headers['X-API-Key'],'Privileged site key leaked');
 assert(calls.at(-1).options.credentials==='omit','Third-party cookie dependency');
 return 'passed';
})()"""
        result=command("Runtime.evaluate",{"expression":script,"awaitPromise":True,"returnByValue":True})
        assert "exceptionDetails" not in result,result
        assert result["result"]["value"]=="passed"
        command("Page.navigate", {"url": (ROOT / "templates" / "knowledge_validation.html").as_uri()})
        for _ in range(100):
            if command("Runtime.evaluate", {"expression": "typeof browse", "returnByValue": True})["result"].get("value") == "function":
                break
            time.sleep(.1)
        script = """(async()=>{
 const assert=(c,m)=>{if(!c)throw Error(m);};
 account={username:'reader',roles:['reader'],csrf:'test'};
 const f={family_id:'NO_SKU',name:'<img src=x onerror=alert(1)>',manufacturer:'Test',identity_state:'unknown',
 guide:{state:'missing'},research_status:'ok',audit_status:'no_report',
 source:{held_count:0,linked_count:0,integrity:'no_linked_source',documents:[]},
 extraction:{status:'no_linked_source',states:{}},review:{status:'no_human_review',decisions:{}},
 publication:{state:'baseline_only',verified_claims:0,eligible_skus:0},sku_count:0,gaps:['No source'],next_action:'Supply local source'};
 const report={family_count:1,families_with_linked_sources:0,document_count:0,families_with_verified_claims:0,
 families_without_skus:1,publication_state:'baseline_only',errors:[],manufacturers:['Test'],total:1,families:[f]};
 window.fetch=async()=>({ok:true,json:async()=>report});
 await enter();
 assert($('families').textContent.includes('<img src=x'),'Literal family name missing');
 assert(!$('families').querySelector('img'),'Untrusted family name created HTML');
 assert($('families').textContent.includes('0 child records'),'No-SKU state lost');
 assert($('families').textContent.includes('no_human_review'),'Review state missing');
 assert($('families').querySelector('a').getAttribute('href')==='/admin/products#NO_SKU','Research link missing');
 let release;window.fetch=()=>new Promise(r=>release=r);
 const pending=browse();clear();release({ok:true,json:async()=>report});
 try{await pending;}catch(e){assert(e.name==='AbortError','Unexpected clear error');}
 assert($('families').children.length===0&&$('workspace').hidden&&!account,'Cleared page repopulated');
 return 'passed';
})()"""
        result = command("Runtime.evaluate", {"expression": script, "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in result, result
        assert result["result"]["value"] == "passed"
    finally:
        if connection:
            connection.close()
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=20)
