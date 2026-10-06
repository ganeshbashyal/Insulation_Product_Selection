# Local preparation and self-hosted storefront deployment

This is an executable deployment path, not a claim that real stores have been
installed. Source preparation stays local. There is no hosted AI, model download,
new cloud infrastructure or required GPU. The serving-only profile uses FastAPI,
Pydantic, Uvicorn, pytz and standard-library SQLite; it does not import pandas,
NumPy, PDF/workbook parsers, research routes or Jupyter.

## 1. Explicit local source intake

Keep originals under the checkout's `data` library. Create an owner-mapped JSON
manifest, for example in `data\local\source_intake.json`:

```json
{
  "documents": [
    {
      "path": "data/tds_inbox/example.pdf",
      "family_ids": ["EXACT_CANONICAL_FAMILY_ID"],
      "role": "tds"
    }
  ]
}
```

Roles are `tds`, `sds`, `installation` or `other`. List all applicable family IDs
explicitly; no filename/fuzzy identity acceptance or URL fetching occurs.
Run:

```powershell
python scripts\stage_local_documents.py data\local\source_intake.json
python scripts\stage_local_documents.py data\local\source_intake.json --confirm EXACT_PREVIEW_ID
```

The first command is read-only. The second stores full-page text and declared
associations in the ignored local intake journal. Source files and baseline
catalogue are unchanged. Research and Knowledge Validation see the associations
and extraction state after refresh, but they remain unreviewed. Scanned pages,
source hashes and unknown fields remain visible. Use existing research page
citations and named review/preview/publish controls to approve specific facts.
There is no automatic assertion that all fields have been extracted correctly.

For structured capture, a document may additionally contain a `candidates` list.
Each entry requires all of these fields (this example is synthetic, not evidence):

```json
{
  "family_id": "EXACT_CANONICAL_FAMILY_ID",
  "kind": "performance",
  "field": "thermal_r",
  "value": 2.0,
  "unit": "m2.K/W",
  "variant": "Exact source variant",
  "scope": "product",
  "page": 2,
  "quote": "Literal words present on page 2",
  "test_standard": "",
  "test_context": ""
}
```

Kinds cover identity, material, application, performance, dimension, standard,
limitation, installation, safety, warranty and reference. Values retain their
JSON scalar type; finite numbers are required. Empty context strings remain
unknown, not inferred. Every quotation must occur on the declared page and every
family must belong to the document's explicit associations. The source hash,
unreviewed status and per-kind candidate counts are preserved. An SDS performance
candidate carries an explicit primary-performance-source gap.
Research shows these candidates and whether their source is still current.
Zero candidate counts mean not captured, never inapplicable or approved.
This is explicit owner annotation plus complete-page extraction, not a claim
that arbitrary PDF tables can be automatically interpreted without review.

## 2. Stage refreshed commercial codes

The new workbook has not been supplied. Do not run a real activation with guessed
sheet/columns. Synthetic tests cover this path.

Place the owner's CSV/XLSX under `data`, and supply a JSON column mapping:

```json
{
  "family_id": "Canonical Family ID",
  "our_sku": "Internal Code",
  "supplier_sku": "Commercial Code",
  "product_name": "Product Name"
}
```

The input family column must contain explicit canonical IDs; resolve name-only
associations with the owner before activation. For XLSX an exact `--sheet` is
required. Formula cells and source rows are preserved, not silently evaluated.

```powershell
python scripts\stage_catalogue_version.py data\raw\new_catalogue.xlsx --mapping data\local\columns.json --sheet ExactSheet
python scripts\stage_catalogue_version.py data\raw\new_catalogue.xlsx --mapping data\local\columns.json --sheet ExactSheet --stage --confirm EXACT_VERSION_ID
python scripts\stage_catalogue_version.py data\raw\new_catalogue.xlsx --mapping data\local\columns.json --sheet ExactSheet --activate --confirm EXACT_VERSION_ID
```

If a version is already active, pass its ID as `--expected-active`.
Preview contains every row, duplicate/blank codes, raw values and mapping blockers.
All new rows start HOLD/REVIEW with eligibility false. No name/code/family match
transfers exact-variant approval. Old version files and historical brief records
remain unchanged. Activating changes the shared index and source baseline, so the
old review overlay is conservatively held pending renewed publication.

