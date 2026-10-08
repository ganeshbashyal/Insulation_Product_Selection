from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import local_operations
import operations_api
import oracle_api
from oracle_store import OracleStore


@pytest.fixture
def owner_client(tmp_path, monkeypatch):
    store = OracleStore(tmp_path / "oracle.sqlite3")
    store.set_passphrase("operations dashboard test passphrase")
    monkeypatch.setattr(oracle_api, "_store_instance", store)
    app = FastAPI()
    app.include_router(oracle_api.router)
    app.include_router(operations_api.router)
    client = TestClient(app, base_url="http://127.0.0.1:8002",
                        client=("127.0.0.1", 5000))
    login = client.post(
        "/api/oracle/login",
        headers={"Origin": "http://127.0.0.1:8002"},
        json={"passphrase": "operations dashboard test passphrase"},
    )
    assert login.status_code == 200
    csrf_headers = {
        "Origin": "http://127.0.0.1:8002",
        "X-Oracle-CSRF": login.json()["csrf"],
    }
    return client, csrf_headers


def test_operations_status_requires_local_owner_and_reports_live_local_state(owner_client, monkeypatch):
    client, _ = owner_client
    monkeypatch.setattr(operations_api, "_health", lambda *args, **kwargs: {"status": "ready"})
    monkeypatch.setattr(operations_api, "process_inventory", lambda **kwargs: [{
        "pid": 123, "name": "python.exe", "label": "Matrix / Neo / Oracle",
        "ports": [8002], "started_at": None,
        "owned_by_current_user": True, "stop_allowed": False,
    }])
    monkeypatch.setattr(operations_api, "installed_models", lambda: ["gemma4:latest"])
    monkeypatch.setattr(operations_api, "resident_models", lambda: [{
        "name": "gemma4:latest", "size_bytes": 100, "size_vram_bytes": 80, "expires_at": "soon",
    }])

    assert client.get("/api/operations/status").status_code == 200
    status = client.get("/api/operations/status").json()
    assert status["services"][1]["status"] == "ready"
    assert status["services"][1]["pid"] is not None
    assert status["models"]["installed"] == ["gemma4:latest"]
    assert status["models"]["resident"][0]["size_vram_bytes"] == 80
    assert status["processes"]["items"][0]["owned_by_current_user"] is True

    remote = TestClient(client.app, base_url="http://127.0.0.1:8002",
                        client=("192.0.2.5", 5000))
    assert remote.get("/api/operations/status").status_code == 404
    rebinding = TestClient(client.app, base_url="http://attacker.invalid:8002",
                           client=("127.0.0.1", 5000))
    assert rebinding.get("/api/operations/status").status_code == 404


def test_operations_status_surfaces_unavailable_local_sources(owner_client, monkeypatch):
    client, _ = owner_client
    monkeypatch.setattr(operations_api, "_health", lambda *args, **kwargs: {"status": "unavailable"})

    def unavailable(**kwargs):
        raise RuntimeError("Windows PowerShell is not available")

    monkeypatch.setattr(operations_api, "process_inventory", unavailable)
    monkeypatch.setattr(operations_api, "installed_models",
                        lambda: (_ for _ in ()).throw(RuntimeError("Local Ollama is unavailable")))
    monkeypatch.setattr(operations_api, "resident_models", lambda: [])

    result = client.get("/api/operations/status").json()
    assert result["processes"]["available"] is False
    assert "PowerShell" in result["processes"]["error"]
    assert result["models"]["available"] is False
    assert result["models"]["error"] == "Local Ollama is unavailable"


def test_operations_model_mutations_require_csrf_and_pass_bounded_duration(owner_client, monkeypatch):
    client, csrf = owner_client
    calls = []
    monkeypatch.setattr(operations_api, "load_model",
                        lambda model, minutes: calls.append((model, minutes)))
    monkeypatch.setattr(operations_api, "unload_model", lambda model: calls.append((model, "unload")))
    payload = {"model": "gemma4:latest", "minutes": 30}

    missing_csrf = client.post("/api/operations/models/load",
                               headers={"Origin": csrf["Origin"]}, json=payload)
    assert missing_csrf.status_code == 403
    loaded = client.post("/api/operations/models/load", headers=csrf, json=payload)
    assert loaded.status_code == 200
    assert loaded.json() == {"loaded": "gemma4:latest", "minutes": 30}
    assert client.post("/api/operations/models/load", headers=csrf,
                       json={"model": "gemma4:latest", "minutes": 2}).status_code == 422
    unloaded = client.post("/api/operations/models/unload", headers=csrf,
                           json={"model": "gemma4:latest"})
    assert unloaded.status_code == 200
    assert calls == [("gemma4:latest", 30), ("gemma4:latest", "unload")]


def test_process_inspection_and_stop_require_account_safe_typed_confirmation(owner_client, monkeypatch):
    client, csrf = owner_client
    monkeypatch.setattr(operations_api, "inspect_process", lambda *args, **kwargs: {
        "pid": 4321, "name": "python.exe", "started_at": "2026-10-06T09:53:47.4165940Z",
        "owned_by_current_user": True, "protected": False, "stop_allowed": True,
    })
    calls = []
    monkeypatch.setattr(operations_api, "stop_process",
                        lambda pid, name, started_at, **kwargs:
                        calls.append((pid, name, started_at)) or "stopped")

    inspected = client.get("/api/operations/processes/4321")
    assert inspected.status_code == 200
    assert inspected.json()["process"]["stop_allowed"] is True
    request = {
        "process_name": "python.exe",
        "started_at": "2026-10-06T09:53:47.4165940Z",
        "confirmation": "STOP 4321",
    }
    assert client.post("/api/operations/processes/4321/stop", json=request,
                       headers={"Origin": csrf["Origin"]}).status_code == 403
    incorrect = client.post("/api/operations/processes/4321/stop", json={
        **request, "confirmation": "yes",
    }, headers=csrf)
    assert incorrect.status_code == 400
    stopped = client.post("/api/operations/processes/4321/stop", json=request, headers=csrf)
    assert stopped.status_code == 200
    assert stopped.json()["stopped"] is True
    assert calls == [(4321, "python.exe", request["started_at"])]


