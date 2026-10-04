# Demo chat harness — run it, and fix it when it breaks

The `/chat` page is a **development harness**, not the shippable widget. It holds a
site API key in browser-readable JavaScript, so it is disabled automatically when
`AURORA_ENV=production`.

## Start it

```powershell
cd <repo root>
$env:AURORA_RATE_LIMIT_BACKEND="sqlite"   # survives restarts, shared across workers
$env:AURORA_SESSION_BACKEND="sqlite"
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8001 --workers 2
```

Then open `http://127.0.0.1:8001/chat`.

Single worker (`--workers 1`) is fine for eyeballing the bot. Use 2 when you care
about replica-safe behaviour: rate limits and sessions must be shared, and only
the SQLite/Redis backends do that.

## The one rule that causes most breakage

**The origin you browse from must be listed in the site config.**

`config/sites/local.json` → `allowed_origins`. A browser sends an `Origin` header
on every POST, and `_auth_and_cors()` refuses any origin not on the list with
`403 Origin not allowed`.

`http://127.0.0.1:8001` and `http://localhost:8001` are **different origins**. Listing
one does not cover the other. If you change the port, add both:

```json
"allowed_origins": [
  "http://localhost:8001",
  "http://127.0.0.1:8001"
]
```

Origins are read at **startup**, so restart the server after editing.

This is exactly why curl can succeed while the browser fails: curl sends no
`Origin` header at all, and a request with no origin is allowed in development.
To reproduce what the browser actually does, send the header explicitly.

## Diagnosing, in order

Work from the outside in. Each step tells you which layer is at fault.

**1. Is the page served?**

```powershell
Invoke-WebRequest http://127.0.0.1:8001/chat -UseBasicParsing | % StatusCode
```

- `404` → the harness is off. `AURORA_ENV=production` or `AURORA_ENABLE_DEMO_CHAT=false`.
- `503` → the site named by `AURORA_DEMO_CHAT_SITE_ID` (default `local`) has no
  API key, or no config file was loaded.
- connection refused → nothing is listening; see "Ghost server" below.

**2. Does the API work without a browser?**

```powershell
$h = @{ "Content-Type"="application/json"; "X-API-Key"="sk_local_dev_test" }
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8001/api/conversations?site_id=local" -Headers $h -Body "{}"
```

Success here with a failing browser means the problem is the `Origin` header.

**3. Does it work *with* the browser's origin?**

Add `"Origin"="http://127.0.0.1:8001"` to `$h` and repeat. A `403` here is the
allowlist. This is the single most useful test.

**4. Status-code meanings**

| Code | Meaning | Fix |
|---|---|---|
| 401 `Invalid API key` | `X-API-Key` missing or wrong | use the key in the site config |
| 403 `Site ID mismatch` | `site_id` query param ≠ the key's site | make them match |
| 403 `Origin not allowed` | origin not in `allowed_origins` | add it, restart |
| 403 `Origin header required` | `AURORA_REQUIRE_ORIGIN=true` and no origin | send one, or unset in dev |
| 404 `Session not found` | stale `conversation_id` after a restart/expiry | reload the page to start a new conversation |
| 429 | rate limit | wait 60s, or raise `rate_limit.requests_per_minute` |

## Ghost server on the port

A uvicorn process can keep serving **old code** after you think you stopped it,
because Windows lets a second process bind the same port with `SO_REUSEADDR`. The
symptom is confusing: your source clearly has the fix, the new server starts
without error, and the browser still gets the old behaviour.

Check who is actually listening:

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen | Select-Object OwningProcess
Get-Process -Id <pid>
Stop-Process -Id <pid> -Force
```

Confirm you are talking to the new build before debugging anything else — put a
unique marker in the page and grep the served HTML for it:

```powershell
(Invoke-WebRequest http://127.0.0.1:8001/chat -UseBasicParsing).Content -match "Cannot reach the API"
```

If the process cannot be killed, **use a different port** and add that origin to
the config. That is faster than fighting the socket.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AURORA_ENV` | `development` | `production` disables the harness and tightens defaults |
| `AURORA_ENABLE_DEMO_CHAT` | on in dev | serve `/chat` |
| `AURORA_DEMO_CHAT_SITE_ID` | `local` | which site the harness authenticates as |
| `AURORA_REQUIRE_ORIGIN` | off in dev | refuse requests with no `Origin` |
| `AURORA_RATE_LIMIT_BACKEND` | memory | `sqlite`/`redis` to share limits across workers |
| `AURORA_SESSION_BACKEND` | memory | `sqlite`/`redis` to share sessions across workers |
| `AURORA_REDIS_URL` | — | Redis connection when using the redis backends |
| `AGENT_USE_LLM` | auto | force natural phrasing on/off; auto-detects Ollama |

## Ollama

Phrasing is optional. If Ollama is unreachable the bot falls back to literal
question text and still works — so a robotic-sounding bot usually means Ollama is
down, not that the conversation logic is broken.

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags | % models | % name
```

Note the **first** call to a model pays the cold-load cost, which on a CPU-only
box can exceed three minutes. Warm the model before timing anything.

## Local state

Everything lives under `data/local/`:

| File | Contents |
|---|---|
| `sessions.sqlite3` | conversations (24h TTL) |
| `rate_limits.sqlite3` | rate-limit hits |
| `interactions.sqlite3` | leads and outcomes |
| `audit.sqlite3` | auth and security events |

Deleting a file resets that concern. Do not delete them while the server is
running — the limiter self-heals, but you will see errors first.

## Lead capture

The chat gathers missing application-specific installation and project details
before voluntary contact. It reuses supplied facts, accepts unknown/skip and
allows "finish now" for an early handoff with visible gaps. Name is optional.
No customer-facing recommendation is made; provisional alternatives live only
in a protected sales brief. Consent is recorded when contact is supplied after
the consent question. Declining saves the anonymous brief without contact.
Callback timing is a preference, not a booking.

Leads are stored locally in `data/local/interactions.sqlite3`. Contact details
are not part of the conversation-learning answers or family-ranking inputs.
Read them through the separate admin endpoint, not the public conversation API:

```powershell
$env:AURORA_LEAD_ADMIN_KEY = "<set a private local admin key>"
$h = @{ "X-Aurora-Lead-Admin-Key" = $env:AURORA_LEAD_ADMIN_KEY }
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/admin/leads?site_id=local" -Headers $h
```

Without `AURORA_LEAD_ADMIN_KEY`, lead access is disabled. Keep the key out of
site configuration and browser code. Omit `site_id` to read leads for all
configured sites.

Open `/admin/briefs` for the read-only operator preview. Enter the separate key
there; it is sent in a header and not saved to browser storage. Use
`/api/admin/briefs?site_id=local` for structured briefs and
`/api/admin/briefs/{conversation_id}?site_id=local` for an individual JSON read.
The preview supports per-record JSON export; exports contain private data.
Pending/rejection learning reads and outcome writes require the operator key,
not the site API key. No endpoint automatically approves a candidate.

## Known limits of the harness

- Ships a site API key to the browser. Development only, by design.
- One retry is allowed if the phone number or email cannot be parsed; declining
  or failing to provide a valid contact ends the lead-capture step.
- No streaming.
- `conversation_id` is held in a JavaScript variable, so a page reload starts a
  new conversation and a server restart orphans the old one.