## 3. Build and activate reviewed serving data

```powershell
python scripts\build_knowledge_release.py
python scripts\build_knowledge_release.py --activate EXACT_RELEASE_ID --confirm EXACT_RELEASE_ID
```

Pass `--expected-active PREVIOUS_RELEASE_ID` when replacing an existing release.
The builder binds the current family catalogue, reviewed technical evidence,
withdrawals and commercial row eligibility into a content-addressed snapshot.
It refuses held source/reviewer publications. Build is separate from activation.
The activation command rechecks current authoring inputs against the staged
release. No account passwords, conversations or customer contacts are exported.

By default all canonical families share the public knowledge set. An optional
`--visibility data\local\site_visibility.json` binds explicit site subsets:

```json
{"shop_a": ["EXACT_CANONICAL_FAMILY_ID"], "shop_b": []}
```

Supply the same visibility file for build and activation. Unknown/duplicate
family IDs are rejected; an unlisted site has no family facts or private brief
candidates when no `*` default is specified. The `*` key, if explicitly used,
is a knowledge-policy default, never an allowed embedding origin. All identities
remain in the master release even when some sites have an empty subset.
Conversation resolution, follow-up topics, internal brief candidates and reviewed
export adapters apply the bound site policy; store names never imply mappings.

For optional retrieval/voice/SQLite consumers, export the activated release:

```powershell
python scripts\export_knowledge_release.py --releases data\local\releases --site-id shop_a --output data\local\exports\NEW_EXPORT
```

The new directory contains version-bound reviewed cards, a human-gated voice
knowledge file, structured SQLite identities/claims/commercial rows and checksums.
It excludes generated research descriptions, inferred dimensions and unreviewed
values. It refuses overwrite and detects release switching during construction.
Re-export after withdrawals. Legacy family SQLite, retrieval-card and Aircall
builders remain authoring/historical tools, not production reviewed exports.

All family identities and empty evidence lists remain represented. Unreviewed
generated descriptions, technical values, dimensions and general RAG answers are
not served as authoritative facts in release mode. Curated glossary definitions
remain available; unsupported questions explicitly go to human review.

The process pins one release at startup. **Restart after activation** so family
identity, evidence, eligibility and brief snapshots agree. The release directory
and service filesystem are trusted operator assets, not a public upload endpoint.
Changes to offline sources cannot magically revoke a disconnected server:
activate a withdrawal release and restart immediately when facts are withdrawn.
The library remembers withdrawn claim IDs and refuses a rollback that resurrects
them. Restoring a whole old directory must not bypass the withdrawal history.

## 4. Serving-only runtime

Use `requirements-runtime.txt` on the self-hosted machine. Prepare dependencies
from an owner-controlled offline wheelhouse; do not download tools as part of a
chat request. A separate authoring installation is needed for import/review.

### Alpha package allowlist gate

The clean Alpha package target is an explicit dependency allowlist rooted in:
`web_agent.py`, `storefront_api.py`, `conversation_service.py`, `agent_core.py`,
`router.py`, `product_answers.py`, `knowledge_release.py`, `release_exports.py`,
`session_store.py`, `site_config.py`, `auth_middleware.py`, and
`interaction_store.py`; plus only the required `tools/`, `templates/`, one
reviewed release snapshot, and runtime requirements. Resolve and document any
strictly necessary dependency closure before adding files.

Exclude notebooks, research ingestion/generation scripts, historical maintenance
candidates, raw source archives, unreviewed literature from public retrieval,
development tests, and legacy Streamlit material. Research/admin mutation routes
must be absent from Alpha or individually protected by an explicit production
authorization boundary. The package manifest and final tree audit must prove
these exclusions; a passing build alone is not sufficient.

`scripts/package_runtime.py` now explicitly lists `release_exports.py` and the
supporting runtime dependency closure, and enumerates the required tool modules
instead of copying every `tools/*.py` file. The package regression verifies
manifest hashes, rejects an unlisted tool, starts from the copied directory,
and confirms research/catalogue mutation routes are absent in serving-only
mode. This verifies the builder contract with a synthetic release; it does not
make a real package approved or deployable. Re-audit the manifest and route
boundary whenever the runtime dependency set changes.

