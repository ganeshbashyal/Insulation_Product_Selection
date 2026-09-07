# P2 Multi-Site Serving — Implementation Plan

**Status:** Planning (2026-09-07)  
**Dependency:** P0 ✅, P1 ✅  
**Premise:** Hybrid retrieval works. Now harden single-machine demo into multi-site production infrastructure.

---

## Context

Today `web_agent.py` is:
- Single-tenant (no site concept, no per-site branding)
- Stateless within one worker (sessions in `_SESSIONS` dict, lost on restart)
- Unauthenticated (`/api/learning/*` open to anyone, no rate limiting)
- Unscoped CORS (no allowlist; every origin can call `/api/learning/*`)

P2 moves this to production-ready infrastructure without touching the retrieval or learning logic.

---

## Deliverables

### 1. Site configuration (`config/sites/`)

Each site is a JSON file defining branding, contact routing, and infrastructure rules.

**File:** `config/sites/{site_id}.json`  
**Schema:**
```json
{
  "site_id": "acme",
  "display_name": "ACME Construction",
  "colours": {"primary": "#003f5c", "accent": "#bc5090"},
  "logo_url": "https://acme.example.com/logo.png",
  "greeting": "G'day! ACME Insulation here...",
  "contact_method": "phone",  // "phone" | "email" | "callback"
  "phone": "+61-2-9999-1234",
  "callback_hours": "Mon–Fri 8am–5pm AEDT",
  "callback_wording": "We'll call you back within 2 hours",
  "privacy_text": "Your data stays with us...",
  "consent_text": "I agree to ACME contacting me about...",
  "allowed_origins": [
    "https://acme.example.com",
    "https://www.acme.example.com"
  ],
  "api_key": "sk_acme_xxxxx",  // SHA256 hash in production
  "rate_limit": {"requests_per_minute": 10, "per_ip": true},
  "manufacturer_emphasis": {  // optional soft boost (never a hard filter)
    "manufacturer_id": 0.2  // 0.0–1.0 boost to relevance ranking
  }
}
```

**Delivery:**
- Create 1–3 example configs (acme, test-site, local-dev)
- Each has a unique `api_key` (generated, stored as SHA256 hash in live config, plaintext in .env for dev)
- Loader validates all required fields at startup

### 2. Sessions persistence (`interaction_store` upgrade)

Move `_SESSIONS` dict to a persistent store so restarts don't drop conversations.

**Current state:** `web_agent.py` uses `_SESSIONS = {}` (in-process, lost on restart, single worker only)

**Target:** SQLite with TTL eviction (or Redis if deployed there)

