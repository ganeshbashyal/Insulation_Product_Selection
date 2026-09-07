# P2.6 Integration Architecture Review

## Current State (web_agent.py)

```python
_SESSIONS: dict[str, agent_core.Conversation] = {}  # ❌ in-process, lost on restart, single-worker

@app.post("/api/conversations")
async def start_conversation(req: StartRequest) -> StartResponse:
    # ❌ No site_id concept
    # ❌ No auth
    # ❌ No CORS
    conversation = agent_core.Conversation(...)
    _SESSIONS[conv_id] = conversation
    return StartResponse(...)

@app.post("/api/conversations/{id}/messages")
async def send_message(id: str, req: MessageRequest) -> MessageResponse:
    # ❌ No auth, no CORS, no site scoping
    conversation = _SESSIONS[id]
    ...

@app.post("/api/learning/outcomes")
async def record_outcome(body: OutcomeRequest):
    # ❌ Completely open, no auth
    interaction_store.record_outcome(...)
```

---

## Target State (P2.6)

### Module Wiring

```python
# Import all P2 modules at startup
from session_store import SQLiteSessionStore
from auth_middleware import AuthMiddleware, InMemoryRateLimiter, AuditLog
from cors_validator import CORSValidator
from widget_config import WidgetConfigProvider
from site_config import load_all_sites

# Instantiate infrastructure
session_store = SQLiteSessionStore()
auth_middleware = AuthMiddleware()
cors_validator = CORSValidator()
widget_provider = WidgetConfigProvider()
sites = load_all_sites()

# Startup: verify all sites loaded
@app.on_event("startup")
async def startup():
    if not sites:
        raise RuntimeError("No site configs found")
    print(f"✓ Loaded {len(sites)} site(s)")
```

### Endpoint Changes

#### 1. Start Conversation (`POST /api/conversations`)

```python
@app.post("/api/conversations")
async def start_conversation(req: StartRequest, site_id: str) -> StartResponse:
    # Auth check
    api_key = req.headers.get("X-API-Key")
    error, site = auth_middleware.validate_api_key(api_key)
    if error:
        audit_log.log("api_key_invalid", site_id=site_id, ip=client_ip, status_code=401)
        raise HTTPException(401, "Invalid API key")
    
    # CORS header injection
    cors_headers = cors_validator.get_cors_headers(site_id, origin)
    
    # Rate limit check
    if not auth_middleware.check_rate_limit(site_id, client_ip):
        audit_log.log("rate_limit_hit", site_id=site_id, ip=client_ip, status_code=429)
        raise HTTPException(429, "Rate limit exceeded")
    
    # Create conversation
    conversation = agent_core.Conversation(...)
    session_id = str(uuid.uuid4())
    session_store.create(session_id, site_id, conversation.to_dict())
    
    # Log audit event
    audit_log.log("conversation_start", site_id=site_id, ip=client_ip, status_code=200)
    
    # Respond with CORS headers
    return JSONResponse(
        {"conversation_id": session_id, "reply": ...},
        headers=cors_headers
    )
```

#### 2. Send Message (`POST /api/conversations/{id}/messages`)

```python
@app.post("/api/conversations/{id}/messages")
async def send_message(id: str, req: MessageRequest, site_id: str):
    # Auth check (same as above)
    error, site = auth_middleware.validate_api_key(api_key)
    if error:
        raise HTTPException(401, "Invalid API key")
    
    # Retrieve session (site-scoped)
    session = session_store.get(id, site_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    if session.is_expired:
        session_store.delete(id, site_id)
        raise HTTPException(401, "Session expired")
    
    # Process message
    conversation = agent_core.Conversation.from_dict(json.loads(session.conversation_json))
    reply = conversation.continue_with(req.message)
    
    # Update session (extends TTL)
    session_store.update(id, site_id, conversation.to_dict())
    
    # Log to interaction_store with site_id
    interaction_store.log_conversation(
        conversation_id=id,
        site_id=site_id,  # NEW: track which site this came from
        ...
    )
    
    # Respond with CORS headers
    return JSONResponse(
        {"reply": reply, "done": conversation.is_complete()},
        headers=cors_headers
    )
```

