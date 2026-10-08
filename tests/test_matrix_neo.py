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
    user_message, assistant_message = store.add_exchange(
        conversation["conversation_id"], "Which ceiling?", "Please check the current source.",
    )
    record = store.save_record("review_task", "Review family", "Needs review.", [])
    messages = store.messages(conversation["conversation_id"])
    assert messages[0]["content"].startswith("Customer needs")
    assert [message["role"] for message in messages[1:]] == ["user", "assistant"]
    assert (user_message["content"], assistant_message["content"]) == (
        "Which ceiling?", "Please check the current source.",
    )
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
    assert result["answer"].startswith("No verified match found.")
    assert result["model_status"] == "fallback"

    assistant.knowledge.retrieve = lambda query: {
        "evidence": [{
            "kind": "verified_claim",
            "status": "verified fact",
            "text": json.dumps({
                "metric_type": "thermal_r_value",
                "value": 2.0,
                "unit": "m²K/W",
                "variant": "R2.0 90mm",
                "scope": "product",
            }),
            "source_id": "local",
        }],
        "citations": [{"source_id": "local", "path": "knowledge/local.md",
                       "status": "verified"}],
        "candidates": [],
    }
    monkeypatch.setattr("neo_assistant._call_model", lambda *args, **kwargs: "Claim [S8].")
    invalid = assistant.answer("What is documented?", "local-model", [])
    assert invalid["model_status"] == "fallback"
    assert "Claim [S8]" not in invalid["answer"]
    assert "R2.0" in invalid["answer"]


