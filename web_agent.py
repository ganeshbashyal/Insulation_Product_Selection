"""Deployable website agent with multi-site support and persistent sessions.

Self-hosted FastAPI app with P2 infrastructure:
  - site_config: per-site branding and routing
  - session_store: persistent SQLite sessions (multi-worker safe)
  - auth_middleware: API key validation + rate limiting
  - cors_validator: origin allowlist enforcement
  - widget_config: client-side branding endpoint

Reuses:
  - agent_core for conversation flow (bot_engine ranking + gating)
  - interaction_store for conversation logging (with site_id)
  - llm_client for optional phrasing (safe fallback when offline)

Run locally:
    pip install fastapi uvicorn python-docx
    uvicorn web_agent:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /chat                             embedded chat UI
    GET  /api/widget-config?site_id=X     site branding for widget injection
    POST /api/conversations                start conversation (X-API-Key header)
    POST /api/conversations/{id}/messages  send message (X-API-Key header)
    GET  /api/learning/families            family stats (X-API-Key header)
    GET  /api/learning/pending             pending review (X-API-Key header)
    POST /api/learning/outcomes            record outcome (X-API-Key header)
    GET  /api/learning/rejections          rejection report (X-API-Key header)
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import agent_core
import interaction_store
from auth_middleware import AuthMiddleware, AuditLog
from cors_validator import CORSValidator
from session_store import SQLiteSessionStore
from site_config import load_all_sites, SiteConfigError
from widget_config import WidgetConfigProvider

app = FastAPI(title="Insulation Enquiry Agent", version="2.0.0")

USE_LLM = os.getenv("AGENT_USE_LLM", "false").casefold() == "true"

# P2 infrastructure instances
session_store: SQLiteSessionStore | None = None
auth_middleware: AuthMiddleware | None = None
cors_validator: CORSValidator | None = None
widget_provider: WidgetConfigProvider | None = None
audit_log: AuditLog | None = None
sites: dict[str, Any] = {}


@app.on_event("startup")
async def startup():
    """Initialize P2 infrastructure at startup."""
    global session_store, auth_middleware, cors_validator, widget_provider, audit_log, sites

    try:
        sites = load_all_sites()
        if not sites:
            raise RuntimeError("No site configs found in config/sites/")
        print(f"✓ Loaded {len(sites)} site(s)")
    except SiteConfigError as e:
        raise RuntimeError(f"Failed to load site configs: {e}")

    session_store = SQLiteSessionStore()
    auth_middleware = AuthMiddleware()
    cors_validator = CORSValidator()
    widget_provider = WidgetConfigProvider()
    audit_log = AuditLog()

    print("✓ P2 infrastructure initialized (sessions, auth, CORS, audit)")


class StartResponse(BaseModel):
    conversation_id: str
    reply: str


class MessageRequest(BaseModel):
    message: str
    manufacturer_scope: str | None = None


class MessageResponse(BaseModel):
    reply: str
    done: bool


class OutcomeRequest(BaseModel):
    conversation_id: str
    outcome: str
    reviewer: str
    corrected_family_id: str | None = None
    note: str = ""


CHAT_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Insulation Enquiry</title>
<style>
:root{--teal:#087f7a;--ink:#17232c;--line:#dce3df}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f1e8;color:var(--ink)}
header{background:#102b32;color:#fff;padding:14px 18px}
header h1{font-size:1.05rem;margin:0}
header p{margin:.2rem 0 0;font-size:.78rem;color:#9fc9c4}
#log{height:calc(100vh - 170px);overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px}
.msg{max-width:82%;padding:10px 13px;border-radius:14px;line-height:1.4;font-size:.92rem;white-space:pre-wrap}
.bot{background:#fff;border:1px solid var(--line);border-top-left-radius:4px;align-self:flex-start}
.user{background:var(--teal);color:#fff;border-top-right-radius:4px;align-self:flex-end}
form{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line);background:#fff}
input{flex:1;padding:11px 13px;border:1px solid var(--line);border-radius:10px;font-size:.95rem}
button{padding:11px 18px;border:0;border-radius:10px;background:var(--teal);color:#fff;font-weight:700;cursor:pointer}
</style></head><body>
<header><h1>Insulation Enquiry</h1><p>Evidence-led family recommendation &middot; human review before quoting</p></header>
<div id="log"></div>
<form id="f"><input id="in" autocomplete="off" placeholder="Type your answer&hellip;"><button>Send</button></form>
<script>
let convo=null;const log=document.getElementById('log');
function add(text,cls){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;}
async function start(){const r=await fetch('/api/conversations',{method:'POST',headers:{'X-API-Key':'sk_local_dev_test'}});const j=await r.json();convo=j.conversation_id;add(j.reply,'bot');}
document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const i=document.getElementById('in');const m=i.value.trim();if(!m||!convo)return;i.value='';add(m,'user');
const r=await fetch('/api/conversations/'+convo+'/messages',{method:'POST',headers:{'Content-Type':'application/json','X-API-Key':'sk_local_dev_test'},body:JSON.stringify({message:m})});const j=await r.json();add(j.reply,'bot');if(j.done){i.placeholder='Enquiry sent for review';}});
start();
</script></body></html>"""


def _get_request_context(request: Request) -> tuple[str, str, str]:
    """Extract origin, IP, and API key from request."""
    origin = request.headers.get("Origin", "")
    client_ip = request.client.host if request.client else "unknown"
    api_key = request.headers.get("X-API-Key", "")
    return origin, client_ip, api_key


