from types import SimpleNamespace

import pytest

from knowledge_service import KnowledgeService
from source_review_queue import review_view


def compiled():
    return {"state": "compiled", "collection": "frozen", "sources": [
        {"sha256": "abc", "path": "cached.pdf", "url": "", "status": "cached",
         "provenance": "archive_hash", "confidence": "unapproved"},
        {"sha256": "", "path": "", "url": "https://example.invalid",
         "status": "failed", "provenance": "Sheet3 row 2", "confidence": "unapproved"}],
        "documents": [], "unassigned_suggestions": []}


def test_grounded_types_and_human_status_only():
    view = review_view(compiled(), "A")
    assert [i["kind"] for i in view["items"]] == [
        "document_identity_origin_variant", "unavailable_or_held_source"]
    item = view["items"][0]
    history = [{"id": 2, "kind": "source_identity_review",
                "target": "source-review:A:" + item["id"], "actor": "reviewer",
                "payload": {"decision": "accepted", "rationale": "Checked source identity."}}]
    changed = review_view(compiled(), "A", history)["items"][0]
    assert changed["status"] == "accepted" and changed["approval"] is False
    assert changed["source_hash"] == "abc"


def test_review_stale_and_approval_decisions_rejected(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path)
    queue = review_view(compiled(), "A")
    monkeypatch.setattr(service, "family", lambda key: {"source_review_queue": queue})
    item = queue["items"][0]
    data = {"item_id": item["id"], "source_hash": "abc",
            "decision": "approved", "rationale": "Reviewed identity."}
    with pytest.raises(ValueError, match="cannot approve"):
        service.review_source_identity("A", data, "reviewer", 0)
    data["decision"] = "accepted"
    data["source_hash"] = "changed"
    with pytest.raises(ValueError, match="input changed"):
        service.review_source_identity("A", data, "reviewer", 0)
    data["source_hash"] = "abc"
    saved = []
    monkeypatch.setattr(service, "store", lambda: SimpleNamespace(
        save_revision=lambda *args: saved.append(args) or 4))
    result = service.review_source_identity("A", data, "reviewer", 0)
    assert result == {"revision": 4, "public_approval": False, "bindings_changed": False}
    assert saved[0][2]["source_hash"] == "abc"


def test_proposed_match_remains_unbound():
    source = compiled()
    source["unassigned_suggestions"] = [{"sha256": "suggested", "family_id": "A",
                                        "quote": "Product name", "reason": "Exact name match."}]
    items = review_view(source, "A")["items"]
    assert items[-1]["kind"] == "proposed_document_association"
    assert items[-1]["approval"] is False
    assert len(source["sources"]) == 2
