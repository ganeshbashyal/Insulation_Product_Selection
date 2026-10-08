import copy
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import oracle_assistant
import research_api
import family_assistant
from family_assistant import (
    FamilyAssistantError,
    apply_changes,
    answer,
    build_family_context,
    validate_model_result,
)
from family_assistant_store import FamilyAssistantStore
from research_store import ResearchStore


def sample_detail():
    return {
        "family": {
            "family_id": "FAMILY-ONE",
            "name": "Synthetic family",
            "manufacturer": "Example manufacturer",
            "category": "Batt",
            "source_url": "https://example.invalid/product",
            "buy_price": 50,
            "sell_price": 100,
        },
        "research": {
            "description": "Retained local notes.",
            "status": "needs_review",
            "spec": {"thickness": "90 mm", "buy_cost": 42},
        },
        "sources": {"research_path": "output/research/FAMILY-ONE.json"},
        "documents": [{
            "id": "DOC-ONE", "path": "data/tds/sample.pdf", "exists": True,
            "sha256": "a" * 64, "candidate_fields": [{"value": "90 mm"}],
        }],
        "effective_evidence": [],
    }


def result_json(proposal=None, reply="Verified against [S1]."):
    return json.dumps({"reply": reply, "proposal": proposal})


def test_context_is_family_scoped_and_redacts_commercial_values():
    context = build_family_context(sample_detail(), "FAMILY-ONE")
    serialized = json.dumps(context)
    assert context["family_id"] == "FAMILY-ONE"
    assert [source["source_id"] for source in context["sources"]] == ["S1", "S2", "S3"]
    evidence = json.dumps(context["evidence"])
    assert "buy_price" not in evidence
    assert "sell_price" not in evidence
    assert "buy_cost" not in evidence
    assert "50" not in evidence
    with pytest.raises(FamilyAssistantError, match="unavailable"):
        build_family_context(sample_detail(), "OTHER-FAMILY")


def test_model_response_validation_allows_only_cited_editable_fields():
    context = build_family_context(sample_detail(), "FAMILY-ONE")
    baseline = context["authoring_copy"]["snapshot"]
    proposal = {
        "title": "Clarify description",
        "summary": "Use the retained description.",
        "changes": [{
            "path": "research.description",
            "value": "A local, owner-reviewed description.",
            "evidence_ids": ["S2"],
        }],
    }
    result = validate_model_result(result_json(proposal), context, "", baseline)
    assert result["citations"][0]["source_id"] == "S1"
    assert result["proposal"]["changes"][0]["before"] == "Retained local notes."
    saved = apply_changes(baseline, result["proposal"]["changes"], "FAMILY-ONE")
    assert saved["research"]["description"] == "A local, owner-reviewed description."
    assert baseline["research"]["description"] == "Retained local notes."


@pytest.mark.parametrize("raw", [
    '{"reply":"ok","proposal":null,"extra":true}',
    '{"reply":"ok [S999]","proposal":null}',
    '{"reply":"ok","proposal":{"title":"bad","summary":"bad","changes":[{"path":"family.family_id","value":"X","evidence_ids":["S1"]}]}}',
    '{"reply":"ok","proposal":{"title":"bad","summary":"bad","changes":[{"path":"research.description","value":"x","evidence_ids":[[]]}]}}',
    '{"reply":"ok","proposal":{"title":"bad","summary":"bad","changes":[{"path":"research.description","value":NaN,"evidence_ids":["S1"]}]}}',
])
def test_model_response_rejects_invalid_shape_paths_citations_and_json(raw):
    context = build_family_context(sample_detail(), "FAMILY-ONE")
    with pytest.raises(FamilyAssistantError):
        validate_model_result(raw, context, "owner supplied this", context["authoring_copy"]["snapshot"])


def test_model_response_requires_owner_input_for_owner_citation():
    context = build_family_context(sample_detail(), "FAMILY-ONE")
    with pytest.raises(FamilyAssistantError, match="Owner citation"):
        validate_model_result(result_json(reply="Owner says [OWNER]."), context, " ", {})