def test_process_stop_maps_revalidation_and_protection_failures(owner_client, monkeypatch):
    client, csrf = owner_client
    monkeypatch.setattr(operations_api, "stop_process", lambda *args, **kwargs: "protected")
    protected = client.post("/api/operations/processes/8011/stop", json={
        "process_name": "python.exe",
        "started_at": "2026-10-06T09:53:47.4165940Z",
        "confirmation": "STOP 8011",
    }, headers=csrf)
    assert protected.status_code == 403
    assert "protected" in protected.json()["detail"].lower()

    monkeypatch.setattr(operations_api, "stop_process", lambda *args, **kwargs: "identity_changed")
    changed = client.post("/api/operations/processes/9000/stop", json={
        "process_name": "python.exe",
        "started_at": "2026-10-06T09:53:47.4165940Z",
        "confirmation": "STOP 9000",
    }, headers=csrf)
    assert changed.status_code == 409


def test_model_helpers_load_only_installed_and_unload_only_resident(monkeypatch):
    calls = []
    monkeypatch.setattr(local_operations, "installed_models", lambda: ["local-model"])
    monkeypatch.setattr(local_operations, "resident_models", lambda: [{"name": "local-model"}])
    monkeypatch.setattr(local_operations, "_ollama_request",
                        lambda path, **kwargs: calls.append((path, kwargs)))

    local_operations.load_model("local-model", 5)
    with pytest.raises(ValueError, match="installed"):
        local_operations.load_model("unknown", 5)
    with pytest.raises(ValueError, match="1, 5, or 30"):
        local_operations.load_model("local-model", 2)
    local_operations.unload_model("local-model")
    monkeypatch.setattr(local_operations, "resident_models", lambda: [])
    with pytest.raises(ValueError, match="currently resident"):
        local_operations.unload_model("local-model")

    assert calls == [
        ("/api/generate", {"payload": {
            "model": "local-model", "prompt": "", "stream": False,
            "keep_alive": "5m", "options": {"num_predict": 0},
        }, "timeout": 180.0}),
        ("/api/generate", {"payload": {
            "model": "local-model", "prompt": "", "stream": False,
            "keep_alive": 0, "options": {"num_predict": 0},
        }, "timeout": 180.0}),
    ]


def test_process_inventory_never_allows_stopping_its_own_process(monkeypatch):
    monkeypatch.setattr(local_operations, "_powershell", lambda *args, **kwargs: [{
        "pid": 123, "name": "python.exe", "label": "Matrix", "ports": [8002],
        "started_at": None, "owned_by_current_user": True, "stop_allowed": True,
    }])

    row = local_operations.process_inventory(current_pid=123, manager_port=8002)[0]

    assert row["owned_by_current_user"] is True
    assert row["stop_allowed"] is False


def test_process_stop_script_revalidates_owner_identity_and_protected_processes():
    script = local_operations._STOP_PROCESS_SCRIPT
    assert "GetOwnerSid" in script
    assert "$ownerSid -ne $currentSid" in script
    assert "$pidValue -eq $currentPid" in script
    assert "$startedAt -cne $expectedStartedAt" in script
    assert "(8011 -in $processPorts) -or ($managerPort -in $processPorts)" in script
    assert "Could not validate protected listener ports" in script
    assert "Stop-Process -Id $pidValue" in script


def test_stop_process_passes_pid_as_data_and_protects_manager_port(monkeypatch):
    calls = []
    monkeypatch.setattr(local_operations, "_powershell",
                        lambda script, *, env, timeout=12.0: calls.append((script, env)) or {
                            "result": "stopped",
                        })

    result = local_operations.stop_process(
        9001, "python.exe", "2026-10-06T09:53:47.4165940Z",
        current_pid=100, manager_port=8002,
    )

    script, env = calls[0]
    assert result == "stopped"
    assert env["LOCAL_OPS_PID"] == "9001"
    assert env["LOCAL_OPS_PROCESS_NAME"] == "python.exe"
    assert env["LOCAL_OPS_STARTED_AT"] == "2026-10-06T09:53:47.4165940Z"
    assert env["LOCAL_OPS_MANAGER_PORT"] == "8002"
    assert "9001" not in script
    assert "python.exe" not in script


def test_operations_status_requires_oracle_owner_authentication(tmp_path, monkeypatch):
    store = OracleStore(tmp_path / "oracle.sqlite3")
    store.set_passphrase("operations dashboard test passphrase")
    monkeypatch.setattr(oracle_api, "_store_instance", store)
    app = FastAPI()
    app.include_router(oracle_api.router)
    app.include_router(operations_api.router)
    client = TestClient(app, base_url="http://127.0.0.1:8002",
                        client=("127.0.0.1", 5000))

    assert client.get("/api/operations/status").status_code == 401


def test_matrix_operations_tab_is_wired_without_exposing_process_arguments():
    from pathlib import Path

    page = Path(__file__).resolve().parents[1] / "templates" / "matrix.html"
    html = page.read_text(encoding="utf-8")

    assert 'id="tab-operations"' in html
    assert 'id="opsModelMinutes"' in html
    assert 'id="opsPid"' in html
    assert "/api/operations/processes/${encodeURIComponent(process.pid)}/stop" in html
    assert "command-line arguments" in html
