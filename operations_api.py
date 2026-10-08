"""Owner-authenticated local service, model, and process operations."""
from __future__ import annotations

import json
import os
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import APIRouter, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel, Field

from local_operations import (
    inspect_process,
    load_model,
    process_inventory,
    resident_models,
    stop_process,
    unload_model,
)
from oracle_api import owner, response
from local_model import installed_models


router = APIRouter()


class ModelLoadRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    minutes: Literal[1, 5, 30] = 5


class ModelUnloadRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)


class ProcessStopRequest(BaseModel):
    process_name: str = Field(min_length=1, max_length=256)
    started_at: str = Field(min_length=1, max_length=80)
    confirmation: str = Field(min_length=1, max_length=40)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _health(port: int, *, manager_port: int, manager_pid: int) -> dict:
    if port == manager_port:
        return {"status": "ready", "pid": manager_pid}
    request = Request(
        f"http://127.0.0.1:{port}/health/ready",
        headers={"Accept": "application/json"},
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=1.5) as result:
            payload = json.loads(result.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "error": type(exc).__name__}
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        return {"status": "not_ready"}
    return {
        "status": "ready",
        "serving_only": payload.get("serving_only"),
        "release_id": payload.get("release_id"),
    }


def _manager_port(request: FastAPIRequest) -> int:
    server = request.scope.get("server")
    port = server[1] if isinstance(server, tuple) and len(server) > 1 else None
    return port if isinstance(port, int) and port not in {80, 443} and 1 <= port <= 65535 else 8002


@router.get("/api/operations/status")
def operations_status(request: FastAPIRequest):
    owner(request)
    manager_port = _manager_port(request)
    manager_pid = os.getpid()
    try:
        processes = process_inventory(current_pid=manager_pid, manager_port=manager_port)
        process_state = {"available": True, "error": None}
    except RuntimeError as exc:
        processes = []
        process_state = {"available": False, "error": str(exc)}

    try:
        models = installed_models()
        model_state = {"available": True, "error": None}
    except RuntimeError as exc:
        models = []
        model_state = {"available": False, "error": str(exc)}
    try:
        resident = resident_models()
        resident_state = {"available": True, "error": None}
    except RuntimeError as exc:
        resident = []
        resident_state = {"available": False, "error": str(exc)}

    pid_by_port = {
        port: process["pid"]
        for process in processes
        for port in process["ports"]
        if isinstance(port, int)
    }
    services = []
    service_specs = [
        ("aurora-development", "Aurora development", 8001),
        ("matrix-manager", "Matrix / Neo / Oracle", manager_port),
        ("aurora-alpha", "Aurora Alpha (serving-only)", 8011),
        ("ollama", "Local Ollama", 11434),
    ]
    for service_id, name, port in service_specs:
        details = _health(port, manager_port=manager_port, manager_pid=manager_pid) \
            if service_id != "ollama" else {
                "status": "ready" if model_state["available"] else "unavailable",
                "error": model_state["error"],
            }
        services.append({
            "id": service_id,
            "name": name,
            "port": port,
            "pid": manager_pid if service_id == "matrix-manager" else pid_by_port.get(port),
            **details,
        })

    return response({
        "services": services,
        "models": {
            "available": model_state["available"] and resident_state["available"],
            "installed": models,
            "resident": resident,
            "error": model_state["error"] or resident_state["error"],
        },
        "processes": {
            **process_state,
            "items": processes,
        },
    })


@router.post("/api/operations/models/load")
def operations_load_model(body: ModelLoadRequest, request: FastAPIRequest):
    owner(request, write=True)
    try:
        load_model(body.model, body.minutes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return response({"loaded": body.model, "minutes": body.minutes})


@router.post("/api/operations/models/unload")
def operations_unload_model(body: ModelUnloadRequest, request: FastAPIRequest):
    owner(request, write=True)
    try:
        unload_model(body.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return response({"unloaded": body.model})


@router.get("/api/operations/processes/{pid}")
def operations_inspect_process(pid: int, request: FastAPIRequest):
    owner(request)
    try:
        process = inspect_process(
            pid, current_pid=os.getpid(), manager_port=_manager_port(request)
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if process is None:
        raise HTTPException(404, "Process not found")
    return response({"process": process})


@router.post("/api/operations/processes/{pid}/stop")
def operations_stop_process(pid: int, body: ProcessStopRequest, request: FastAPIRequest):
    owner(request, write=True)
    if body.confirmation != f"STOP {pid}":
        raise HTTPException(400, f"Type STOP {pid} to confirm this process stop")
    try:
        result = stop_process(
            pid,
            body.process_name,
            body.started_at,
            current_pid=os.getpid(),
            manager_port=_manager_port(request),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    errors = {
        "not_found": (404, "Process no longer exists"),
        "identity_changed": (409, "Process identity changed; inspect it again"),
        "ownership_denied": (403, "Only processes owned by the current Windows account can be stopped"),
        "protected": (403, "This process is protected from dashboard termination"),
        "stop_failed": (500, "Windows could not stop this process"),
    }
    if result in errors:
        status, message = errors[result]
        raise HTTPException(status, message)
    if result != "stopped":
        raise HTTPException(500, "Windows returned an unknown process-stop result")
    return response({"stopped": True, "pid": pid, "name": body.process_name})
