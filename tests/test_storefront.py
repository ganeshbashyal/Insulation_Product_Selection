"""Synthetic storefront boundaries; no live source approval or store deployment."""
from types import SimpleNamespace
from pathlib import Path
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from storefront_api import ChatTokens, build_router, public_origin
from session_store import SQLiteSessionStore
from site_config import SiteConfig
from local_intake import preview, stage


@pytest.fixture
def widget(tmp_path, monkeypatch):
    monkeypatch.setenv("AURORA_STATE_DIR", str(tmp_path))
    sites = {key: SiteConfig(key, key, {"primary": "#000", "accent": "#fff"}, "", "", "phone",
                            phone="test", allowed_origins=["https://"+key+".invalid"])
             for key in ("one", "two")}
    runtime = SimpleNamespace(sites=sites, session_store=SQLiteSessionStore(tmp_path / "sessions.sqlite3"),
                              widget_provider=SimpleNamespace(get_widget_config=lambda key: {"display_name":key, "privacy_text":"Synthetic"}),
                              auth_middleware=SimpleNamespace(check_rate_limit=lambda *args: True),
                              conversation_service=SimpleNamespace(handle=lambda *args, **kwargs:
                                  SimpleNamespace(reply="Synthetic answer", done=False, human_review_required=False)))
    app = FastAPI()
    app.include_router(build_router(runtime))
    return TestClient(app), runtime


def test_widget_frame_requires_known_allowed_parent(widget):
    client, _ = widget
    assert client.get("/widget.js").status_code == 200
    assert client.get("/widget?site_id=one&parent_origin=https://one.invalid").status_code == 200
    assert "frame-ancestors https://one.invalid" in client.get(
        "/widget?site_id=one&parent_origin=https://one.invalid").headers["content-security-policy"]
    assert client.get("/widget?site_id=one&parent_origin=https://two.invalid").status_code == 403
    assert client.get("/widget?site_id=missing&parent_origin=https://one.invalid").status_code == 404
    assert client.get("/widget?site_id=one&parent_origin=https://one.invalid/path").status_code == 400


def test_widget_token_binds_site_and_session_not_operator_access(widget):
    client, _ = widget
    origin = {"Origin": "http://testserver"}
    assert client.post("/api/widget/conversations?site_id=one").status_code == 403
    data = client.post("/api/widget/conversations?site_id=one", headers=origin).json()
    assert "api_key" not in data["branding"]
    headers = {**origin, "X-Chat-Token": data["token"]}
    path = "/api/widget/conversations/"+data["conversation_id"]+"/messages"
    assert client.post(path+"?site_id=one", headers=headers, json={"message":"Hi"}).status_code == 200
    assert client.post(path+"?site_id=two", headers=headers, json={"message":"Hi"}).status_code == 401
    assert client.post(path+"?site_id=one", headers=origin, json={"message":"Hi"}).status_code == 401
    assert client.post(path+"?site_id=one", headers=headers, json={"message":"x"*4001}).status_code == 422
    assert client.post(path+"?site_id=one", headers={**headers,"Origin":"https://evil.invalid"},
                       json={"message":"Hi"}).status_code == 403