def test_neo_does_not_send_unverified_material_to_local_model(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {
                "evidence": [
                    {"kind": "unreviewed_tds_pdf", "status": "unreviewed", "text": "R9.9"},
                ],
                "citations": [{"source_id": "tds", "path": "data/tds/example.pdf"}],
                "candidates": [],
            }

    prompts = []

    def conversational_model(model, messages):
        prompts.extend(messages)
        return "I can't verify that product rating from the supplied approved sources. [S1]"

    monkeypatch.setattr("neo_assistant._call_model", conversational_model)
    result = NeoAssistant(Knowledge()).answer("What is the R-value?", "llama3.2:latest", [])

    assert result["model_status"] == "local_model"
    assert "R9.9" not in prompts[1]["content"]
    assert result["citations"][0]["path"] == "data/tds/example.pdf"


def test_neo_uses_local_model_for_free_flow_without_search_evidence(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {"evidence": [], "citations": [], "candidates": []}

    calls = []

    def local_chat(model, messages):
        calls.append((model, messages))
        return "Hi, happy to help. What has the customer asked?"

    monkeypatch.setattr("neo_assistant._call_model", local_chat)
    result = NeoAssistant(Knowledge()).answer("Hi", "llama3.2:latest", [])

    assert result["model_status"] == "local_model"
    assert result["answer"].startswith("Hi, happy to help")
    assert calls[0][0] == "llama3.2:latest"


def test_neo_retrieval_ignores_greetings_and_normalizes_plural_batts():
    knowledge = NeoKnowledge()
    assert knowledge.retrieve("hi") == {"citations": [], "evidence": [], "candidates": []}
    matches = knowledge.knowledge._product_matches("pink batt", {})
    assert any(
        row["family_id"] in {"FLETCHER_PINK_BATTS_CEILING", "FLETCHER_PINK_BATTS_WALL",
                             "FLETCHER_PINK_BATTS_FLOOR"}
        for row, _ in matches
    )


def test_neo_does_not_choose_between_multiple_live_call_family_candidates():
    class Knowledge:
        def retrieve(self, query):
            return {
                "evidence": [],
                "citations": [],
                "candidates": [
                    "Fletcher / Pink Batts Ceiling",
                    "Fletcher / Pink Batts Floor",
                    "Fletcher / Pink Batts Wall",
                ],
            }

    result = NeoAssistant(Knowledge()).answer("pink batt", "llama3.2:latest", [])

    assert result["model_status"] == "catalogue_clarification"
    assert "Which area is the customer insulating" in result["answer"]
    assert "not confirmation of stock or an exact SKU" in result["answer"]


def test_neo_asks_for_application_before_buying_when_family_is_unresolved(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {"evidence": [], "citations": [], "candidates": []}

    monkeypatch.setattr(
        "neo_assistant._call_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("An unresolved product choice should be clarified deterministically")
        ),
    )
    result = NeoAssistant(Knowledge()).answer(
        "The caller asked for pink batt. Which one should I tell them to buy?",
        "llama3.2:latest",
        [],
    )

    assert result["model_status"] == "catalogue_clarification"
    assert result["answer"].count("?") == 1
    assert "Which area is the customer insulating" in result["answer"]


def test_neo_limits_explicit_one_question_coaching_to_one_question(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {"evidence": [], "citations": [], "candidates": []}

    monkeypatch.setattr(
        "neo_assistant._call_model",
        lambda *args, **kwargs: (
            "That sounds uncomfortable. Is it cold all night? Does it vary by room? "
            "What insulation is installed?"
        ),
    )
    result = NeoAssistant(Knowledge()).answer(
        "The customer says their bedroom gets cold at night. Give me one useful opening question.",
        "llama3.2:latest",
        [],
    )

    assert result["model_status"] == "local_model"
    assert result["answer"].count("?") == 1
    assert "Does it vary" not in result["answer"]


def test_neo_supplies_a_question_when_coaching_reply_has_none(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {"evidence": [], "citations": [], "candidates": []}

    monkeypatch.setattr("neo_assistant._call_model", lambda *args, **kwargs: "Start by acknowledging the concern.")
    result = NeoAssistant(Knowledge()).answer(
        "The customer says their bedroom gets cold at night. Give me one useful opening question.",
        "llama3.2:latest",
        [],
    )

    assert result["answer"].count("?") == 1
    assert result["answer"].endswith("What is the most useful detail to clarify first?")


def test_neo_trims_a_second_interrogative_clause_inside_one_sentence(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {"evidence": [], "citations": [], "candidates": []}

    monkeypatch.setattr(
        "neo_assistant._call_model",
        lambda *args, **kwargs: (
            "Can you tell me more about the bedroom, like what kind of windows and doors it has, "
            "and what's the typical temperature range you're experiencing?"
        ),
    )
    result = NeoAssistant(Knowledge()).answer(
        "The customer says their bedroom gets cold at night. Give me one useful opening question.",
        "llama3.2:latest",
        [],
    )

    assert result["answer"].count("?") == 1
    assert "typical temperature" not in result["answer"]
    assert result["answer"].endswith("has?")


def test_neo_formats_dictionary_shaped_candidates_as_catalogue_matches(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {
                "evidence": [],
                "citations": [],
                "candidates": [
                    {"family_id": "FLETCHER_PINK_BATTS_CEILING",
                     "manufacturer": "Fletcher", "name": "Pink Batts Ceiling Insulation"},
                    {"family_id": "FLETCHER_PINK_BATTS_WALL",
                     "manufacturer": "Fletcher", "name": "Pink Batts Wall Insulation"},
                ],
            }

    def unexpected_model_call(*args, **kwargs):
        raise AssertionError("A catalogue clarification must not call the model")

    monkeypatch.setattr("neo_assistant._call_model", unexpected_model_call)
    result = NeoAssistant(Knowledge()).answer("pink batt", "llama3.2:latest", [])

    assert result["model_status"] == "catalogue_clarification"
    assert "Fletcher / Pink Batts Ceiling Insulation" in result["answer"]
    assert "Fletcher / Pink Batts Wall Insulation" in result["answer"]
    assert "Which area is the customer insulating" in result["answer"]


def test_neo_model_context_marks_exact_and_family_claims(monkeypatch):
    class Knowledge:
        def retrieve(self, query):
            return {
                "evidence": [
                    {
                        "kind": "verified_claim",
                        "status": "verified fact",
                        "text": json.dumps({
                            "metric_type": "thermal_r_value", "value": 2.0, "unit": "m²K/W",
                            "variant": "90 mm", "scope": "product",
                        }),
                        "source_id": "source",
                        "family_id": "BOARD_FAMILY",
                    },
                    {
                        "kind": "verified_claim",
                        "status": "verified fact",
                        "text": json.dumps({
                            "metric_type": "thermal_r_value", "value": 1.5, "unit": "m²K/W",
                            "variant": None, "scope": "family",
                        }),
                        "source_id": "source",
                        "family_id": "BOARD_FAMILY",
                    },
                ],
                "citations": [{"source_id": "source", "path": "data/tds/board.pdf"}],
                "candidates": [],
            }

    prompts = []

    def fake_model(model, messages):
        prompts.extend(messages)
        return "The source lists these family and product claims [S1]."

    monkeypatch.setattr("neo_assistant._call_model", fake_model)
    result = NeoAssistant(Knowledge()).answer("Board 90 mm", "local-model", [])

    evidence_block = prompts[1]["content"].split("Evidence JSON:\n", 1)[1]
    evidence = json.loads(evidence_block)["evidence"]
    assert evidence[0]["evidence_level"] == "exact_product_or_component"
    assert evidence[0]["variant"] == "90 mm"
    assert evidence[1]["evidence_level"] == "family_level"
    assert result["model_status"] == "local_model"


def test_neo_prompt_distinguishes_exact_product_from_family_evidence():
    from assistant_policy import SHARED_ASSISTANT_POLICY
    from neo_assistant import NEO_PROMPT

    assert NEO_PROMPT.startswith(SHARED_ASSISTANT_POLICY)
    assert "internal sales-support assistant" in NEO_PROMPT
    assert "Do not turn every" in NEO_PROMPT
    assert "local sources do not verify it" in NEO_PROMPT
    assert "family-level evidence" in NEO_PROMPT
    assert "free-flowing live-call copilot" in NEO_PROMPT
    assert "private configuration" in NEO_PROMPT


def test_neo_retrieval_attaches_page_locator_and_local_filename(monkeypatch):
    knowledge = NeoKnowledge()
    sources = [{
        "source_id": "pdf-source",
        "path": "data/tds/product.pdf",
        "status": "locally extracted TDS text",
    }]
    evidence = [{
        "source_id": "pdf-source",
        "kind": "unreviewed_tds_pdf",
        "locator": "PDF page 3",
    }]
    monkeypatch.setattr(
        knowledge.knowledge, "_product_evidence",
        lambda query, context: (sources, evidence, []),
    )

    result = knowledge.retrieve("rating")

    assert result["citations"][0]["filename"] == "product.pdf"
    assert result["citations"][0]["locator"] == "PDF page 3"
    assert result["citations"][0]["open_url"] == "/api/neo/sources/pdf-source/open"


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


def test_neo_api_does_not_persist_user_turn_when_answering_raises(monkeypatch, tmp_path):
    database = NeoStore(tmp_path / "neo-failed-turn.sqlite3")

    def fail_answer(*args, **kwargs):
        raise TypeError("candidate shape regression")

    monkeypatch.setattr(neo_api, "_store", database)
    monkeypatch.setattr(neo_api, "_assistant", type("MockNeo", (), {
        "answer": staticmethod(fail_answer),
    })())
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000),
        raise_server_exceptions=False,
    )
    csrf = client.get("/api/neo/session").json()["csrf"]
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}
    created = client.post("/api/neo/conversations", headers=headers, json={"model": ""})
    conversation_id = created.json()["conversation"]["conversation_id"]

    failed = client.post(
        f"/api/neo/conversations/{conversation_id}/messages",
        headers=headers, json={"message": "pink batt"},
    )

    assert failed.status_code == 500
    assert database.messages(conversation_id) == []


def test_neo_model_endpoint_prefers_a_resident_installed_local_model(monkeypatch, tmp_path):
    monkeypatch.setattr(neo_api, "_store", NeoStore(tmp_path / "neo-models.sqlite3"))
    monkeypatch.setattr(neo_api, "installed_models",
                        lambda: ["gemma4:latest", "llama3.2:latest"])
    monkeypatch.setattr(neo_api, "resident_models", lambda: [
        {"name": "llama3.2:latest", "size_bytes": 1, "size_vram_bytes": 0, "expires_at": "soon"},
    ])
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))
    assert client.get("/api/neo/session").status_code == 200

    result = client.get("/api/neo/models")

    assert result.status_code == 200
    assert result.json()["default_model"] == "llama3.2:latest"
    assert result.json()["resident"][0]["name"] == "llama3.2:latest"


def test_neo_ui_selects_resident_model_for_free_flow():
    html = (Path(__file__).resolve().parents[1] / "templates" / "neo.html").read_text(
        encoding="utf-8"
    )
    assert 'defaultModel=result.default_model||""' in html
    assert "using resident" in html
    assert "if(!conversation.model&&defaultModel)" in html


def test_matrix_page_is_loopback_only():
    app = FastAPI()
    app.include_router(matrix_api.router)
    local = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000))
    result = local.get("/matrix")
    assert result.status_code == 200
    assert all(f">{tab}</button>" in result.text for tab in ("Aurora", "Neo", "Oracle", "Admin"))
    assert '>Compare agents</button>' in result.text
    assert 'src="/chat" data-agent="aurora"' in result.text
    assert 'src="/neo" data-agent="neo"' in result.text
    assert 'src="/oracle" data-agent="oracle"' in result.text
    assert "Send to all three" in result.text
    assert "Do not enter customer personal information" in result.text
    assert "assistant-compare-prompt" in result.text
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