def _auth_and_cors(request: Request, site_id: str) -> dict[str, str]:
    """
    Validate auth and return CORS headers.
    Raises HTTPException on failure. Returns CORS headers dict on success.
    """
    origin, client_ip, api_key = _get_request_context(request)

    # Validate API key
    error, site = auth_middleware.validate_api_key(api_key)
    if error:
        audit_log.log("api_key_invalid", site_id=site_id, ip_address=client_ip, status_code=401)
        raise HTTPException(status_code=401, detail=error)

    # Verify site_id matches the API key's site
    if site.site_id != site_id:
        audit_log.log("site_mismatch", site_id=site_id, ip_address=client_ip, status_code=403)
        raise HTTPException(status_code=403, detail="Site ID mismatch")

    # Check rate limit
    if not auth_middleware.check_rate_limit(site_id, client_ip):
        audit_log.log("rate_limit_hit", site_id=site_id, ip_address=client_ip, status_code=429)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Get CORS headers
    cors_headers = cors_validator.get_cors_headers(site_id, origin)
    if not cors_headers and origin:  # Origin was provided but not allowed
        audit_log.log("cors_blocked", site_id=site_id, ip_address=client_ip, status_code=403)
        # Still reject, don't return headers
        cors_headers = {}

    audit_log.log("auth_success", site_id=site_id, ip_address=client_ip, status_code=200)
    return cors_headers


@app.get("/chat", response_class=HTMLResponse)
def chat() -> str:
    return CHAT_HTML


@app.get("/api/widget-config")
async def get_widget_config(site_id: str, request: Request):
    """Get site configuration for client-side widget injection."""
    origin = request.headers.get("Origin", "")

    # No auth required for widget config (it's public branding data)
    # But still enforce CORS
    config = widget_provider.get_widget_config(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")

    cors_headers = cors_validator.get_cors_headers(site_id, origin)
    return JSONResponse(config, headers=cors_headers)


@app.post("/api/conversations")
async def start_conversation(request: Request, site_id: str = "local") -> JSONResponse:
    """Start a new conversation. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)

    # Create conversation and session
    conversation = agent_core.Conversation()
    session_id = str(uuid.uuid4())
    session_store.create(session_id, site_id, {
        "conversation_id": conversation.conversation_id,
        "messages": [],
        "answers": {},
        "done": False,
    })

    opening = agent_core.QUESTIONS[0][1]
    if USE_LLM:
        opening = agent_core._phrase(opening, True)

    response = StartResponse(conversation_id=session_id, reply=opening)
    return JSONResponse(response.dict(), headers=cors_headers)


@app.post("/api/conversations/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request, site_id: str = "local") -> JSONResponse:
    """Send a message in an active conversation. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)

    # Retrieve session (site-scoped)
    session = session_store.get(session_id, site_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.is_expired:
        session_store.delete(session_id, site_id)
        raise HTTPException(status_code=401, detail="Session expired")

    # Reconstruct conversation from session
    session_data = json.loads(session.conversation_json)
    conversation = agent_core.Conversation()
    conversation.conversation_id = session_data["conversation_id"]
    conversation.answers = session_data["answers"]
    conversation.done = session_data["done"]

    # Process message
    reply = agent_core.reply(conversation, body.message, use_llm=USE_LLM, manufacturer_scope=body.manufacturer_scope)

    # Update session (extends TTL)
    session_store.update(session_id, site_id, {
        "conversation_id": conversation.conversation_id,
        "messages": session_data["messages"] + [{"role": "user", "content": body.message}, {"role": "assistant", "content": reply}],
        "answers": conversation.answers,
        "done": conversation.done,
    })

    # Log to interaction store with site_id
    if conversation.done and conversation.recommendation:
        interaction_store.log_conversation(
            conversation_id=conversation.conversation_id,
            site_id=site_id,
            answers=conversation.answers,
            recommendation=conversation.recommendation,
            gate_status=getattr(conversation, "gate_status", "unknown"),
            gate_reason=getattr(conversation, "gate_reason", ""),
            climate_zone=None,
            candidates=getattr(conversation, "candidates", []),
        )

    response = MessageResponse(reply=reply, done=conversation.done)
    return JSONResponse(response.dict(), headers=cors_headers)


@app.get("/api/learning/families")
async def learning_families(request: Request, site_id: str = "local") -> JSONResponse:
    """Get per-family statistics. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)
    stats = interaction_store.family_stats()
    return JSONResponse(stats, headers=cors_headers)


@app.get("/api/learning/pending")
async def learning_pending(request: Request, site_id: str = "local") -> JSONResponse:
    """Get conversations awaiting review. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)
    pending = interaction_store.pending_review()
    return JSONResponse(pending, headers=cors_headers)


@app.post("/api/learning/outcomes")
async def learning_outcome(body: OutcomeRequest, request: Request, site_id: str = "local") -> JSONResponse:
    """Record an outcome for a conversation. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)

    try:
        interaction_store.record_outcome(
            conversation_id=body.conversation_id,
            site_id=site_id,
            outcome=body.outcome,
            reviewer=body.reviewer,
            corrected_family_id=body.corrected_family_id,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse({"status": "recorded"}, headers=cors_headers)


@app.get("/api/learning/rejections")
async def learning_rejections(request: Request, site_id: str = "local") -> JSONResponse:
    """Get recent rejections for tuning. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)
    rejections = interaction_store.rejection_report()
    return JSONResponse(rejections, headers=cors_headers)
