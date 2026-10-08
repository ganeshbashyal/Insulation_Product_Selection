"""Local-only Matrix managerial interface."""
from __future__ import annotations

import ipaddress
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from assistant_contract import AssistantContract
import matrix_handoff_store

ROOT = Path(__file__).resolve().parent
router = APIRouter()
MATRIX_CONTRACT = AssistantContract(
    persona_id="matrix",
    audience="Workspace owner/operator",
    purpose="Manage local assistants and supporting services through explicit operational controls.",
    tone=("operational", "clear", "explicit", "auditable"),
    allowed_sources=("service health", "process status", "configuration status", "operational audit events"),
    restricted_sources=("raw assistant conversations", "customer records", "Oracle-private notes"),
    allowed_tools=("local service and model controls", "approved module navigation", "operational event logging"),
    prohibited_actions=(
        "act as a customer assistant",
        "make product claims or recommendations",
        "modify production data automatically",
        "send external messages without explicit approval",
        "share assistant histories",
    ),
    memory_boundary="Operational events only; no conversational memory.",
    output_format=("status and diagnostics", "auditable operation results"),
    escalation_rules=("unsafe or unauthorized operation", "service/process identity mismatch", "failed control action"),
)
PERSONA_ID = MATRIX_CONTRACT.persona_id


@router.get("/matrix", response_class=HTMLResponse)
def matrix_page(request: Request):
    address = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(address).is_loopback
    except ValueError:
        local = False
    hostname = request.url.hostname or ""
    try:
        local_host = hostname.casefold() == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        local_host = False
    if not local or not local_host:
        raise HTTPException(404, "Not found")
    return HTMLResponse((ROOT / "templates" / "matrix.html").read_text(encoding="utf-8"),
                        headers={
                            "X-Assistant-Persona": PERSONA_ID,
                            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
                            "Content-Security-Policy":
                                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                                "frame-src 'self'; img-src 'self' data:",
                        })


@router.get("/api/matrix/handoffs")
def handoff_metadata(request: Request):
    address = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(address).is_loopback
    except ValueError:
        local = False
    hostname = request.url.hostname or ""
    try:
        local_host = hostname.casefold() == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        local_host = False
    if not local or not local_host:
        raise HTTPException(404, "Not found")
    return JSONResponse({
        "handoffs": matrix_handoff_store.store().metadata(),
        "payloads_included": False,
        "source_identifiers_included": False,
    }, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff"})
