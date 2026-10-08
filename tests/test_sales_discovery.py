"""Adaptive discovery, private briefs and offline source review contracts."""
import asyncio
import hashlib
import json
import urllib.request
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import agent_core
import interaction_store
import web_agent
from conversation_service import ConversationService
from local_source_review import SourceReview, extract_pages, local_document
from sales_brief import SalesBriefBuilder
from session_store import SQLiteSessionStore


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", tmp_path / "interactions.sqlite3")
    return ConversationService(use_llm=False)


def test_brick_wall_discovers_installation_before_contact_and_preserves_answers(service):
    state = agent_core.Conversation()
    result = service.handle(state, "Cold existing external brick wall with plasterboard in my home in Sydney 2000")
    assert state.pending_field == "wall_assembly"
    assert "brick veneer" in result.reply and "email" not in result.reply
    script = {
        "wall_assembly": "brick veneer",
        "access": "We will remove the plasterboard",
        "cavity_depth": "90mm",
        "area": "20 square metres",
        "existing_insulation": "none",
        "moisture": "no",
        "airspace": "unknown",
        "requirements": "No specified requirements",
        "timeframe": "next month",
    }
    visited = []
    while state.pending_field:
        key = state.pending_field
        assert key in script and key not in visited
        visited.append(key)
        result = service.handle(state, script[key])
        state = agent_core.Conversation.from_dict(state.to_dict())
    assert len(visited) >= 8 and state.capturing_lead
    assert agent_core.HANDOFF_CONSENT_PROMPT in result.reply
    result = service.handle(state, "yes")
    assert agent_core.LEAD_CONSENT_TEXT in result.reply
    service.handle(state, "synthetic@example.com")
    result = service.handle(state, "skip")
    assert state.done and "not booked" in result.reply
    saved = interaction_store.leads()[0]
    brief = saved["sales_brief"]
    assert brief["capture_completeness"]["unresolved_fields"] == ["airspace"]
    assert brief["capture_completeness"]["field_status"]["airspace"] == "unknown"
    assert "90mm" in brief["known_facts"]["cavity_depth"]
    assert saved["recommended_families"] == [] and brief["approval"] is None
    assert len(brief["candidates"]) > 1
    assert len(brief["operator_questions"]) == 1  # No repeated basic questions.


def test_volunteered_multiple_details_skip_questions_without_misfiling(service):
    state = agent_core.Conversation()
    service.handle(state, "My external wall is cold")
    assert state.pending_field == "project_stage"
    service.handle(state, "Timber frame, 90mm cavity depth, no insulation, 20 square metres, residential retrofit in Sydney 2000")
    assert state.pending_field == "access"
    assert "Timber" in state.answers["construction"]
    assert "90mm" in state.answers["cavity_depth"]
    assert "residential" in state.answers["building_use"]
    assert "retrofit" in state.answers["project_stage"]
    assert "20 square" in state.answers["area"]
    assert state.answers["placement"] == "My external wall is cold"


def test_unknown_and_skip_are_recorded_not_invented_or_repeated(service):
    state = agent_core.Conversation()
    service.handle(state, "My wall is cold")
    assert state.pending_field == "placement"
    service.handle(state, "unknown")
    assert state.pending_field == "project_stage"
    service.handle(state, "skip")
    assert state.pending_field == "building_use"
    assert state.discovery_status["placement"] == "unknown"
    assert state.discovery_status["project_stage"] == "skipped"
    service.handle(state, "finish now")
    service.handle(state, "no thanks")
    brief = interaction_store.leads()[0]["sales_brief"]
    assert brief["discovery_ended_early"]
    assert "project_stage" in brief["capture_completeness"]["unresolved_fields"]


def test_later_checked_detail_replaces_unknown_without_answering_another_question(service):
    state = agent_core.Conversation(
        mode="discovery", step=1, pending_field="requirements",
        answers={"problem": "cold wall", "application": "external wall", "airspace": "unknown"},
        discovery_status={"airspace": "unknown"},
    )
    service.handle(state, "We checked: there is a 25mm airspace")
    assert "unknown" not in state.answers["airspace"]
    assert state.discovery_status["airspace"] == "provided"
    assert "requirements" not in state.answers


def test_depth_answer_is_not_a_fuzzy_product_query_and_interruption_does_not_advance(service):
    state = agent_core.Conversation()
    service.handle(state, "Cold external wall in my existing home")
    result = service.handle(state, "90mm cavity depth")
    assert result.category == "product-fit"
    assert "90mm" in state.answers["cavity_depth"]
    assert "Ametalin" not in result.reply
    pending = state.pending_field
    service.handle(state, "Tell me about NuWrap 5")
    result = service.handle(state, "What is it used for?")
    assert "NuWrap 5" in result.reply and state.pending_field == pending
    service.handle(state, "Timber frame")
    assert state.pending_field == "access"