After activating a local release, create an allowlisted portable serving folder:

```powershell
python scripts\package_runtime.py --releases data\local\releases --name YOUR_RELEASE_PACKAGE
```

The output is under ignored `data\local\distribution`. Only explicit runtime
modules/templates/configuration, the curated glossary, runbook and active release
are copied. No source PDFs/workbooks, site secrets, customer databases, research
routes or notebooks are included. Inspect the package manifest before moving
that folder to the approved self-hosted machine. Source checkout state and
original documents stay on the authoring machine.

Release, intake and commercial-version filenames use short hash prefixes to fit
deep Windows worktrees; the full SHA-256 identity remains in their content and
confirmation/pointer contracts. Checksums and collisions remain fail-closed.
Release/catalogue readers also accept legacy full-hash filenames.
Packaging checks the Windows path budget before creating its output; use a short
package name or shorter checkout path when instructed.

Create an explicit site configuration per store under an operator-controlled
directory, with literal HTTPS origins (no `*`), branding/contact/privacy settings
and no committed API key. Reuse the existing `SiteConfig` schema.
Inject site API keys via `AURORA_SITE_API_KEY_<SITE_ID>` for the private legacy API;
the production widget does not receive those keys.

Example on the local host; replace directories with the actual approved paths:

```powershell
$env:AURORA_ENV = 'production'
$env:AURORA_SERVING_ONLY = 'true'
$env:AURORA_RELEASE_DIR = 'C:\Aurora\releases'
$env:AURORA_STATE_DIR = 'C:\Aurora\state'
$env:AURORA_SITES_DIR = 'C:\Aurora\sites'
$env:AGENT_USE_LLM = 'false'
$env:USE_HYBRID_RANKING = 'false'
$env:AURORA_SESSION_BACKEND = 'sqlite'
$env:AURORA_RATE_LIMIT_BACKEND = 'sqlite'
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8001 --workers 1
```

Serving-only forces model phrasing off and does not mount research account,
review or source-file routes. The development `/chat` harness is disabled in
production. `/health/live` checks the process; `/health/ready` reports initialization
and the pinned release. This profile currently retains existing private operator
APIs; restrict them at the reverse proxy and use separate operator credentials.
Never expose SQLite, release/backup directories or secrets as static assets.

Use a self-hosted TLS reverse proxy to the loopback service. Configure trusted
forwarded headers only for that proxy, preserve Host/HTTPS origin information,
restrict admin endpoints, and apply request-size/time limits. No host/domain/TLS
credentials have been supplied or provisioned by this implementation.
Single-worker operation is required: widget turns are serialized within the
process. Multi-worker conversation ordering is not claimed.

## 5. Embed on each store

The launcher accepts only page context explicitly supplied as data attributes.
For a product page, the WooCommerce template may render:

```html
<script defer src="https://YOUR_APPROVED_BOT_HOST/widget.js"
        data-site-id="YOUR_SITE_ID"
        data-page-type="product"
        data-product-id="123"
        data-variation-id="456"
        data-product-name="Example product"
        data-product-category="Ceiling"
        data-product-url="https://shop.example/products/example"></script>
```

Use only values available to the public product page; never add account, order,
cart, payment, stock or pricing data. `data-page-type` is one of `product`,
`category`, `content` or `other`. The launcher also sends the current origin and
path, excluding the browser query and fragment. It omits context on standard
WooCommerce account, cart and checkout routes, which the API also rejects.
Context crosses into the chat
frame by `postMessage`, is checked against the site's exact configured origin,
and the server strips query/fragment from supplied URLs. The chat asks the
customer whether the page hint is relevant; rejecting it is recorded as
`not_relevant`. This metadata is retained as context only and is not evidence
of product identity or suitability, nor does it select a family/SKU.

