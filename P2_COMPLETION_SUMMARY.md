# P2 Multi-Site Infrastructure — COMPLETE

**Completion time:** 2026-09-07 (while you slept)  
**Final test status:** 128 passing (72 new P2 tests + 56 existing)  
**Branch status:** All committed, ready to merge  

---

## What Was Built

### P2.1: Site Configuration Loader ✅
- `site_config.py` — Load per-site JSON configs from `config/sites/`
- SiteConfig dataclass with full validation (colours, contact routing, allowed_origins, API key, rate limits)
- `config/sites/acme.json` — Production example (callback contact)
- `config/sites/local.json` — Local dev example (phone contact)
- 10 tests: required fields, validation, contact method specificity

**Commit:** `1a26c99`

### P2.2: Persistent Sessions (SQLite) ✅
- `session_store.py` — SessionStore interface + SQLiteSessionStore implementation
- Sessions scoped by (session_id, site_id) — no cross-site access
- TTL-based eviction (24h from last access, extendable on update)
- Multi-worker safe (SQLite connection pooling with 5s timeout)
- Background cleanup utility (cleanup_expired())
- 10 tests: CRUD, TTL extension, multi-site isolation, expiry handling

**Commit:** `6c94d05`

### P2.3: Auth Middleware ✅
- `auth_middleware.py` — API key validation + rate limiting + audit logging
- AuthMiddleware: validate_api_key() → resolves to SiteConfig
- InMemoryRateLimiter: sliding-window per-minute limiter, keyed by (site_id, ip)
- AuditLog: SQLite-backed audit trail for compliance (auth events, rate limit hits)
- 10 tests: key validation, rate limiting per site, audit log persistence

**Commit:** `c471313`

### P2.4: CORS Validation ✅
- `cors_validator.py` — Per-site origin allowlist enforcement
- is_origin_allowed(site_id, origin) — checks allowlist from site config
- get_cors_headers() — returns CORS headers for allowed origins, empty dict for unauthorized
- Automatic origin rejection (no headers = browser blocks the response)
- 10 tests: origin validation, multiple allowed origins, CORS header structure

**Commit:** `f21fb70`

### P2.5: Widget Config Provider ✅
- `widget_config.py` — Branding endpoint for client-side widget injection
- get_widget_config(site_id) → JSON-safe dict with display_name, colours, logo, greeting, contact info
- Excludes sensitive fields (api_key, rate_limit, allowed_origins)
- Public endpoint (no auth, but CORS-aware)
- 9 tests: config retrieval, field validation, JSON serializability, branding completeness

**Commit:** `004cf1d`

### P2.6: Web_Agent Integration ✅
- **Schema upgrade:** interaction_store.py — Added site_id to conversations/outcomes tables
  - Composite key (conversation_id, site_id) for site isolation
  - All queries updated to join on both keys
  - Backwards compatible with site_id="default" for old code
  - 1 commit: `ba331c2`

- **Endpoint rewrite:** web_agent.py — Full integration of P2 components
  - Startup event initializes all infrastructure (sites, session_store, auth, CORS, audit)
  - All endpoints (conversations, messages, learning/*) now require X-API-Key header
  - All endpoints enforce site_id scoping (can't cross sites, enforced at store level)
  - All endpoints return CORS headers (origin-aware per site config)
  - Rate limiting per (site_id, ip_address) from site config
  - Audit logging for all auth events
  - New `/api/widget-config?site_id=X` endpoint (public, branding data)
  - Conversation sessions now persist (SQLite), survive restarts, multi-worker safe
  - 23 endpoint tests covering auth, CORS, site scoping, conversation flow
  - 1 commit: `78033c1`

---

## Test Coverage Summary

**Total: 128 passing tests**

| Component | Tests | Status |
|-----------|-------|--------|
| Site config | 10 | ✅ Complete |
| SessionStore | 10 | ✅ Complete |
| Auth middleware | 10 | ✅ Complete |
| CORS validator | 10 | ✅ Complete |
| Widget config | 9 | ✅ Complete |
| Web_agent endpoints | 23 | ✅ Complete |
| Existing (P0-P1) | 56 | ✅ Passing |

---

## Deployment Checklist

- [x] Multi-site config loader (prod/dev examples included)
- [x] Persistent sessions with TTL (24h expiry)
- [x] API key authentication (X-API-Key header required)
- [x] Per-site rate limiting (requests_per_minute from config)
- [x] CORS enforcement (origin allowlist per site)
- [x] Audit logging (all auth events to SQLite)
- [x] Widget config endpoint (public branding delivery)
- [x] Session persistence (SQLite backend, multi-worker safe)
- [x] Site scoping (sessions, outcomes, audit all scoped by site_id)
- [x] All 128 tests passing

---

## API Usage Notes

### Client Integration (Example)

```javascript
// Start conversation (site-scoped, requires API key)
const response = await fetch('https://your-host/api/conversations?site_id=acme', {
  method: 'POST',
  headers: {
    'X-API-Key': 'sk_acme_prod_xxxxx',
    'Content-Type': 'application/json'
  }
});

// Widget branding (public, CORS-aware)
const config = await fetch('https://your-host/api/widget-config?site_id=acme');
// Use colours, greeting, contact info for UI theming
```

### Session Persistence

- Sessions stored in `data/local/sessions.sqlite3` (created automatically)
- TTL: 24 hours from last access
- Accessing a session extends its expiry
- Sessions expire and are cleaned up automatically (via cleanup_expired())
- Multi-worker safe: sessions are per-site and survive process restarts

### Auth & Rate Limiting

- All `/api/learning/*` endpoints require `X-API-Key` header
- Rate limits per site (from config: requests_per_minute, per_ip)
- Missing/invalid key → 401 Unauthorized
- Rate limit exceeded → 429 Too Many Requests
- All auth events logged to `data/local/audit.sqlite3` for compliance

### CORS Enforcement

- Every endpoint checks `Origin` header against site's allowed_origins
- Disallowed origins get no CORS headers (browser blocks response)
- Allowed origins get `Access-Control-Allow-Origin` + full CORS headers
- Widget endpoint (public) still enforces CORS even without auth

---

## Next Steps (Post-Wake)

1. **Review** — Check the commit messages and test coverage
2. **Test locally** — Run `python -m pytest tests/ -q` to verify 128 passing
3. **Deploy** — Site configs in `config/sites/*.json` drive everything; update as needed
4. **Monitor** — Audit logs in `data/local/audit.sqlite3`; retention policy TBD
5. **Plan P3** — Router + RAG answering + policy lint (queued, independent of P2)

---

## Key Design Decisions (For Context)

- **No in-memory sessions:** Replaced `_SESSIONS` dict with SQLite → sessions survive restarts
- **Optional site_id default:** interaction_store functions default to "default" site for backwards compatibility
- **Public widget endpoint:** No auth required (branding is public data), but still CORS-aware
- **Audit logging via AuditLog class:** Separate from interaction_store (different purposes: compliance vs. learning)
- **Rate limit keying:** (site_id, ip_address) per site config (prevents cross-site abuse)
- **Composite session key:** (session_id, site_id) in SQLite → clean multi-tenancy, no collisions

---

**All commits are clean, tests are green, and the system is ready for multi-site deployment.**
