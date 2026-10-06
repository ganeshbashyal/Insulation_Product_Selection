from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import llm_client
import oracle_api
from oracle_assistant import OracleAssistant, OracleKnowledge, _safe_local_path, installed_models, loopback_ollama_base
from oracle_pricing import OraclePricingError, analyze
from oracle_store import OracleStore


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class FakeSources:
    def __init__(self, guide):
        self.guides = {"EXAMPLE_BOARD": guide}
        self.research = {}


class FakeIndex:
    def __init__(self, root: Path):
        self.root = root
        self.families = {
            "EXAMPLE_BOARD": {
                "family_id": "EXAMPLE_BOARD", "name": "Example Board",
                "manufacturer": "Example Maker", "category": "Board",
                "confidence": "manufacturer_supported",
                "source_url": "https://maker.example.invalid/board",
            }
        }
        self.sources = FakeSources(root / "knowledge" / "example" / "board.md")
        self.evidence = {"EXAMPLE_BOARD": {"evidence_items": []}}
        self._detail = {
            "sources": {"documents": [{
                "path": "data/tds/example.pdf", "exists": True, "sha256": "ignored",
                "extraction": {"status": "text_extracted"},
            }]}
        }

    def detail(self, family_id):
        return self._detail


@pytest.fixture
def knowledge(tmp_path):
    write_json(tmp_path / "knowledge/example/families.json", {"families": [{
        "family_id": "EXAMPLE_BOARD", "name": "Example Board", "manufacturer": "Example Maker",
    }]})
    guide = tmp_path / "knowledge/example/board.md"
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text("# Example Board\n\nThis unreviewed guide describes the local board family.\n",
                     encoding="utf-8")
    pdf = tmp_path / "data/tds/example.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"synthetic local pdf bytes")
    compliance = tmp_path / "knowledge/industry/compliance/thermal.md"
    compliance.parent.mkdir(parents=True)
    compliance.write_text("# NCC note\n\nThermal requirements depend on building class and climate zone.",
                          encoding="utf-8")
    chunk_path = tmp_path / "knowledge/industry/training/compliance_rag_chunks.jsonl"
    chunk_path.parent.mkdir(parents=True)
    chunk_path.write_text(json.dumps({
        "topic": "NCC thermal requirements", "source_file": "knowledge/industry/compliance/thermal.md",
        "text": "Thermal requirements depend on building class and climate zone.",
        "scope_note": "Screening aid only.",
    }) + "\n", encoding="utf-8")
    return tmp_path, OracleKnowledge(tmp_path, FakeIndex(tmp_path))


def test_oracle_store_has_dedicated_auth_sessions_and_private_data(tmp_path):
    path = tmp_path / "oracle.sqlite3"
    store = OracleStore(path)
    store.set_passphrase("this is a distinct local Oracle passphrase")

    with pytest.raises(ValueError, match="Invalid Oracle"):
        store.login("wrong passphrase", "127.0.0.1")
    session = store.login("this is a distinct local Oracle passphrase", "127.0.0.1")
    assert store.session(session["token"])["csrf"] == session["csrf"]
    conversation = store.create_conversation("conversation-1", "all", "local", "", {})
    store.add_message(conversation["conversation_id"], "user", "Private owner project note")
    store.save_note("note-1", "Private", "Only Oracle can read this.", [])
    store.save_task("task-1", "Follow up", "", "open", None, [])

    assert store.messages("conversation-1")[0]["content"] == "Private owner project note"
    assert store.notes()[0]["content"] == "Only Oracle can read this."
    assert store.tasks()[0]["title"] == "Follow up"
    raw = path.read_bytes()
    assert b"this is a distinct local Oracle passphrase" not in raw
    assert store.delete_conversation("conversation-1")
    with pytest.raises(KeyError, match="not found"):
        store.messages("conversation-1")