The launcher embeds `/widget` on the bot origin. CSP `frame-ancestors` allows only
the configured literal store origins. Frame chat requests remain same-origin;
no cross-origin credential preflight or third-party session cookie is required.
The browser receives a random one-hour capability restricted to one site and
conversation. Tokens are hashed in SQLite, stay in page memory and cannot access
research or operator APIs. The bootstrap is intentionally public chat access,
not authentication of a customer identity; Origin/CSP are not secret credentials.
Rate limits and message/conversation bounds limit public use.

Install on two staging stores first. Verify branding, opening/reply flow,
known-product ambiguity/unknowns, consented enquiry handoff, blocked embeds and
cross-site session refusal. Live stock, pricing, cart/order and automatic CRM
transfers are not included.

## 6. Private backup and restore

Stop the serving process first to obtain a consistent boundary across stores.
These commands use SQLite's backup API, not raw copying of live WAL files:

```powershell
python scripts\runtime_backup.py backup --state C:\Aurora\state --backup C:\Aurora\backups\NEW_BACKUP --confirm-server-stopped
python scripts\runtime_backup.py restore --state C:\Aurora\restored-state --backup C:\Aurora\backups\NEW_BACKUP --confirm-server-stopped
```

Restore only into an empty directory. Checksums and SQLite integrity are checked.
Backups contain private customer/session data: restrict filesystem access and
apply the owner's retention/encryption policy. Keep site secrets and release
withdrawal history backed up separately using protected operator procedures.
No unattended lead deletion or invented retention period is enabled.

## 7. Private competitor review

Owner-supplied JSON lives under `data\local\competitors`, with a separate stable
`competitor_id`, name, exact `our_family_id` and `claims` list. Each claim needs
`metric`, typed `value`, `unit`, `variant`, `scope`, `test_standard`,
`test_context` and a `citation` containing a local data PDF path, SHA-256,
positive page number and literal quote. These records never enter public facts,
release exports or commercial eligibility.

`/admin/competitors` uses named Product Research accounts. A reader can inspect
and export private JSON/readable text; an account with both reader and reviewer
roles can record notes and a comparable/not-comparable/needs-information decision.
Same-origin CSRF, exact evidence hashes and revision checks protect edits.
Comparable requires current citations and matching reviewed metric, unit, exact
variant, product/system scope and test standard/context for every candidate.
Changed evidence or disabled reviewers hold old annotations. Decisions are
internal comparison reviews, not performance publication or automatic winners.
Original files, historical notes and our reviewed facts remain separate.

## Private Oracle assistant

Oracle is a separate owner-only local page at `/oracle`; it is not part of the
customer-serving package and is disabled in production. In local development,
set up its independent passphrase interactively:

```powershell
python scripts\oracle_owner.py
```

Use `python scripts\oracle_owner.py --reset` to replace the passphrase and
invalidate existing Oracle sessions. Oracle conversations, notes, tasks and
login state use a dedicated local SQLite database; protect the application
state directory with the owner's filesystem backup and access-control policy.
Oracle accepts requests only from loopback clients, uses a separate owner
session and CSRF token, and calls Ollama only through a loopback HTTP endpoint.
If Ollama is unavailable or no model is selected, Oracle uses grounded local
excerpts instead. It does not query the web, fall back to a cloud model, write
production knowledge, or expose Oracle data through Aurora or Neo.

Oracle searches local family guides, linked TDS PDFs, curated NCC/ABCB
literature and explicitly owner-supplied pricing snapshots. Extracted PDF text
and maintained guides remain unreviewed material until a human review gate
changes their status. A citation opens the current local file only when its
content hash still matches the indexed source.

The four-tab Matrix manager and its separate Neo sales assistant are documented
in [Oracle and Matrix local workspaces](ORACLE_MATRIX.md). They are excluded
from the V1 Alpha serving package as well.

## Release gate still requiring owner inputs

The local implementation and synthetic checks do not supply missing supplier
documents, human claim approvals, the new workbook, real store domains or a
target-host capacity result. Review these inputs, measure memory/startup/p95 under
the actual expected concurrent traffic, rehearse restart/restore and authorize
installation before calling the real deployment complete.

## Local acceptance evidence and limits

The current implementation was exercised with models disabled, Ollama pointed
at an unreachable loopback port, and the already-installed Edge browser:

```powershell
$env:AGENT_USE_LLM = 'false'
$env:USE_HYBRID_RANKING = 'false'
$env:OLLAMA_HOST = 'http://127.0.0.1:9'
$env:AURORA_TEST_EDGE = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
python -m pytest -q
git diff --check
```

Result: 572 passed, 11 environment-gated checks skipped; no model generation,
supplier fetching or dependency downloads were used. Synthetic cases cover
activation/withdrawal, held imports, site/token isolation, typed quotations,
named comparison edits and stale reviews, reviewed exports, private backups
and the copied portable runtime starting without authoring files.
Runtime import checks exclude heavy authoring/model libraries; this is not a
claim that an offline wheelhouse has been installed on the target host.

The refreshed loopback authoring app serves chat, brief/research/knowledge/
competitor pages and widget assets. Unauthenticated research data/export
requests are refused. It remains in authoring mode. Separately, the allowlisted
serving package has activated release
`1134bcd195cba93072f0f7190219b0a572d6c7dc899ac27cbbbaf11c5eae72f6`, but this
is not a live e-commerce installation or approval of every product fact. The
implementation is local worktree state, not a pushed release.

### Same-machine Windows staging rehearsal

The package was staged under
`%LOCALAPPDATA%\Aurora\staging\alpha-serving-1134bcd1` by copying only the
46 files in its verified package manifest. The rehearsal used a fresh isolated
SQLite state directory, separate redacted site-config copies, test-only
environment keys, one Uvicorn worker, `AGENT_USE_LLM=false`, and loopback
`127.0.0.1:8011`. No production credentials, site-config key values, or
customer data were copied into the staged package.

The staged service returned live and ready, reported serving-only mode and the
release above, served the widget frame, and had no `/api/research` routes in
its OpenAPI surface. A synthetic widget conversation and capability were
accepted after a stop/start, proving local SQLite session and token persistence.
The staged backup/restore tool backed up `audit.sqlite3`, `rate_limits.sqlite3`,
`sessions.sqlite3`, and `widget_tokens.sqlite3`; restored copies passed SQLite
integrity checks and matched the staged database counts. The rehearsal backup
and restored state are private local artifacts, not package contents.

This proves a same-machine loopback rehearsal only. It does not test an external
browser, public TLS/reverse proxy, another host, real operator keys, capacity,
or a real store integration. Do not expose this service beyond loopback or
treat test-only site keys as deployment credentials. Before using customer-
facing data, confirm the release visibility policy and complete human/source
review for the product facts; local model validation is evidence for review,
not source truth.

For a repeatable local start/health/stop check from one PowerShell window:

```powershell
$Root = Join-Path $env:LOCALAPPDATA 'Aurora\staging'
$Package = Join-Path $Root 'alpha-serving-1134bcd1'
$env:AURORA_ENV = 'production'
$env:AURORA_SERVING_ONLY = 'true'
$env:AURORA_RELEASE_DIR = Join-Path $Package 'releases'
$env:AURORA_STATE_DIR = Join-Path $Root 'state-1134bcd1'
$env:AURORA_SITES_DIR = Join-Path $Root 'operator\sites'
$env:AGENT_USE_LLM = 'false'
$env:USE_HYBRID_RANKING = 'false'
$env:AURORA_SESSION_BACKEND = 'sqlite'
$env:AURORA_RATE_LIMIT_BACKEND = 'sqlite'
$Server = Start-Process -FilePath (Get-Command python).Source `
  -ArgumentList @('-m','uvicorn','web_agent:app','--host','127.0.0.1','--port','8011','--workers','1') `
  -WorkingDirectory $Package -PassThru
try {
  Invoke-RestMethod http://127.0.0.1:8011/health/live
  Invoke-RestMethod http://127.0.0.1:8011/health/ready
} finally {
  Stop-Process -Id $Server.Id
  Wait-Process -Id $Server.Id -ErrorAction SilentlyContinue
}
```

Keep any operator API keys in the launching process environment, populated by
the owner's protected local procedure; do not put values in this command,
script, or package. Keep the listener on loopback unless a separately reviewed
proxy setup is ready. Use a dedicated Windows service/supervisor and protected
logs for unattended operation; this interactive command is a manual rehearsal,
not a service manager.
