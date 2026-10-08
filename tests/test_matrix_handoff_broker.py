from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import interaction_store
import matrix_api
import matrix_handoff_store
import neo_api
import web_agent
from neo_store import NeoStore


CONSENT_AT = "2026-10-06T00:00:00+00:00"


def make_payload(**overrides):
    data = {
        "source": "aurora",
        "record_type": "sales_review",
        "handoff_id": hashlib.sha256(b"example-handoff").hexdigest(),
        "customer_context": {"enquiry_type": "insulation_project"},
        "problem_description": "Cold bedroom wall in an existing home.",
        "application_details": {"application": "external wall", "locality": "Sydney 2000"},
        "unknown_fields": ["airspace"],
        "escalation_flags": ["human_review_required_before_product_selection"],
        "provisional_family_candidates": [{
            "family_id": "FLETCHER_PINK_BATTS_WALL",
            "name": "Pink Batts Wall Insulation",
            "review_status": "requires_review",
        }],
        "consent": {
            "project_details_sharing_recorded": True,
            "recorded_at": CONSENT_AT,
            "contact_details_included": False,
        },
    }
    data.update(overrides)
    return matrix_handoff_store.HandoffPayload.model_validate(data)


def test_matrix_registry_is_immutable_and_exposes_no_source_or_contact_data(tmp_path):
    registry = matrix_handoff_store.MatrixHandoffStore(tmp_path / "matrix.sqlite3")
    payload = make_payload()
    metadata, duplicate = registry.publish_approved(
        payload,
        source_site_id="local",
        source_conversation_id="private-conversation-123",
        consent_recorded_at=CONSENT_AT,
        operator_approved=True,
    )

    assert metadata["approval_status"] == "approved"
    assert not duplicate
    assert registry.publish_approved(
        payload,
        source_site_id="local",
        source_conversation_id="private-conversation-123",
        consent_recorded_at=CONSENT_AT,
        operator_approved=True,
    )[1]
    neo_records = registry.approved_for_neo()
    serialized = json.dumps(neo_records)
    assert "private-conversation-123" not in serialized
    assert "source_site_id" not in serialized
    assert "phone" not in serialized.casefold() and "email" not in serialized.casefold()
    assert registry.metadata()[0]["handoff_id"] == payload.handoff_id[:12]
    assert "source_conversation_id" not in json.dumps(registry.metadata())
    with registry.connection() as connection:
        events = connection.execute(
            "SELECT event_type,actor FROM matrix_handoff_events"
        ).fetchall()
    assert [tuple(row) for row in events] == [("approved_handoff_published", "operator")]


def test_matrix_registry_requires_consent_and_operator_approval(tmp_path):
    registry = matrix_handoff_store.MatrixHandoffStore(tmp_path / "matrix.sqlite3")
    with pytest.raises(PermissionError, match="operator approval"):
        registry.publish_approved(
            make_payload(),
            source_site_id="local",
            source_conversation_id="conversation",
            consent_recorded_at=CONSENT_AT,
            operator_approved=False,
        )
    no_consent = make_payload(consent={
        "project_details_sharing_recorded": False,
        "recorded_at": CONSENT_AT,
        "contact_details_included": False,
    })
    with pytest.raises(PermissionError, match="customer consent"):
        registry.publish_approved(
            no_consent,
            source_site_id="local",
            source_conversation_id="conversation",
            consent_recorded_at=CONSENT_AT,
            operator_approved=True,
        )
    with pytest.raises(ValidationError):
        make_payload(consent={
            "project_details_sharing_recorded": True,
            "recorded_at": CONSENT_AT,
            "contact_details_included": True,
        })
    with pytest.raises(ValidationError):
        make_payload(problem_description="Call me at jane@example.com")


def _saved_brief(status: str):
    return {
        "known_facts": {"application": "external wall", "locality": "Sydney 2000"},
        "capture_completeness": {"unresolved_fields": ["airspace"]},
        "candidates": [{
            "family_id": "FLETCHER_PINK_BATTS_WALL",
            "name": "Pink Batts Wall Insulation",
            "disposition": "HOLD",
        }],
        "handoff_consent": {
            "status": status,
            "recorded_at": CONSENT_AT if status == "granted" else None,
            "scope": "non_contact_project_details_for_internal_sales_review",
        },
        "review_labels": ["internal_draft_human_review_required"],
    }