def test_owner_api_requires_loopback_login_and_csrf(monkeypatch, tmp_path):
    db = OracleStore(tmp_path / "oracle.sqlite3")
    db.set_passphrase("test Oracle owner passphrase long enough")
    monkeypatch.setattr(oracle_api, "_store_instance", db)
    monkeypatch.setattr(oracle_api, "_assistant_instance", None)
    app = FastAPI()
    app.include_router(oracle_api.router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))

    assert client.get("/api/oracle/notes").status_code == 401
    login = client.post("/api/oracle/login", headers={"Origin": "http://127.0.0.1"},
                        json={"passphrase": "test Oracle owner passphrase long enough"})
    assert login.status_code == 200
    csrf = login.json()["csrf"]
    assert client.post("/api/oracle/notes", headers={"Origin": "http://127.0.0.1"},
                       json={"title": "Note", "content": "Private"}).status_code == 403
    saved = client.post("/api/oracle/notes", headers={"Origin": "http://127.0.0.1",
                         "X-Oracle-CSRF": csrf}, json={"title": "Note", "content": "Private"})
    assert saved.status_code == 201
    assert client.get("/api/oracle/notes").json()["notes"][0]["content"] == "Private"

    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.10", 5000))
    assert remote.get("/api/oracle/session").status_code == 404
    rebinding = TestClient(app, base_url="http://oracle.attacker.invalid",
                           client=("127.0.0.1", 5000))
    assert rebinding.get("/api/oracle/session").status_code == 404


def test_oracle_conversation_uses_persisted_scope_and_local_fallback(monkeypatch, tmp_path):
    db = OracleStore(tmp_path / "oracle.sqlite3")
    db.set_passphrase("test Oracle owner passphrase long enough")
    monkeypatch.setattr(oracle_api, "_store_instance", db)
    monkeypatch.setattr(oracle_api, "assistant", lambda: type("MockAssistant", (), {
        "answer": staticmethod(lambda query, **kwargs: {
            "answer": "Grounded local evidence only.", "citations": [], "model_status": "fallback",
        })
    })())
    app = FastAPI()
    app.include_router(oracle_api.router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))
    login = client.post("/api/oracle/login", headers={"Origin": "http://127.0.0.1"},
                        json={"passphrase": "test Oracle owner passphrase long enough"})
    headers = {"Origin": "http://127.0.0.1", "X-Oracle-CSRF": login.json()["csrf"]}
    created = client.post("/api/oracle/conversations", headers=headers,
                          json={"scope": "compliance", "environment": "local", "model": "", "context": {}})
    assert created.status_code == 201
    conversation_id = created.json()["conversation"]["conversation_id"]
    reply = client.post(f"/api/oracle/conversations/{conversation_id}/messages", headers=headers,
                        json={"message": "What does the local source say?"})
    assert reply.status_code == 200
    assert reply.json()["model_status"] == "fallback"
    assert db.messages(conversation_id)[-1]["content"] == "Grounded local evidence only."
    with db.connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "sessions" not in tables
    assert "oracle_sessions" in tables


def test_product_and_compliance_searches_are_separate_and_sources_are_openable(knowledge):
    root, adapter = knowledge
    products = adapter.retrieve("Example Board", "products", {})
    compliance = adapter.retrieve("NCC thermal requirements", "compliance", {})

    assert any(row["kind"] == "unreviewed_family_guide" for row in products["evidence"])
    assert any(row["status"].startswith("reference URL") for row in products["citations"])
    assert any(row["path"] == "knowledge/example/board.md" for row in products["citations"])
    assert any(row["kind"] == "compliance_reference" for row in compliance["evidence"])
    assert not any(row.get("family_id") for row in compliance["evidence"])
    local_source = next(row for row in products["citations"] if row["path"] == "knowledge/example/board.md")
    opened = adapter.source_file(local_source["source_id"])
    assert opened and opened[0].read_text(encoding="utf-8").startswith("# Example Board")
    opened[0].write_text("# Changed after citation\n", encoding="utf-8")
    assert adapter.source_file(local_source["source_id"]) is None
    assert adapter.source_file("../outside") is None
    assert _safe_local_path(root, "../outside") is None


def test_linked_tds_pdf_text_is_searchable_and_labelled_unreviewed(monkeypatch, knowledge):
    _, adapter = knowledge
    import local_source_review

    monkeypatch.setattr(local_source_review, "checked_pages", lambda path, expected_hash: {
        "status": "text_extracted",
        "pages": [
            {"page": 1, "text": "General product introduction."},
            {"page": 2, "text": "Thermal resistance is stated for the tested board thickness."},
        ],
    })

    result = adapter.retrieve("thermal resistance", "products", {"family_id": "EXAMPLE_BOARD"})
    excerpts = [row for row in result["evidence"] if row["kind"] == "unreviewed_tds_pdf"]

    assert len(excerpts) == 1
    assert excerpts[0]["locator"] == "PDF page 2"
    assert "unreviewed" in excerpts[0]["status"]
    assert any(row["path"] == "data/tds/example.pdf" for row in result["citations"])