def test_local_model_prompt_redacts_commercial_baseline(monkeypatch):
    context = build_family_context(sample_detail(), "FAMILY-ONE")
    captured = {}

    def call_model(model, messages):
        captured["model"] = model
        captured["prompt"] = messages[1]["content"]
        return result_json()

    monkeypatch.setattr(family_assistant, "installed_models", lambda: ["llama:latest"])
    monkeypatch.setattr(family_assistant, "_call_model", call_model)
    result = answer(
        "Review the family facts.", context=context,
        baseline=context["authoring_copy"]["snapshot"],
        model="llama:latest", history=[],
    )
    assert result["reply"] == "Verified against [S1]."
    assert captured["model"] == "llama:latest"
    assert "buy_price" not in captured["prompt"]
    assert "sell_price" not in captured["prompt"]
    assert "buy_cost" not in captured["prompt"]


def test_private_store_isolates_actors_and_versions_approved_copies(tmp_path):
    store = FamilyAssistantStore(tmp_path / "private" / "family.sqlite3")
    store.create_conversation("c1", "reviewer", "FAMILY-ONE", "llama:latest")
    store.create_conversation("c2", "other", "FAMILY-ONE", "gemma:latest")
    store.add_message("c1", "reviewer", "user", "Check the product")
    store.create_proposal(
        proposal_id="p1", conversation_id="c1", actor="reviewer",
        family_id="FAMILY-ONE", title="Update", summary="Test update",
        source_signature="sig", base_revision=0,
        baseline={"family": {"family_id": "FAMILY-ONE"}},
        changes=[{"path": "family.name", "after": "Updated"}],
    )
    assert store.conversation("c1", "other") is None
    assert store.proposal("p1", "other") is None
    saved = store.apply_proposal(
        "p1", "reviewer", source_signature="sig", expected_revision=0,
        snapshot={"family": {"family_id": "FAMILY-ONE", "name": "Updated"}},
    )
    assert saved["revision"] == 1
    assert store.authoring_copy("FAMILY-ONE")["snapshot"]["family"]["name"] == "Updated"
    with pytest.raises(ValueError, match="no longer a draft"):
        store.apply_proposal(
            "p1", "reviewer", source_signature="sig", expected_revision=1,
            snapshot={"family": {"family_id": "FAMILY-ONE"}},
        )


@pytest.fixture
def manager_api(tmp_path, monkeypatch):
    detail = sample_detail()
    canonical_file = tmp_path / "knowledge" / "family.json"
    canonical_file.parent.mkdir(parents=True)
    original_canonical = '{"families":[{"family_id":"FAMILY-ONE"}]}'
    canonical_file.write_text(original_canonical, encoding="utf-8")

    class Index:
        root = tmp_path
        families = {"FAMILY-ONE": detail["family"]}

    class Service:
        def family(self, family_id):
            if family_id != "FAMILY-ONE":
                raise ValueError("Unknown family")
            return copy.deepcopy(detail)

    accounts = ResearchStore(tmp_path / "accounts.sqlite3")
    accounts.create_user("reviewer", "Synthetic password only!", ["reviewer"])
    accounts.create_user("reader", "Synthetic password only!", ["reader"])
    accounts.create_user("other", "Synthetic password only!", ["reviewer"])
    manager = FamilyAssistantStore(tmp_path / "private" / "family.sqlite3")
    monkeypatch.setattr(research_api, "store", lambda: accounts)
    monkeypatch.setattr(research_api, "index", lambda refresh=False: Index())
    monkeypatch.setattr(research_api, "service", lambda: Service())
    monkeypatch.setattr(research_api, "family_assistant_store", lambda: manager)
    monkeypatch.setattr(oracle_assistant, "installed_models", lambda: ["llama:latest"])
    monkeypatch.setattr("local_model.installed_models", lambda: ["llama:latest"])
    monkeypatch.setattr("local_model.chat_models", lambda: ["llama:latest"])

    app = FastAPI()
    app.include_router(research_api.router)
    return TestClient(app), manager, detail, canonical_file, original_canonical