def test_widget_page_context_is_origin_checked_sanitized_and_customer_confirmable(widget):
    client, runtime = widget
    origin = {"Origin": "http://testserver"}
    context = {
        "page_url": "https://one.invalid/products/acoustic-panel?customer=private#details",
        "page_type": "product",
        "product_id": "123",
        "variation_id": "456",
        "product_name": "Acoustic panel",
        "product_category": "Ceiling",
        "product_url": "https://one.invalid/products/acoustic-panel?campaign=private",
    }
    response = client.post(
        "/api/widget/conversations?site_id=one",
        headers=origin,
        json={"page_context": context},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page_context"]["page_url"] == "https://one.invalid/products/acoustic-panel"
    assert data["page_context"]["product_url"] == "https://one.invalid/products/acoustic-panel"
    assert data["page_context"]["confirmation"] == "unconfirmed"
    assert "private" not in json.dumps(data["page_context"])
    assert data["page_context"]["product_id"] == "123"

    headers = {**origin, "X-Chat-Token": data["token"]}
    decision_url = f"/api/widget/conversations/{data['conversation_id']}/context?site_id=one"
    assert client.post(decision_url, headers=headers, json={"confirmed": True}).status_code == 200
    assert client.post(decision_url, headers=headers, json={"confirmed": False}).status_code == 409
    session = runtime.session_store.get(data["conversation_id"], "one")
    assert session is not None
    stored = json.loads(session.conversation_json)
    assert stored["page_context"]["confirmation"] == "confirmed"
    assert stored["page_context"]["confirmed_at"]


def test_widget_rejects_foreign_page_and_product_urls(widget):
    client, _ = widget
    origin = {"Origin": "http://testserver"}
    base = {"page_type": "product", "product_id": "123"}
    for context in (
        {**base, "page_url": "https://foreign.invalid/product"},
        {"page_url": "https://one.invalid/product", "product_url": "https://foreign.invalid/product"},
        {"page_url": "https://one.invalid/my-account/orders"},
    ):
        response = client.post(
            "/api/widget/conversations?site_id=one",
            headers=origin,
            json={"page_context": context},
        )
        assert response.status_code == 422
    response = client.post(
        "/api/widget/conversations?site_id=one",
        headers=origin,
        json={"page_context": {"page_url": "https://one.invalid/product?private=value"}},
    )
    assert response.status_code == 200
    assert response.json()["page_context"]["page_url"] == "https://one.invalid/product"


def test_widget_page_context_decision_requires_matching_chat_token(widget):
    client, _ = widget
    origin = {"Origin": "http://testserver"}
    response = client.post(
        "/api/widget/conversations?site_id=one",
        headers=origin,
        json={"page_context": {"page_url": "https://one.invalid/product", "page_type": "product"}},
    )
    data = response.json()
    path = f"/api/widget/conversations/{data['conversation_id']}/context?site_id=one"
    assert client.post(path, headers=origin, json={"confirmed": True}).status_code == 401


def test_page_context_survives_conversation_and_enters_private_sales_brief(monkeypatch):
    import agent_core

    context = {
        "page_url": "https://one.invalid/products/example",
        "page_type": "product",
        "product_id": "123",
        "variation_id": None,
        "product_name": "Example product",
        "product_category": "Ceiling",
        "product_url": "https://one.invalid/products/example",
        "confirmation": "confirmed",
        "confirmed_at": "2026-10-05T10:00:00+00:00",
    }
    conversation = agent_core.Conversation(page_context=context)
    restored = agent_core.Conversation.from_dict(conversation.to_dict())
    assert restored.page_context == context

    saved = {}

    class Builder:
        def __init__(self, families):
            pass

        def build(self, *args, **kwargs):
            return {"candidates": [], "approval": None}

    monkeypatch.setattr("sales_brief.SalesBriefBuilder", Builder)
    monkeypatch.setattr(agent_core.interaction_store, "save_lead", lambda **kwargs: saved.update(kwargs))
    monkeypatch.setattr(agent_core.interaction_store, "log_conversation", lambda **kwargs: None)
    agent_core._finalise_lead(restored, "one")
    assert saved["sales_brief"]["entry_context"] == context

    restored.start_new_project()
    assert restored.page_context is None


def test_tokens_hash_storage_expiry_and_origin_validation(tmp_path):
    store = ChatTokens(tmp_path / "tokens.sqlite3")
    token = store.issue("one", "session")
    assert store.verify(token, "one", "session")
    assert not store.verify(token, "two", "session")
    with store.connect() as conn:
        assert conn.execute("SELECT token_hash FROM widget_tokens").fetchone()[0] != token
        conn.execute("UPDATE widget_tokens SET expires=0")
    assert not store.verify(token, "one", "session")
    for value in ("javascript:alert(1)", "https://one.invalid/?x=1", "https://user:pass@one.invalid", "*",
                  "https://one.invalid; frame-ancestors *", "https://one.invalid\n", "https://one.invalid:bad"):
        with pytest.raises(ValueError):
            public_origin(value)


def test_local_manifest_preserves_pages_and_requires_preview_confirmation(tmp_path):
    from pypdf import PdfWriter

    family = tmp_path / "knowledge" / "test" / "families.json"
    family.parent.mkdir(parents=True)
    family.write_text(json.dumps({"families":[{"family_id":"ONE"},{"family_id":"TWO"}]}))
    pdf = tmp_path / "data" / "tds_inbox" / "source.pdf"
    pdf.parent.mkdir(parents=True)
    writer = PdfWriter()
    for _ in range(15):
        writer.add_blank_page(100,100)
    with pdf.open("wb") as handle:
        writer.write(handle)
    original = pdf.read_bytes()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents":[{"path":"data/tds_inbox/source.pdf",
                                                "family_ids":["ONE","TWO"],"role":"sds"}]}))
    data = preview(tmp_path, manifest)
    assert data["approval"] is False
    assert len(data["documents"][0]["extraction"]["pages"]) == 15
    assert data["documents"][0]["family_ids"] == ["ONE","TWO"]
    assert not (tmp_path / "data/local").exists()
    with pytest.raises(ValueError):
        stage(tmp_path, manifest, "wrong")
    result = stage(tmp_path, manifest, data["preview_id"])
    assert result.is_file()
    assert pdf.read_bytes() == original
    receipt = result.read_bytes()
    assert stage(tmp_path, manifest, data["preview_id"]) == result
    assert result.read_bytes() == receipt


def test_runtime_backup_restore_integrity_and_no_live_overwrite(tmp_path):
    import sqlite3
    from scripts.runtime_backup import backup, restore
    state=tmp_path/"state"
    state.mkdir()
    with sqlite3.connect(state/"sessions.sqlite3") as conn:
        conn.execute("CREATE TABLE synthetic(value TEXT)")
        conn.execute("INSERT INTO synthetic VALUES('private synthetic')")
    target=tmp_path/"backup"
    backup(state,target)
    restored=tmp_path/"restored"
    restore(target,restored)
    with sqlite3.connect(restored/"sessions.sqlite3") as conn:
        assert conn.execute("SELECT value FROM synthetic").fetchone()[0]=="private synthetic"
    with pytest.raises(ValueError,match="empty"):
        restore(target,restored)
    with (target/"sessions.sqlite3").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ValueError,match="checksum"):
        restore(target,tmp_path/"other")
