from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

import neo_api
import matrix_api
from neo_assistant import NeoAssistant, NeoKnowledge
from neo_store import NeoStore


def test_neo_store_uses_its_own_database_and_records(tmp_path):
    store = NeoStore(tmp_path / "neo.sqlite3")
    with store.connection() as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert "neo_conversations" in tables
    assert "neo_records" in tables
    assert "oracle_conversations" not in tables
    assert "sessions" not in tables
    conversation = store.create_conversation("")
    store.add_message(conversation["conversation_id"], "user", "Customer needs acoustic ceiling advice.")
    record = store.save_record("review_task", "Review family", "Needs review.", [])
    assert store.messages(conversation["conversation_id"])[0]["content"].startswith("Customer needs")
    assert store.records()[0]["record_id"] == record["record_id"]


def test_neo_retrieval_never_includes_oracle_pricing_rows(monkeypatch):
    knowledge = NeoKnowledge()
    pricing = {"source_id": "private", "path": "data/local/oracle_pricing/prices.json"}
    product = {"source_id": "public", "path": "knowledge/acme/families.json"}
    monkeypatch.setattr(knowledge.knowledge, "_product_evidence",
                        lambda query, context: ([pricing, product], [
                            {"source_id": "private", "kind": "private_price"},
                            {"source_id": "public", "kind": "family_identity"},
                        ], []))
    result = knowledge.retrieve("compare")
    assert result["citations"] == [{
        **product, "open_url": "/api/neo/sources/public/open",
    }]
    assert result["evidence"] == [{"source_id": "public", "kind": "family_identity"}]


def test_neo_assistant_uses_local_fallback_and_checks_citations(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {
                "evidence": [{"kind": "unreviewed", "status": "unreviewed material",
                              "text": "Local product excerpt.", "source_id": "local"}],
                "citations": [{"source_id": "local", "path": "knowledge/local.md",
                               "status": "owner-maintained"}],
                "candidates": [],
            }

    assistant = NeoAssistant(Knowledge())
    result = assistant.answer("What is documented?", "", [])
    assert "Local product excerpt" in result["answer"]
    assert result["model_status"] == "fallback"

    monkeypatch.setattr("neo_assistant._call_model", lambda *args, **kwargs: "Claim [S8].")
    invalid = assistant.answer("What is documented?", "local-model", [])
    assert invalid["model_status"] == "fallback"
    assert "Claim [S8]" not in invalid["answer"]


def test_neo_api_uses_separate_loopback_session_and_human_review_outputs(monkeypatch, tmp_path):
    database = NeoStore(tmp_path / "neo.sqlite3")
    monkeypatch.setattr(neo_api, "_store", database)
    monkeypatch.setattr(neo_api, "_assistant", type("MockNeo", (), {
        "answer": staticmethod(lambda query, model, history: {
            "answer": "Confirm the current TDS before advising.", "citations": [],
            "model_status": "fallback",
        }),
        "knowledge": type("MockKnowledge", (), {"source_file": staticmethod(lambda source_id: None)})(),
    })())
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))
    started = client.get("/api/neo/session")
    assert started.status_code == 200
    csrf = started.json()["csrf"]
    denied = client.post("/api/neo/conversations", json={"model": ""})
    assert denied.status_code == 403
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}
    created = client.post("/api/neo/conversations", headers=headers, json={"model": ""})
    assert created.status_code == 201
    conversation_id = created.json()["conversation"]["conversation_id"]
    reply = client.post(
        f"/api/neo/conversations/{conversation_id}/messages", headers=headers,
        json={"message": "Customer asks about acoustic ceiling products."},
    )
    assert reply.status_code == 200
    assert reply.json()["message"]["content"].startswith("Confirm the current TDS")
    record = client.post("/api/neo/records", headers=headers, json={
        "conversation_id": conversation_id, "record_type": "sales_brief",
    })
    assert record.status_code == 201
    assert record.json()["production_change"] is False
    assert client.get("/api/neo/records").json()["records"][0]["record_type"] == "sales_brief"

    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.11", 5000))
    assert remote.get("/api/neo/session").status_code == 404
    rebinding = TestClient(app, base_url="http://neo.attacker.invalid",
                           client=("127.0.0.1", 5000))
    assert rebinding.get("/api/neo/session").status_code == 404