def test_pipe_discovery_asks_service_not_wall_questions(service):
    state = agent_core.Conversation()
    service.handle(state, "Noise from a waste pipe in my existing home")
    service.handle(state, "the pipe itself")
    assert state.pending_field == "service_temperature"
    assert "construction" not in agent_core.discovery.fields_for(state.answers)
    assert "airspace" not in agent_core.discovery.fields_for(state.answers)


def test_correction_after_email_reopens_relevant_discovery_without_losing_contact(service):
    state = agent_core.Conversation()
    service.handle(state, "Cold external wall in my existing home")
    service.handle(state, "finish now")
    service.handle(state, "synthetic@example.com")
    # Restart discovery on an element correction, unless explicitly asking to finish.
    state.discovery_ended_early = False
    result = service.handle(state, "Actually it is the roof, not the wall")
    assert "roofline" in result.reply and state.pending_field == "placement"
    assert "construction" not in state.answers
    assert state.lead["email"] == "synthetic@example.com" and state.lead_step == 1
    service.handle(state, "finish now")
    result = service.handle(state, "What is R-value?")
    assert result.category == "informational" and not state.done
    service.handle(state, "skip")
    assert state.done


def test_legacy_recommendation_removed_but_contact_and_discovery_retained():
    state = agent_core.Conversation.from_dict({
        "step": 8, "mode": "selection", "answers": {"problem": "cold wall"},
        "recommendation": {"family_id": "THERMOTEC_E_THERM", "name": "E-Therm"},
        "candidates": [{"name": "E-Therm"}], "topic_products": ["THERMOTEC_E_THERM"],
        "lead": {"email": "synthetic@example.com"}, "lead_step": 1,
    })
    assert state.recommendation is None and state.candidates == [] and state.topic_products == []
    assert state.lead["email"] and state.lead_step == 1 and state.mode == "capture"


def test_wall_candidates_are_multiple_internal_only_and_offline(monkeypatch):
    monkeypatch.setenv("USE_HYBRID_RANKING", "true")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("Brief must be offline"))
    result = SalesBriefBuilder(agent_core.FAMILIES).build({"problem": "retrofit thermal insulation behind a brick wall with plasterboard", "application": "wall", "priority": "thermal"})
    candidates = {c["family_id"]: c for c in result["candidates"]}
    assert len(candidates) > 1
    assert "FLETCHER_PINK_BATTS_WALL" in candidates
    assert candidates["THERMOTEC_E_THERM"]["disposition"] == "HOLD"
    assert candidates["THERMOTEC_E_THERM"]["evidence"]["source_gaps"]
    assert all("match_score" not in c and "confidence" not in c for c in candidates.values())
    assert result["approval"] is None and result["delivery_status"] == "saved_locally_not_sent"


def test_no_access_and_no_airspace_do_not_establish_fit():
    selected = [f for f in agent_core.FAMILIES if f["family_id"] in {"THERMOTEC_E_THERM", "FLETCHER_PINK_BATTS_WALL"}]
    result = SalesBriefBuilder(selected).build({"problem": "thermal wall retrofit, no access, cannot remove lining, no airspace", "priority": "thermal", "application": "wall"})
    assert len(result["candidates"]) == 2
    for c in result["candidates"]:
        assert any("Restricted installation access" in reason for reason in c["reasons"])
        assert c["disposition"] == ("REJECTED" if c["family_id"] == "THERMOTEC_E_THERM" else "HOLD")


@pytest.mark.parametrize("text", ["help", "a wall", "something needs fixing"])
def test_no_candidate_is_valid_for_insufficient_information(text):
    result = SalesBriefBuilder(agent_core.FAMILIES).build({"problem": text})
    assert result["candidates"] == [] and result["no_candidate_reason"]