def login(client, username="reviewer"):
    response = client.post(
        "/api/research/login",
        json={"username": username, "password": "Synthetic password only!"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200, response.text
    return {"Origin": "http://testserver", "X-Research-CSRF": response.json()["csrf"]}


def test_manager_routes_enforce_named_reviewer_csrf_and_local_model(manager_api):
    client, _, _, _, _ = manager_api
    page = client.get("/admin/family-manager")
    assert page.status_code == 200
    assert "connect-src 'self'" in page.headers["content-security-policy"]
    assert "Family Knowledge Manager" in page.text
    assert 'headers:{"Content-Type":"application/json"}' in page.text
    path = "/api/research/family-manager/families"
    assert client.get(path).status_code == 401
    login(client, "reader")
    assert client.get(path).status_code == 403
    headers = login(client)
    assert client.get(path).json()["families"][0]["family_id"] == "FAMILY-ONE"
    body = {"family_id": "FAMILY-ONE", "model": "llama:latest"}
    assert client.post("/api/research/family-manager/conversations", json=body).status_code == 403
    assert client.post(
        "/api/research/family-manager/conversations",
        json={**body, "model": "not-installed"}, headers=headers,
    ).status_code == 422
    assert client.post(
        "/api/research/family-manager/conversations",
        json={"family_id": "UNKNOWN", "model": "llama:latest"}, headers=headers,
    ).status_code == 404


def test_api_approval_changes_only_private_copy_and_detects_stale_sources(manager_api, monkeypatch):
    client, manager, detail, canonical_file, original_canonical = manager_api
    headers = login(client)
    monkeypatch.setattr(
        research_api, "family_assistant_answer",
        lambda *args, **kwargs: {
            "reply": "The retained research supports this wording [S2].",
            "citations": [{"source_id": "S2", "path": "output/research/FAMILY-ONE.json",
                           "status": "retained research"}],
            "proposal": {
                "proposal_id": "proposal-one", "title": "Clarify description",
                "summary": "Use the retained description.",
                "changes": [{
                    "path": "research.description",
                    "before": "Retained local notes.",
                    "after": "Updated locally after review.",
                    "evidence_ids": ["S2"], "evidence": [],
                }],
            },
        },
    )
    created = client.post(
        "/api/research/family-manager/conversations",
        json={"family_id": "FAMILY-ONE", "model": "llama:latest"}, headers=headers,
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation"]["conversation_id"]
    sent = client.post(
        f"/api/research/family-manager/conversations/{conversation_id}/messages",
        json={"message": "Please clarify this family description."}, headers=headers,
    )
    assert sent.status_code == 200, sent.text
    proposal = sent.json()["proposal"]
    assert "baseline" not in proposal
    history = client.get(
        f"/api/research/family-manager/conversations/{conversation_id}/messages",
    )
    assert history.status_code == 200
    assert history.json()["proposals"][0]["stale"] is False

    approved = client.post(
        f"/api/research/family-manager/proposals/{proposal['proposal_id']}/approve",
        json={"expected_revision": 0}, headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["canonical_knowledge_changed"] is False
    assert canonical_file.read_text(encoding="utf-8") == original_canonical
    assert manager.authoring_copy("FAMILY-ONE")["snapshot"]["research"]["description"] == (
        "Updated locally after review."
    )
    assert client.get(
        f"/api/research/family-manager/conversations/{conversation_id}/messages",
    ).status_code == 200

    detail["research"]["description"] = "Source record changed after the proposal."
    monkeypatch.setattr(
        research_api, "family_assistant_answer",
        lambda *args, **kwargs: {
            "reply": "Please review [S2].",
            "citations": [{"source_id": "S2", "path": "research", "status": "retained"}],
            "proposal": {
                "proposal_id": "proposal-two", "title": "Second update",
                "summary": "Based on the current source.",
                "changes": [{
                    "path": "research.description", "before": "x", "after": "y",
                    "evidence_ids": ["S2"], "evidence": [],
                }],
            },
        },
    )
    second = client.post(
        f"/api/research/family-manager/conversations/{conversation_id}/messages",
        json={"message": "Review the changed local source."}, headers=headers,
    )
    assert second.status_code == 200
    detail["research"]["description"] = "A newer source update."
    stale = client.post(
        "/api/research/family-manager/proposals/proposal-two/approve",
        json={"expected_revision": 1}, headers=headers,
    )
    assert stale.status_code == 409
    assert canonical_file.read_text(encoding="utf-8") == original_canonical


def test_manager_conversation_and_proposal_are_owner_scoped(manager_api):
    client, _, _, _, _ = manager_api
    headers = login(client)
    created = client.post(
        "/api/research/family-manager/conversations",
        json={"family_id": "FAMILY-ONE", "model": "llama:latest"}, headers=headers,
    )
    conversation_id = created.json()["conversation"]["conversation_id"]
    client.post("/api/research/logout", headers=headers)
    login(client, "other")
    assert client.get(
        f"/api/research/family-manager/conversations/{conversation_id}/messages",
    ).status_code == 404