def test_matrix_page_is_loopback_only():
    app = FastAPI()
    app.include_router(matrix_api.router)
    local = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))
    result = local.get("/matrix")
    assert result.status_code == 200
    assert all(f">{tab}</button>" in result.text for tab in ("Aurora", "Neo", "Oracle", "Admin"))
    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.12", 5000))
    assert remote.get("/matrix").status_code == 404
    rebinding = TestClient(app, base_url="http://matrix.attacker.invalid",
                           client=("127.0.0.1", 5000))
    assert rebinding.get("/matrix").status_code == 404


def test_matrix_routes_and_neo_are_not_mounted_in_production_or_serving_only(tmp_path):
    root = Path(__file__).resolve().parents[1]
    base_env = {
        **__import__("os").environ,
        "AGENT_USE_LLM": "false",
        "MATRIX_ENABLED": "true",
        "ORACLE_ENABLED": "true",
        "AURORA_ENV": "production",
        "AURORA_SERVING_ONLY": "false",
    }
    production = subprocess.run(
        [sys.executable, "-c",
         "import web_agent; print(hasattr(web_agent, 'matrix_router'), hasattr(web_agent, 'neo_router'))"],
        cwd=root, env=base_env, capture_output=True, text=True, timeout=30,
    )
    assert production.returncode == 0, production.stderr
    assert production.stdout.strip().endswith("False False")

    local_env = {**base_env, "AURORA_ENV": "development"}
    local = subprocess.run(
        [sys.executable, "-c",
         "import web_agent; print(hasattr(web_agent, 'matrix_router'), hasattr(web_agent, 'neo_router'))"],
        cwd=root, env=local_env, capture_output=True, text=True, timeout=30,
    )
    assert local.returncode == 0, local.stderr
    assert local.stdout.strip().endswith("True True")

    disabled = subprocess.run(
        [sys.executable, "-c",
         "import web_agent; print(hasattr(web_agent, 'matrix_router'), hasattr(web_agent, 'neo_router'))"],
        cwd=root, env={**local_env, "MATRIX_ENABLED": "false"},
        capture_output=True, text=True, timeout=30,
    )
    assert disabled.returncode == 0, disabled.stderr
    assert disabled.stdout.strip().endswith("False False")

    release = tmp_path / "release"
    release.mkdir()
    payload = {
        "schema_version": 1, "automatic_selection": False, "families": [],
        "catalogue": [], "evidence": {}, "site_visibility": {"*": []},
        "eligibility": {}, "baseline": {}, "publication_id": "test",
        "revoked": [], "gaps": [],
    }
    from research_store import canonical
    import hashlib

    identifier = hashlib.sha256(canonical(payload).encode()).hexdigest()
    (release / f"{identifier[:16]}.json").write_text(
        canonical({"release_id": identifier, "payload": payload}), encoding="utf-8"
    )
    (release / "active.json").write_text(
        json.dumps({"release_id": identifier, "withdrawals": []}), encoding="utf-8"
    )
    serving_env = {
        **base_env,
        "AURORA_ENV": "development",
        "AURORA_SERVING_ONLY": "true",
        "AURORA_RELEASE_DIR": str(release),
    }
    serving = subprocess.run(
        [sys.executable, "-c",
         "import web_agent; print(hasattr(web_agent, 'matrix_router'), hasattr(web_agent, 'neo_router'))"],
        cwd=root, env=serving_env, capture_output=True, text=True, timeout=30,
    )
    assert serving.returncode == 0, serving.stderr
    assert serving.stdout.strip().endswith("False False")


def test_matrix_tab_contract_and_alpha_manifest_exclusions():
    root = Path(__file__).resolve().parents[1]
    page = (root / "templates" / "matrix.html").read_text(encoding="utf-8")
    for tab in ("Aurora", "Neo", "Oracle", "Admin"):
        assert f">{tab}</button>" in page
    from scripts.package_runtime import FILES, LOCAL_OWNER_ONLY_EXCLUSIONS

    assert not {"matrix_api.py", "neo_api.py", "neo_assistant.py", "neo_store.py"} & set(FILES)
    assert not {"templates/matrix.html", "templates/neo.html"} & set(FILES)
    assert {"matrix_api.py", "neo_api.py", "neo_assistant.py", "neo_store.py",
            "templates/matrix.html", "templates/neo.html", "data/local/neo.sqlite3"} <= set(
                LOCAL_OWNER_ONLY_EXCLUSIONS
            )
    setup = subprocess.run(
        [sys.executable, str(root / "scripts" / "oracle_owner.py"), "--help"],
        cwd=Path(sys.prefix), capture_output=True, text=True, timeout=15,
    )
    assert setup.returncode == 0, setup.stderr
    assert "Create or reset the dedicated Oracle owner passphrase" in setup.stdout