def test_local_source_links_cannot_follow_symlinks_outside_approved_roots(tmp_path):
    root = tmp_path / "repo"
    outside = tmp_path / "private.pdf"
    outside.write_bytes(b"not part of Oracle's source library")
    approved = root / "data" / "tds"
    approved.mkdir(parents=True)
    link = approved / "linked.pdf"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows configuration")
    assert _safe_local_path(root, "data/tds/linked.pdf") is None


def test_local_model_cannot_invent_source_citation(monkeypatch):
    class Knowledge:
        def retrieve(self, query, scope, context):
            return {"evidence": [{"kind": "local", "status": "unreviewed material",
                                  "text": "Local cited excerpt.", "source_id": "abc"}],
                    "citations": [{"source_id": "abc", "path": "knowledge/local.md",
                                   "status": "unreviewed"}], "candidates": [], "scope": scope}

    monkeypatch.setattr("oracle_assistant._call_model", lambda *args, **kwargs: "Claim [S999].")
    result = OracleAssistant(Knowledge()).answer(
        "question", scope="all", context={}, model="local-model", history=[]
    )
    assert result["model_status"] == "fallback"
    assert "invalid citation" in result["answer"]
    assert "Claim [S999]" not in result["answer"]


def test_private_notes_tasks_and_customer_route_exclusions(monkeypatch, tmp_path):
    db = OracleStore(tmp_path / "oracle.sqlite3")
    db.set_passphrase("test Oracle owner passphrase long enough")
    monkeypatch.setattr(oracle_api, "_store_instance", db)
    app = FastAPI()
    app.include_router(oracle_api.router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))
    login = client.post("/api/oracle/login", headers={"Origin": "http://127.0.0.1"},
                        json={"passphrase": "test Oracle owner passphrase long enough"})
    headers = {"Origin": "http://127.0.0.1", "X-Oracle-CSRF": login.json()["csrf"]}

    saved_task = client.post("/api/oracle/tasks", headers=headers, json={
        "title": "Review family", "details": "Inspect cited TDS.", "status": "open",
    })
    assert saved_task.status_code == 201
    assert client.get("/api/oracle/tasks").json()["tasks"][0]["title"] == "Review family"
    invalid_task = client.post("/api/oracle/tasks", headers=headers, json={
        "title": "Bad status", "status": "customer_visible",
    })
    assert invalid_task.status_code == 400

    repo_root = Path(__file__).resolve().parents[1]
    base_env = os.environ.copy()
    base_env.update({"AGENT_USE_LLM": "false", "ORACLE_ENABLED": "true",
                     "AURORA_ENV": "production", "AURORA_SERVING_ONLY": "false"})

    def imports_oracle_router(env):
        return subprocess.run(
            [sys.executable, "-c",
             "import web_agent; print(hasattr(web_agent, 'oracle_router'))"],
            cwd=repo_root, env=env, capture_output=True, text=True, timeout=30,
        )

    local = imports_oracle_router({**base_env, "AURORA_ENV": "development"})
    assert local.returncode == 0, local.stderr
    assert local.stdout.strip().endswith("True")

    disabled = imports_oracle_router({**base_env, "AURORA_ENV": "development",
                                      "ORACLE_ENABLED": "false"})
    assert disabled.returncode == 0, disabled.stderr
    assert disabled.stdout.strip().endswith("False")

    production = subprocess.run(
        [sys.executable, "-c",
         "import web_agent; print(hasattr(web_agent, 'oracle_router'))"],
        cwd=repo_root, env=base_env, capture_output=True, text=True, timeout=30,
    )
    assert production.returncode == 0, production.stderr
    assert production.stdout.strip().endswith("False")

    release_dir = tmp_path / "serving-release"
    payload = {
        "schema_version": 1, "automatic_selection": False, "families": [],
        "catalogue": [], "evidence": {}, "site_visibility": {"*": []},
        "eligibility": {}, "baseline": {}, "publication_id": "test",
        "revoked": [], "gaps": [],
    }
    from research_store import canonical

    release_id = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
    release_dir.mkdir()
    (release_dir / f"{release_id[:16]}.json").write_text(
        canonical({"release_id": release_id, "payload": payload}), encoding="utf-8"
    )
    (release_dir / "active.json").write_text(
        json.dumps({"release_id": release_id, "withdrawals": []}), encoding="utf-8"
    )
    serving_env = {**base_env, "AURORA_ENV": "development", "AURORA_SERVING_ONLY": "true",
                   "AURORA_RELEASE_DIR": str(release_dir)}
    serving = subprocess.run(
        [sys.executable, "-c",
         "import web_agent; print(hasattr(web_agent, 'oracle_router'))"],
        cwd=repo_root, env=serving_env, capture_output=True, text=True, timeout=30,
    )
    assert serving.returncode == 0, serving.stderr
    assert serving.stdout.strip().endswith("False")