def test_operator_publication_requires_consent_key_and_same_origin(tmp_path, monkeypatch):
    interaction_db = tmp_path / "interactions.sqlite3"
    matrix_db = tmp_path / "matrix.sqlite3"
    monkeypatch.setattr(interaction_store, "DEFAULT_DB", interaction_db)
    monkeypatch.setattr(matrix_handoff_store, "DEFAULT_DB", matrix_db)
    monkeypatch.setattr(matrix_handoff_store, "_store", None)
    monkeypatch.setenv("AURORA_LEAD_ADMIN_KEY", "operator-test-key")
    interaction_store.save_lead(
        "consent-granted",
        site_id="local",
        customer_name="Synthetic Customer",
        phone="0412345678",
        email="synthetic@example.com",
        problem_statement="Cold wall. Contact synthetic@example.com or 0412345678.",
        sales_brief=_saved_brief("granted"),
    )
    interaction_store.save_lead(
        "consent-denied", site_id="local", problem_statement="Cold roof.",
        sales_brief=_saved_brief("declined"),
    )
    client = TestClient(
        web_agent.app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 54321),
    )
    headers = {"X-Aurora-Lead-Admin-Key": "operator-test-key"}
    path = "/api/admin/briefs/consent-granted/handoff?site_id=local"
    assert client.post(path, json={"operator_approved": True}).status_code == 401
    assert client.post(path, headers=headers, json={"operator_approved": True}).status_code == 403
    assert client.post(
        "/api/admin/briefs/consent-denied/handoff?site_id=local",
        headers={**headers, "Origin": "http://127.0.0.1"},
        json={"operator_approved": True},
    ).status_code == 409
    published = client.post(
        path,
        headers={**headers, "Origin": "http://127.0.0.1"},
        json={"operator_approved": True},
    )
    assert published.status_code == 201, published.text
    assert "synthetic@example.com" not in published.text
    assert "0412345678" not in published.text
    handoff = matrix_handoff_store.store().approved_for_neo()[0]
    serialized = json.dumps(handoff, ensure_ascii=False)
    assert "synthetic@example.com" not in serialized
    assert "0412345678" not in serialized
    assert "consent-granted" not in serialized
    assert handoff["payload"]["problem_description"] == "Cold wall. Contact [contact details omitted] or [contact details omitted]."


def test_neo_reads_only_matrix_approved_handoffs(tmp_path, monkeypatch):
    monkeypatch.setattr(matrix_handoff_store, "DEFAULT_DB", tmp_path / "matrix.sqlite3")
    monkeypatch.setattr(matrix_handoff_store, "_store", None)
    monkeypatch.setattr(neo_api, "_store", NeoStore(tmp_path / "neo.sqlite3"))
    registry = matrix_handoff_store.store()
    payload = make_payload()
    registry.publish_approved(
        payload,
        source_site_id="local",
        source_conversation_id="private-conversation-123",
        consent_recorded_at=CONSENT_AT,
        operator_approved=True,
    )
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 54321))
    started = client.get("/api/neo/session")
    assert started.status_code == 200
    csrf = started.json()["csrf"]
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}
    result = client.get("/api/neo/aurora-handoffs")
    assert result.status_code == 200
    serialized = json.dumps(result.json())
    assert "private-conversation-123" not in serialized
    assert "source_site_id" not in serialized
    assert "contact_details_included" in serialized
    rejected_import = client.post(
        "/api/neo/aurora-handoffs",
        headers=headers,
        json=payload.model_dump(),
    )
    assert rejected_import.status_code == 405
    assert not hasattr(neo_api.store(), "save_aurora_handoff")


def test_matrix_status_api_returns_metadata_only(tmp_path, monkeypatch):
    monkeypatch.setattr(matrix_handoff_store, "DEFAULT_DB", tmp_path / "matrix.sqlite3")
    monkeypatch.setattr(matrix_handoff_store, "_store", None)
    matrix_handoff_store.store().publish_approved(
        make_payload(),
        source_site_id="local",
        source_conversation_id="private-conversation-123",
        consent_recorded_at=CONSENT_AT,
        operator_approved=True,
    )
    app = FastAPI()
    app.include_router(matrix_api.router)
    local = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 54321))
    result = local.get("/api/matrix/handoffs")
    assert result.status_code == 200
    assert result.json()["payloads_included"] is False
    assert result.json()["source_identifiers_included"] is False
    assert "private-conversation-123" not in result.text
    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.7", 54321))
    assert remote.get("/api/matrix/handoffs").status_code == 404
