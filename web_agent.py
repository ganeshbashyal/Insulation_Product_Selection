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

Environment:
    AURORA_ENV                      "development" (default) or "production".
                                    Production flips the hardening defaults below.
    AURORA_SITE_API_KEY_<SITE_ID>   Injected API key for a site, e.g.
                                    AURORA_SITE_API_KEY_LOCAL. Takes precedence
                                    over any api_key in config/sites/*.json, and
                                    is mandatory when AURORA_ENV=production.
    AURORA_REQUIRE_ORIGIN           Refuse requests with no Origin header.
                                    Defaults to true in production.
    AURORA_ENABLE_DEMO_CHAT         Serve the /chat development harness.
                                    Defaults to false in production.
    AURORA_DEMO_CHAT_SITE_ID        Site the /chat harness authenticates as
                                    (default "local").
    AURORA_RATE_LIMIT_BACKEND       "sqlite" (default, shared across workers on
                                    one host), "redis" (shared across hosts), or
                                    "memory" (single process, tests only).
    AURORA_SESSION_BACKEND          "sqlite" (default) or "redis".
    AURORA_REDIS_URL                Redis connection URL when a redis backend is
                                    selected (default redis://127.0.0.1:6379/0).
    AGENT_USE_LLM                   Force phrasing on/off; auto-detected if unset.

Scaling:
    One host, several workers  - the sqlite backends are sufficient; WAL mode
                                 coordinates the processes. No extra services.
    Several hosts              - set both backends to redis so quotas and
                                 sessions are shared rather than per-machine.

Endpoints:
    GET  /chat                             embedded chat UI (development only)
    GET  /api/widget-config?site_id=X     site branding for widget injection
    POST /api/conversations                start conversation (X-API-Key header)
    POST /api/conversations/{id}/messages  send message (X-API-Key header)
    GET  /api/learning/families            family stats (X-API-Key header)
    GET  /api/learning/pending             pending review (X-API-Key header)
    POST /api/learning/outcomes            record outcome (X-API-Key header)
    GET  /api/learning/rejections          rejection report (X-API-Key header)
    GET  /api/admin/leads                  captured leads (AURORA_LEAD_ADMIN_KEY header)
"""
from __future__ import annotations

import json
import hmac
import os
import threading
import uuid
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import agent_core
import interaction_store
import llm_client
from conversation_service import ConversationService
from auth_middleware import AuthMiddleware, AuditLog
from cors_validator import CORSValidator
from session_store import SQLiteSessionStore, SessionStore, build_session_store
from site_config import load_all_sites, SiteConfigError, is_production
from widget_config import WidgetConfigProvider

app = FastAPI(title="Insulation Enquiry Agent", version="2.0.0")
SERVING_ONLY = os.getenv("AURORA_SERVING_ONLY", "false").casefold() == "true"
if SERVING_ONLY:
    if not os.getenv("AURORA_RELEASE_DIR"):
        raise RuntimeError("Serving-only mode requires an explicitly activated knowledge release")
else:
    from research_api import router as research_router
    app.include_router(research_router)
    if (os.getenv("MATRIX_ENABLED", "true").strip().casefold() == "true"
            and os.getenv("AURORA_ENV", "development").strip().casefold() != "production"):
        from matrix_api import router as matrix_router
        from neo_api import router as neo_router
        app.include_router(matrix_router)
        app.include_router(neo_router)
    if (os.getenv("ORACLE_ENABLED", "true").strip().casefold() == "true"
            and os.getenv("AURORA_ENV", "development").strip().casefold() != "production"):
        from oracle_api import router as oracle_router
        app.include_router(oracle_router)
from storefront_api import build_router as build_storefront_router
app.include_router(build_storefront_router(sys.modules[__name__]))


@app.middleware("http")
async def research_response_privacy(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/research", "/admin/products", "/admin/knowledge",
                                    "/admin/competitors", "/admin/catalogue", "/api/oracle", "/oracle")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response

# Production hardening switches. Both default to the safe value whenever
# AURORA_ENV=production, so a production deployment is locked down even if the
# operator sets nothing, while local development keeps working untouched.
IS_PRODUCTION = is_production()

# Refuse public conversation requests that arrive without an Origin header.
# The embedded widget always sends one, so in production a missing Origin means
# the caller is not a browser. Off in development so curl and TestClient work.
REQUIRE_ORIGIN = (
    os.getenv("AURORA_REQUIRE_ORIGIN", "true" if IS_PRODUCTION else "false")
    .strip()
    .casefold()
    == "true"
)

# The bundled /chat page is a development harness: it is a first-party page
# that must hold a site API key in browser-readable JavaScript to talk to the
# API. That is acceptable for local testing and never acceptable in production,
# so the route is disabled there.
DEMO_CHAT_ENABLED = (
    os.getenv("AURORA_ENABLE_DEMO_CHAT", "false" if IS_PRODUCTION else "true")
    .strip()
    .casefold()
    == "true"
)

# Which site the development /chat harness authenticates as.
DEMO_CHAT_SITE_ID = os.getenv("AURORA_DEMO_CHAT_SITE_ID", "local")

# How long startup will wait for the phrasing model to load. Generous because a
# cold load on a CPU-only host is far slower than steady-state inference; it
# runs on a background thread, so a long wait costs nothing but a late log line.
WARM_TIMEOUT_SECONDS = float(os.getenv("AURORA_WARM_TIMEOUT_SECONDS", "300"))

# AGENT_USE_LLM lets an operator force phrasing on/off explicitly. Left unset,
# auto-detect: if a local Ollama server is actually reachable at startup, turn
# on natural phrasing (persona-driven, guardrailed) automatically - a robotic
# canned-question demo was never the intent, that was just the safe fallback
# for when no local model is running. generate_reply()/phrase() still fall
# back to the literal text on any later failure, so this is never a
# reliability risk, only a quality upgrade when the model is actually there.
_use_llm_env = os.getenv("AGENT_USE_LLM")
if SERVING_ONLY:
    USE_LLM = False
elif _use_llm_env is not None:
    USE_LLM = _use_llm_env.casefold() == "true"
else:
    USE_LLM = False if IS_PRODUCTION else llm_client.ollama_available()
    print(f"OK - AGENT_USE_LLM not set; auto-detected Ollama {'reachable' if USE_LLM else 'unreachable'} -> USE_LLM={USE_LLM}")


# P2 infrastructure instances
session_store: SessionStore | None = None
auth_middleware: AuthMiddleware | None = None
cors_validator: CORSValidator | None = None
widget_provider: WidgetConfigProvider | None = None
audit_log: AuditLog | None = None
sites: dict[str, Any] = {}

# P3 infrastructure instances
conversation_service: ConversationService | None = None


@app.on_event("startup")
async def startup():
    """Initialize P2 and P3 infrastructure at startup."""
    global session_store, auth_middleware, cors_validator, widget_provider, audit_log, sites
    global conversation_service

    try:
        sites = load_all_sites()
        if not sites:
            raise RuntimeError("No site configs found in config/sites/")
        print(f"OK - Loaded {len(sites)} site(s)")
    except SiteConfigError as e:
        raise RuntimeError(f"Failed to load site configs: {e}")

    session_store = build_session_store()
    auth_middleware = AuthMiddleware()
    cors_validator = CORSValidator()
    widget_provider = WidgetConfigProvider()
    audit_log = AuditLog()

    print(
        f"OK - P2 infrastructure initialized "
        f"(sessions={type(session_store).__name__}, "
        f"rate_limit={type(auth_middleware.rate_limiter).__name__}, CORS, audit)"
    )

    # P3 initialization
    conversation_service = ConversationService(use_llm=USE_LLM)

    print("OK - P3 infrastructure initialized (router, RAG, lint)")

    if USE_LLM:
        # Ollama unloads an idle model from memory; the first real user message
        # after that pays the full cold-load penalty. phrase() treats a missed
        # deadline as "use the literal text", so an unwarmed model reads as a
        # robotic bot rather than a slow one. Pay that cost here at startup, on
        # a background thread so a slow or absent Ollama never blocks the
        # server from accepting requests.
        import time as _time

        def _warm_ollama() -> None:
            start = _time.monotonic()
            ok = llm_client.warm_model(timeout=WARM_TIMEOUT_SECONDS)
            elapsed = _time.monotonic() - start
            if ok:
                print(f"OK - chat model {llm_client.OLLAMA_MODEL} warm in {elapsed:.1f}s")
            else:
                print(
                    f"WARNING - could not warm {llm_client.OLLAMA_MODEL} in {elapsed:.1f}s; "
                    f"replies will fall back to literal text"
                )

        threading.Thread(target=_warm_ollama, daemon=True).start()


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    if session_store is None or conversation_service is None or not sites:
        raise HTTPException(503, "Service not initialized")
    return {"status": "ready", "serving_only": SERVING_ONLY,
            "release_id": conversation_service.product_answers.release["release_id"]
            if conversation_service.product_answers.release else None}


class StartResponse(BaseModel):
    conversation_id: str
    reply: str


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    manufacturer_scope: str | None = None


class MessageResponse(BaseModel):
    reply: str
    done: bool
    category: str
    retrieval_mode: str
    human_review_required: bool


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
<header><h1 id="title">Insulation Enquiry</h1><p id="subtitle">Project discovery and product facts &middot; human-reviewed selection</p><p id="family"></p><p>Local test chat only. Do not enter customer personal information. Nothing here approves or publishes product claims.</p></header>
<div id="log"></div>
<form id="f"><input id="in" autocomplete="off" placeholder="Type your answer&hellip;"><button>Send</button></form>
<script>
let convo=null;const log=document.getElementById('log');
const API_KEY=__AURORA_DEMO_KEY__;const SITE_ID=__AURORA_DEMO_SITE__;
const FAMILY_ID=__AURORA_DEMO_FAMILY_ID__;const FAMILY_NAME=__AURORA_DEMO_FAMILY_NAME__;
function add(text,cls){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;}
// Surface failures instead of rendering `undefined` into an empty bubble. A 403
// from the origin allowlist used to look identical to a silent hang, which made
// a one-line config problem very hard to tell apart from a broken server.
async function post(url,body){
  let r;
  try{r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-API-Key':API_KEY},body:body?JSON.stringify(body):undefined});}
  catch(e){throw new Error('Cannot reach the API: '+e.message);}
  let j=null;try{j=await r.json();}catch(e){}
  if(!r.ok)throw new Error('HTTP '+r.status+' - '+((j&&j.detail)||r.statusText));
  return j;
}
async function start(){
  try{
    const params=new URLSearchParams({site_id:SITE_ID});
    if(FAMILY_ID)params.set('family_id',FAMILY_ID);
    const j=await post('/api/conversations?'+params.toString());convo=j.conversation_id;add(j.reply,'bot');
    if(FAMILY_ID){
      document.getElementById('title').textContent='Family review chat';
      document.getElementById('subtitle').textContent='Ask about the selected family; the bot can explain available local information and identify gaps.';
      document.getElementById('family').textContent='Family: '+FAMILY_NAME+' ('+FAMILY_ID+'). Your messages are not approvals.';
      document.getElementById('in').placeholder='Ask about '+FAMILY_NAME+'…';
    }
  }
  catch(e){add(e.message,'bot');}
}
document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const i=document.getElementById('in');const m=i.value.trim();if(!m||!convo)return;i.value='';add(m,'user');
  try{const j=await post('/api/conversations/'+convo+'/messages?site_id='+encodeURIComponent(SITE_ID),{message:m});add(j.reply,'bot');if(j.done){i.placeholder='Enquiry sent for review';}}
  catch(e){add(e.message,'bot');}
});
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

    # Origin enforcement. A browser-originated request must come from an origin
    # on the site's allowlist; anything else is refused outright rather than
    # merely served without CORS headers. Withholding the headers only stops a
    # compliant browser reading the body - it does not stop the request, so the
    # work is still done and the data still leaves the process.
    if origin and not cors_validator.is_origin_allowed(site_id, origin):
        audit_log.log("cors_blocked", site_id=site_id, ip_address=client_ip, status_code=403)
        raise HTTPException(status_code=403, detail="Origin not allowed")

    # A request with no Origin header is not a browser request. In production
    # that is refused for public conversation endpoints, because the widget
    # always sends one; in development it is allowed so curl and the test
    # client keep working.
    if not origin and REQUIRE_ORIGIN:
        audit_log.log("origin_missing", site_id=site_id, ip_address=client_ip, status_code=403)
        raise HTTPException(status_code=403, detail="Origin header required")

    # Check rate limit
    if not auth_middleware.check_rate_limit(site_id, client_ip):
        audit_log.log("rate_limit_hit", site_id=site_id, ip_address=client_ip, status_code=429)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    cors_headers = cors_validator.get_cors_headers(site_id, origin) if origin else {}

    audit_log.log("auth_success", site_id=site_id, ip_address=client_ip, status_code=200)
    return cors_headers


@app.get("/chat", response_class=HTMLResponse)
def chat(family_id: str | None = Query(default=None, max_length=100)) -> str:
    """
    Development chat harness.

    Disabled whenever AURORA_ENV=production (or AURORA_ENABLE_DEMO_CHAT=false),
    because this page necessarily exposes a site API key to the browser. The key
    is injected from the resolved site config at render time rather than being
    hardcoded, so no credential literal ships in the source.
    """
    if not DEMO_CHAT_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    site = (sites or {}).get(DEMO_CHAT_SITE_ID)
    if site is None or not site.api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Demo chat site '{DEMO_CHAT_SITE_ID}' is not configured with an "
                "API key. Set AURORA_DEMO_CHAT_SITE_ID or supply the site's key."
            ),
        )

    family = None
    if family_id:
        family = next((row for row in agent_core.FAMILIES if row["family_id"] == family_id), None)
        if family is None:
            raise HTTPException(status_code=404, detail="Unknown family")
        from knowledge_release import configured_release, visible_family_ids
        release = configured_release()
        if release and family_id not in visible_family_ids(release, DEMO_CHAT_SITE_ID):
            raise HTTPException(status_code=404, detail="Unknown family")

    return (
        CHAT_HTML.replace("__AURORA_DEMO_KEY__", json.dumps(site.api_key))
        .replace("__AURORA_DEMO_SITE__", json.dumps(site.site_id))
        .replace("__AURORA_DEMO_FAMILY_ID__", json.dumps(family["family_id"] if family else ""))
        .replace("__AURORA_DEMO_FAMILY_NAME__", json.dumps(family["name"] if family else ""))
    )


@app.get("/api/widget-config")
async def get_widget_config(site_id: str, request: Request):
    """Get site configuration for client-side widget injection."""
    origin = request.headers.get("Origin", "")

    # No auth required for widget config (it's public branding data), but an
    # explicit cross-origin caller must still be on the site's allowlist.
    config = widget_provider.get_widget_config(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")

    if origin and not cors_validator.is_origin_allowed(site_id, origin):
        raise HTTPException(status_code=403, detail="Origin not allowed")

    cors_headers = cors_validator.get_cors_headers(site_id, origin) if origin else {}
    return JSONResponse(config, headers=cors_headers)


@app.post("/api/conversations")
async def start_conversation(
    request: Request,
    site_id: str = "local",
    family_id: str | None = Query(default=None, max_length=100),
) -> JSONResponse:
    """Start a new conversation. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)

    # Create conversation and session
    conversation = agent_core.Conversation()
    if family_id:
        family = next((row for row in agent_core.FAMILIES if row["family_id"] == family_id), None)
        if family is None:
            raise HTTPException(status_code=404, detail="Unknown family")
        from knowledge_release import configured_release, visible_family_ids
        release = configured_release()
        if release and family_id not in visible_family_ids(release, site_id):
            raise HTTPException(status_code=404, detail="Unknown family")
        conversation.topic_products = [family_id]
        conversation.family_review_id = family_id
    session_id = str(uuid.uuid4())
    session_store.create(
        session_id,
        site_id,
        {**conversation.to_dict(), "messages": []},
    )

    opening = agent_core.OPENING
    if USE_LLM:
        opening = agent_core._phrase(opening, True, is_opening=True)

    response = StartResponse(conversation_id=session_id, reply=opening)
    return JSONResponse(response.model_dump(), headers=cors_headers)


@app.post("/api/conversations/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request, site_id: str = "local") -> JSONResponse:
    """Send a message with parallel processing (fast response)."""
    cors_headers = _auth_and_cors(request, site_id)

    session = session_store.get(session_id, site_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_expired:
        session_store.delete(session_id, site_id)
        raise HTTPException(status_code=401, detail="Session expired")

    session_data = json.loads(session.conversation_json)
    conversation = agent_core.Conversation.from_dict(session_data)
    result = conversation_service.handle(
        conversation,
        body.message,
        manufacturer_scope=body.manufacturer_scope,
        site_id=site_id,
    )

    # Update session
    session_store.update(
        session_id,
        site_id,
        {
            **conversation.to_dict(),
            "messages": session_data["messages"]
            + [
                {"role": "user", "content": body.message},
                {"role": "assistant", "content": result.reply},
            ],
        },
    )

    response = MessageResponse(
        reply=result.reply,
        done=result.done,
        category=result.category,
        retrieval_mode=result.retrieval_mode,
        human_review_required=result.human_review_required,
    )
    return JSONResponse(response.model_dump(), headers=cors_headers)


@app.get("/api/learning/families")
async def learning_families(request: Request, site_id: str = "local") -> JSONResponse:
    """Get per-family statistics. Requires X-API-Key header."""
    cors_headers = _auth_and_cors(request, site_id)
    stats = interaction_store.family_stats()
    return JSONResponse(stats, headers=cors_headers)


@app.get("/api/learning/pending")
async def learning_pending(request: Request, site_id: str = "local") -> JSONResponse:
    """Get conversations awaiting review. Requires X-API-Key header."""
    _require_lead_admin(request)
    pending = [row for row in interaction_store.pending_review() if row["site_id"] == site_id]
    return JSONResponse(pending, headers={"Cache-Control": "no-store"})


def _require_lead_admin(request: Request) -> None:
    expected_key = os.getenv("AURORA_LEAD_ADMIN_KEY", "")
    if not expected_key:
        raise HTTPException(status_code=503, detail="Operator access is disabled until AURORA_LEAD_ADMIN_KEY is configured")
    supplied_key = request.headers.get("X-Aurora-Lead-Admin-Key", "")
    if not hmac.compare_digest(supplied_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid lead admin key")


@app.get("/api/admin/leads")
async def admin_leads(request: Request, site_id: str | None = None) -> JSONResponse:
    """Read captured leads using a separate, server-side admin key."""
    _require_lead_admin(request)
    return JSONResponse(interaction_store.leads(site_id=site_id), headers={"Cache-Control": "no-store"})


@app.get("/api/admin/briefs")
async def admin_briefs(request: Request, site_id: str = "local") -> JSONResponse:
    _require_lead_admin(request)
    return JSONResponse(interaction_store.sales_briefs(site_id), headers={"Cache-Control": "no-store"})


@app.get("/api/admin/briefs/{conversation_id}")
async def admin_brief(conversation_id: str, request: Request, site_id: str = "local") -> JSONResponse:
    _require_lead_admin(request)
    record = next((row for row in interaction_store.sales_briefs(site_id) if row["conversation_id"] == conversation_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Brief not found for this site")
    return JSONResponse(record, headers={"Cache-Control": "no-store"})


@app.get("/admin/briefs")
async def operator_preview() -> HTMLResponse:
    # This page contains no records or secret; all reads require the admin header.
    page = Path(__file__).resolve().parent / "templates" / "sales_briefs.html"
    return HTMLResponse(page.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/api/learning/outcomes")
async def learning_outcome(body: OutcomeRequest, request: Request, site_id: str = "local") -> JSONResponse:
    """Record an outcome for a conversation. Requires X-API-Key header."""
    _require_lead_admin(request)

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

    return JSONResponse({"status": "recorded"}, headers={"Cache-Control": "no-store"})


@app.get("/api/learning/rejections")
async def learning_rejections(request: Request, site_id: str = "local") -> JSONResponse:
    """Get recent rejections for tuning. Requires X-API-Key header."""
    _require_lead_admin(request)
    rejections = [row for row in interaction_store.rejection_report() if row["site_id"] == site_id]
    return JSONResponse(rejections, headers={"Cache-Control": "no-store"})