def test_compliance_and_products_all_scope_can_be_combined(knowledge):
    _, adapter = knowledge
    result = adapter.retrieve("Example Board NCC thermal requirements", "all", {})
    kinds = {row["kind"] for row in result["evidence"]}
    assert "unreviewed_family_guide" in kinds
    assert "compliance_reference" in kinds


def test_model_selector_and_local_only_host_guard(monkeypatch):
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "https://example.invalid")
    with pytest.raises(RuntimeError, match="local HTTP"):
        loopback_ollama_base()
    with pytest.raises(RuntimeError, match="local HTTP"):
        installed_models()
    monkeypatch.setattr(llm_client, "OLLAMA_HOST", "http://127.0.0.1:11434")
    assert loopback_ollama_base() == "http://127.0.0.1:11434"


def test_oracle_fallback_is_grounded_and_never_calls_model(monkeypatch):
    class Knowledge:
        def retrieve(self, query, scope, context):
            return {"evidence": [{"kind": "unreviewed", "status": "unreviewed material",
                                 "text": "Local cited excerpt.", "source_id": "abc"}],
                    "citations": [{"source_id": "abc", "path": "knowledge/local.md",
                                   "status": "unreviewed"}], "candidates": [], "scope": scope}

    monkeypatch.setattr("oracle_assistant._call_model",
                        lambda *args, **kwargs: pytest.fail("No model selected; fallback only"))
    result = OracleAssistant(Knowledge()).answer("question", scope="all", context={}, model="", history=[])
    assert "Local cited excerpt" in result["answer"]
    assert result["model_status"] == "fallback"


def test_local_pricing_comparison_uses_exact_keys_and_source_metadata(tmp_path):
    directory = tmp_path / "data/local/oracle_pricing"
    write_json(directory / "snapshot.json", {
        "schema_version": 1, "source_name": "Owner's local comparison sheet",
        "currency": "AUD", "region": "AU-NSW", "effective_date": "2026-09-01",
        "prices": [
            {"competitor": "Supplier A", "product_name": "Example Board 50mm",
             "comparison_key": "example board 50mm", "sku": "A-50", "unit": "pack", "price": 80.0},
            {"competitor": "Supplier B", "product_name": "Example Board 50mm",
             "comparison_key": "example board 50mm", "sku": "B-50", "unit": "pack", "price": 92.0},
            {"competitor": "Supplier C", "product_name": "Other Board 100mm",
             "comparison_key": "other board 100mm", "sku": "C-100", "unit": "pack", "price": 110.0},
        ],
    })

    result = analyze(tmp_path, "compare price Example Board 50mm")

    assert result["state"] == "local_snapshot_matches"
    assert len(result["evidence"]) == 2
    assert all("AUD" in row["text"] and "AU-NSW" in row["text"] for row in result["evidence"])
    assert all("not independently verified" in row["status"] for row in result["evidence"])
    assert len(result["sources"]) == 1


def test_invalid_local_pricing_snapshot_fails_explicitly(tmp_path):
    write_json(tmp_path / "data/local/oracle_pricing/bad.json", {
        "schema_version": 1, "source_name": "bad", "currency": "AUD", "region": "AU",
        "effective_date": "2026-01-01", "prices": [{"competitor": "A", "product_name": "Board",
        "comparison_key": "board", "unit": "each", "price": float("nan")}],
    })
    with pytest.raises(OraclePricingError, match="invalid price"):
        analyze(tmp_path, "price Board")