**Schema:**
```sql
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  conversation_blob BLOB NOT NULL,  -- pickled Conversation object
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME,
  FOREIGN KEY (site_id) REFERENCES sites(site_id)
);

CREATE TABLE sites (
  site_id TEXT PRIMARY KEY,
  config_hash TEXT,
  last_synced DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Lifecycle:**
- On session access, update `accessed_at` and extend `expires_at` (TTL = 24h from last access)
- Background cleanup job runs hourly, deletes expired sessions
- No session can be accessed after `expires_at`

**Delivery:**
- Add `SessionStore` interface (supports both SQLite and Redis)
- `SQLiteSessionStore` implementation (default, local dev/testing)
- Migrate `_SESSIONS` dict access → store API in `web_agent.py`
- Add sessionstore cleanup task (cron or background thread)

### 3. API authentication (`/api/learning/*`)

Currently all endpoints are open. P2 adds per-site API key auth.

**Endpoints to guard:**
- `POST /api/learning/conversation` (start conversation)
- `POST /api/learning/message` (send message, get reply)
- `POST /api/learning/outcome` (submit `approved`/`rejected`/`edited`)

**Auth flow:**
1. Client includes `X-API-Key: sk_acme_xxxxx` header
2. Middleware resolves key → site_id, validates against `config/sites/{site_id}.json`
3. Request scoped to that site_id; session lookups filtered by site_id
4. Invalid key → 401 Unauthorized

**Delivery:**
- Add `@api_key_auth` decorator or middleware
- All three learning endpoints consume it
- 401/403 responses with audit logging
- Rate limiter keyed by (site_id, IP) per config

### 4. CORS hardening

Currently no CORS limits. P2 uses per-site allowlist.

**Mechanism:**
- On each request, extract `Origin` header
- Check against site config's `allowed_origins`
- Return `Access-Control-Allow-Origin: <origin>` only if in list
- If origin not in list, reject with 403

**Delivery:**
- CORS middleware reads site config
- Tests for origin spoofing, missing config, wildcard abuse

### 5. Widget (`static/widget.js`)

Ship a lightweight launcher that embeds the existing iframe with per-site theming.

**Purpose:** Allow `<script data-site-id="acme">` one-liner to inject a branded chatbot bubble.

**Delivery:**
- `static/widget.js` — shadow DOM launcher, reads `data-site-id`, injects iframe with site config
- Themeable via CSS (primary colour, logo, branding text)
- Communicates with `/api/widget-config?site_id=acme` to fetch colours/branding
- Falls back gracefully if config unreachable

**Example usage on partner site:**
```html
<script src="https://your-host/widget.js" data-site-id="acme"></script>
```

### 6. Audit logging

Log all auth events and learning outcomes to a queryable store.

**Schema:**
```sql
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  site_id TEXT,
  session_id TEXT,
  event_type TEXT,  -- "api_key_auth", "rate_limit_hit", "outcome_recorded", etc.
  details BLOB,
  ip_address TEXT,
  user_agent TEXT
);
```

**Delivery:**
- Audit every auth success/failure, outcome submission, session create/expire
- Retention policy: 90 days (config knob)
- Query interface for compliance review

---

## Architecture changes

### `web_agent.py` changes

1. Migrate `_SESSIONS` dict → `SessionStore` interface (inject at startup)
2. Add `site_id` to every request (from auth middleware)
3. Pass `site_id` to `interaction_store` on all writes
4. Load site config once at startup, validate, watch for changes
5. Populate CORS and rate-limit headers from site config

### New files

- `config/sites/acme.json`, `config/sites/local.json` (example configs)
- `interaction_store.py` additions: `SessionStore` interface, `SQLiteSessionStore`
- `session_cleanup.py` (background job)
- `auth_middleware.py` (API key validation)
- `static/widget.js` (client-side launcher)

### Updated files

- `web_agent.py` (sessions, auth, site scoping)
- `interaction_store.py` (session store interface)

---

## Testing & validation

### Unit tests

- `tests/test_auth_middleware.py` — key resolution, 401/403 paths
- `tests/test_session_store.py` — TTL eviction, multi-site isolation
- `tests/test_cors.py` — allowlist matching, origin spoofing
- `tests/test_widget_config.py` — config delivery, missing fields

### Integration tests

- Full conversation flow with site_id (auth → message → outcome)
- Session persistence across process restart (SQLite)
- Rate limiting per IP+site
- Audit log writes for all auth events

### Manual testing

- Embed widget on a test page with data-site-id
- Verify CORS headers match allowed_origins
- Check session survives server restart
- Verify audit log captures all events

---

## Sequencing & timeline

| Task | Estimate | Blocker? |
|------|----------|----------|
| Config schema + loaders | 2h | No |
| SessionStore interface + SQLite impl | 4h | No |
| Auth middleware + key validation | 2h | No |
| CORS hardening | 1h | No |
| Widget + config endpoint | 3h | No |
| Audit logging | 2h | No |
| Unit tests (auth, sessions, CORS) | 3h | No |
| Integration tests (full flow) | 3h | No |
| Manual testing (widget embed, restart) | 2h | No |
| **Total** | **~22h** | No |

All tasks are independent of P1 output (hybrid retrieval works regardless); can start immediately.

---

## Success criteria

1. ✅ Multiple sites can run on same codebase with different branding/contact routing
2. ✅ Sessions persist across server restart (SQLite backend)
3. ✅ `/api/learning/*` requires valid API key per site_id
4. ✅ CORS respects per-site allowlist
5. ✅ Widget embeds on partner sites with one-liner
6. ✅ Audit log captures auth and outcome events for compliance review
7. ✅ Rate limiting works per IP+site
8. ✅ Full test coverage (auth, sessions, CORS, widget)

---

## Open questions for owner

- **Session backend:** SQLite (simplest, no external deps) or Redis (if deployed there)?
- **API key generation:** Manual in config file, or admin UI?
- **Widget styling:** Minimal (just logo + colors) or full theming (fonts, animations)?
- **Audit retention:** 90 days, or longer for compliance?