def test_backward_compatible_lead_migration(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    interaction_store.save_lead("legacy", site_id="local", problem_statement="old brief", recommended_families=[{"name": "Old family"}], db_path=db)
    with closing(interaction_store.connect(db)) as conn, conn:
        conn.execute("ALTER TABLE leads DROP COLUMN sales_brief_json")
        conn.execute("PRAGMA user_version = 2")
    record = interaction_store.sales_briefs("local", db)[0]
    assert record["problem_statement"] == "old brief"
    assert record["sales_brief"]["decision_status"] == "LEGACY_REQUIRES_REVIEW"
    assert record["sales_brief"]["candidates"][0]["disposition"] == "HOLD"


def test_all_pdf_pages_and_late_warnings_are_retained(tmp_path):
    path = tmp_path / "long.pdf"
    writer = PdfWriter()
    for number in range(14):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        text = ("local technical data " * 100) + ("LATE WARNING: required airspace" if number == 13 else "")
        stream.set_data(f"BT /F1 10 Tf 10 700 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    result = extract_pages(path)
    assert result["page_count"] == 14 and sum(len(p["text"]) for p in result["pages"]) > 16000
    assert "LATE WARNING" in result["pages"][13]["text"]
    assert result["truncated"] is False and result["review_status"] == "pending_human_review"
    assert original == hashlib.sha256(path.read_bytes()).hexdigest() == result["sha256"]


def test_blank_corrupt_and_missing_pdfs_require_review(tmp_path):
    blank = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(blank)
    assert extract_pages(blank)["blank_pages"] == [1]
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a PDF")
    assert extract_pages(corrupt)["status"] == "read_error"
    assert extract_pages(tmp_path / "absent.pdf")["status"] == "read_error"


def test_manifest_escape_hash_mismatch_and_audit_gaps(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.pdf").write_bytes(b"changed")
    manifest = knowledge / "_tds_manifest.json"
    manifest.write_text(json.dumps({"TEST": {"path": "data/sample.pdf", "sha256": "wrong"}}))
    result = SourceReview(tmp_path).family("TEST")
    assert result["documents"][0]["manifest_hash_matches"] is False
    assert any("hash differs" in gap for gap in result["source_gaps"])
    assert any("Full-page" in gap for gap in result["source_gaps"])
    assert any("safety data" in gap for gap in result["source_gaps"])
    assert local_document(tmp_path, r"data\sample.pdf") == (data / "sample.pdf").resolve()
    with pytest.raises(ValueError):
        local_document(tmp_path, "..\\outside.pdf")


@pytest.fixture
def client(tmp_path, monkeypatch):
    asyncio.run(web_agent.startup())
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", tmp_path / "interactions.sqlite3")
    monkeypatch.setattr(web_agent, "session_store", SQLiteSessionStore(tmp_path / "sessions.sqlite3"))
    monkeypatch.setattr(web_agent, "conversation_service", ConversationService(use_llm=False))
    monkeypatch.setenv("AURORA_LEAD_ADMIN_KEY", "synthetic-operator")
    return TestClient(web_agent.app)


def test_public_chat_never_exposes_brief_and_operator_is_site_scoped(client):
    public = {"X-API-Key": "sk_local_dev_test"}
    start = client.post("/api/conversations?site_id=local", headers=public).json()
    route = f"/api/conversations/{start['conversation_id']}/messages?site_id=local"
    for message in ("Retrofit thermal insulation behind a brick wall with plasterboard", "finish now", "synthetic@example.com", "skip"):
        response = client.post(route, headers=public, json={"message": message})
        assert response.status_code == 200
        assert "E-Therm" not in response.text and "Pink Batts" not in response.text
        assert "candidates" not in response.json() and "sales_brief" not in response.json()
    lead = interaction_store.leads()[0]
    for endpoint in ("/api/admin/leads", "/api/admin/briefs", "/api/learning/pending", "/api/learning/rejections"):
        assert client.get(endpoint + "?site_id=local", headers=public).status_code == 401
    operator = {"X-Aurora-Lead-Admin-Key": "synthetic-operator"}
    records = client.get("/api/admin/briefs?site_id=local", headers=operator)
    assert records.status_code == 200 and records.headers["Cache-Control"] == "no-store"
    assert records.json()[0]["sales_brief"]["approval"] is None
    assert records.json()[0]["email"] == "synthetic@example.com"
    assert client.get("/api/admin/briefs?site_id=acme", headers=operator).json() == []
    assert client.get(f"/api/admin/briefs/{lead['conversation_id']}?site_id=acme", headers=operator).status_code == 404
    assert client.get(f"/api/admin/briefs/{lead['conversation_id']}?site_id=local", headers=operator).json() == records.json()[0]
    turns = client.get("/api/admin/interactions?site_id=local", headers=operator)
    assert turns.status_code == 200 and turns.headers["Cache-Control"] == "no-store"
    assert len(turns.json()["turns"]) == 5  # Opening plus every user/assistant exchange.
    assert any(row["user_message"] == "synthetic@example.com" for row in turns.json()["turns"])
    assert any("neo_handoff_not_authorized_by_customer" in row["review_labels"]
               for row in turns.json()["turns"])
    assert client.get("/api/admin/interactions?site_id=local", headers=public).status_code == 401
    assert client.post("/api/learning/outcomes?site_id=acme", headers=operator, json={"conversation_id": lead["conversation_id"], "reviewer": "operator", "outcome": "approved"}).status_code == 400
    assert client.post("/api/learning/outcomes?site_id=local", headers=public, json={"conversation_id": lead["conversation_id"], "reviewer": "widget", "outcome": "approved"}).status_code == 401
    page = client.get("/admin/briefs")
    assert "synthetic@example.com" not in page.text and "E-Therm" not in page.text
    assert "localStorage" not in page.text and "innerHTML" not in page.text


def test_unconfigured_operator_access_is_disabled(client, monkeypatch):
    monkeypatch.delenv("AURORA_LEAD_ADMIN_KEY")
    assert client.get("/api/admin/briefs").status_code == 503