#### 3. Record Outcome (`POST /api/learning/outcomes`)

```python
@app.post("/api/learning/outcomes")
async def record_outcome(body: OutcomeRequest, site_id: str):
    # Auth check (must have API key)
    error, site = auth_middleware.validate_api_key(api_key)
    if error:
        raise HTTPException(401, "Invalid API key")
    
    # Use site_id from auth, not from request
    interaction_store.record_outcome(
        conversation_id=body.conversation_id,
        site_id=site_id,  # Enforced from auth, not user-supplied
        outcome=body.outcome,
        reviewer=body.reviewer,
        ...
    )
    
    # Respond with CORS headers
    return JSONResponse({"status": "ok"}, headers=cors_headers)
```

#### 4. New: Widget Config (`GET /api/widget-config`)

```python
@app.get("/api/widget-config")
async def get_widget_config(site_id: str):
    # No auth needed; this is public branding data
    config = widget_provider.get_widget_config(site_id)
    if not config:
        raise HTTPException(404, f"Site not found: {site_id}")
    
    cors_headers = cors_validator.get_cors_headers(site_id, origin)
    return JSONResponse(config, headers=cors_headers)
```

---

## Key Changes to interaction_store

```python
# Add site_id to conversations table
def log_conversation(
    conversation_id: str,
    site_id: str,  # NEW
    answers: dict,
    recommendation: dict | None,
    ...
) -> None:
    connection.execute(
        "INSERT INTO conversations (..., site_id, ...) VALUES (?, ?, ...)",
        (..., site_id, ...),
    )

# Outcome recording also includes site_id
def record_outcome(
    conversation_id: str,
    site_id: str,  # NEW
    outcome: str,
    reviewer: str,
    ...
) -> None:
    ...
```

---

## Benefits of This Architecture

| Aspect | Before | After |
|--------|--------|-------|
| **Sessions** | Lost on restart, single process | Persistent SQLite, multi-worker |
| **Auth** | None—wide open | Per-site API key, 401/403 on failure |
| **Rate limiting** | None | Per-minute per IP+site |
| **CORS** | None—accepts all origins | Per-site allowlist from config |
| **Tenancy** | Not supported | Fully scoped by site_id |
| **Audit trail** | None for auth events | Logged to audit.sqlite3 |
| **Branding** | Hardcoded in UI | Dynamic config endpoint |
| **Multi-site** | ❌ Not possible | ✅ Same code, different configs |

---

## Risk Mitigation

1. **Auth key exposure:** API keys stored as plaintext in config JSONs (dev-only). In production, use env vars or secure vault. Tests use hardcoded keys.
2. **Session hijacking:** Sessions scoped to site_id + session_id; can't cross sites.
3. **CORS bypass:** Origin header validated on every request; empty dict returned if not allowed (automatic 403).
4. **Rate limit evasion:** Per-IP tracking with sliding window; can't spam with different IPs (admin must set higher limits if needed).
5. **Backwards compatibility:** Old clients (no X-API-Key header) will get 401. Documented in migration guide.

---

## Testing Strategy for P2.6

- Unit tests: each endpoint with/without auth, with/without CORS origin, rate limit exceeded
- Integration tests: full flow (start → message → outcome) with site scoping
- Multi-site tests: same session_id on different sites are isolated
- Audit log tests: all auth events (success, failure, rate limit) are logged

**New tests:** ~40 covering endpoints, site scoping, CORS, auth, rate limiting.

---

## Approval Checkpoints Before Proceeding

1. ✅ Session migration (`_SESSIONS` → SQLiteSessionStore): Clear?
2. ✅ Auth enforcement on learning endpoints: OK to reject unauthenticated requests?
3. ✅ site_id scoping everywhere: Acceptable security model?
4. ✅ Audit logging in auth_middleware: Sufficient for compliance?
5. ✅ Interaction_store changes (add site_id column): Acceptable schema change?

**Any concerns, or ready to proceed?**
