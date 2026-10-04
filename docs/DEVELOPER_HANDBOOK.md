# Aurora developer handbook

## Delivery boundary

Aurora is a local-first insulation knowledge and enquiry application. It answers
supported product questions, gathers project details and creates private human
review briefs. It does not approve customer suitability, installations,
compliance, quantities, quotations or orders. [Bot policy](../BOT_POLICY.md)
is the governing behavior contract.

The deployment-readiness programme uses deterministic local ingestion and
validation. Local model output is an optional annotation, never source truth,
completion or approval. Repeated failed maintenance policy-map proposals are
not a prerequisite for building the serving application.

**Implemented:** framework-independent knowledge access, all-family Knowledge
Validation, explicit local PDF intake, versioned commercial previews/activation,
private competitor inspection/review/export, content-addressed serving releases, reusable
storefront widget, serving-only dependency profile and SQLite backup/restore.
See the [local deployment runbook](LOCAL_DEPLOYMENT.md) for commands and limitations.
**Still owner-input-gated:** remaining supplier documents, actual human claim
review, the refreshed workbook, production domains/TLS and target-host capacity/
retention decisions. These features do not prove that real deployment is complete.

## Navigation

- [Architecture and ownership](#architecture-and-ownership)
- [Family coverage and validation](#family-coverage-and-validation)
- [Local developer commands](#local-developer-commands)
- [Deployment path and remaining gates](#deployment-path-and-remaining-gates)
- [Documentation ownership](#documentation-ownership)

## Architecture and ownership

| Layer | Owner / entrypoint | Meaning |
| --- | --- | --- |
| Canonical family metadata | `knowledge/*/families.json` | Stable identities and descriptive catalogue data, not approval of every technical claim |
| Source library and full pages | `local_source_review.py`; `data/tds`, `data/tds_inbox`, `evidence/raw` | Original source files and extraction status; source text stays unreviewed |
| Baseline performance registry | `knowledge/performance_evidence.json` | Variant/unit/scope/test-context claims with explicit review states |
| Commercial child records | `data/processed/product_catalogue_skus.csv` | Distinct row IDs, provenance and conflicts; codes may be shared |
| Authoring index | `product_research.py` | Join existing source, guide, research, evidence and SKU records |
| Shared governed service | `knowledge_service.py` | Framework-independent index/store access and effective evidence; no dependency on research HTTP routes |
| Shared retained family dossier | `family_knowledge.py`; `KnowledgeService.family` | Grouped occurrences, raw prose/tables and legacy original-unavailable provenance; never automatic approval |
| Offline read front door | `scripts/knowledge_workflow.py` | Same family service as Product Research, no network/models or publication writes |
| Draft and publication governance | `research_store.py`, `research_workflow.py` | Named reviewers, immutable revisions, preview/publish, source holds and revocations |
| Admin adapters | `research_api.py`, `templates/product_research.html`, `templates/knowledge_validation.html` | Named-account research and read-only coverage inspection |
| Customer facts and discovery | `conversation_service.py`, `product_answers.py`, `agent_core.py` | Direct known-product questions and adaptive enquiry gathering, not automatic selection |
| Private enquiry storage | `interaction_store.py`, `session_store.py` | Site-scoped sessions, consent and historical brief snapshots; not a knowledge database |
| Multi-site web service | `web_agent.py`, `site_config.py`, `cors_validator.py`, `auth_middleware.py` | Branding, origin rules, sessions and access boundaries |

`ProductAnswers` and default published family SKU lookup use the shared knowledge
service rather than importing `research_api`. Explicit alternate SKU SQLite
callers retain their legacy lookup contract. No family range is inferred as an
exact row's dimensions or stock.

The authoring service checks local filesystem fingerprints to maintain
stale-source behavior. The serving-only profile instead pins an explicitly
activated immutable release at startup, avoiding those authoring scans.
Release activation requires a restart; withdrawal updates must be deployed by
the operator, not inferred from an offline authoring machine.

Do not merge the research, session, enquiry and audit stores merely because they
use SQLite. Their privacy, retention and approval lifecycles are different.

### Incremental streamlining status

See the [shared knowledge workflow](KNOWLEDGE_WORKFLOW.md) for offline commands
and the local Llama development boundary.

Product Research and the offline CLI now share the private family-detail read
contract. The grouped dossier retains literal alternatives instead of choosing
a winner, and preserves raw family/research/guide content and manual records.
`legacy_supplied_original_unavailable` keeps lost-PDF knowledge visible without
claiming it has a manufacturer source. Historical guide headings and research
`ok` are not approval. The dossier hash identifies retained content, not a
publication or release.

Document-page reads, formal citations and competitor quotation checks share a
bounded full-page extraction cache with live source hash checks; a changed hash
requires refresh. This cache is in-memory, not a retained authoring backup.
The source audit includes the evidence library and every canonical family.

The standalone local maintenance runner uses Windows extended paths for its
verification copies and limits model generation to two CPU threads. It keeps
explicit propose/verify/apply gates; model candidates are still untrusted and
tests are not a sandbox. Smaller Llama drafts proved unreliable on code tasks;
the installed 8B model produced the bounded CLI dispatch after correction.

The incremental workflow now includes verified private authoring backup,
function-level ownership/reference inventory, preview-first source intake and
draft projections, manual-report preservation, named retained-field review and
shared GUI/CLI claim/publication operations. Unknown callers remain flagged for
review rather than deleted. Source/reviewer-scoped holds require an explicit
new-publication opt-in; other or unknown input dependencies still hold globally.
Serving releases remain immutable, and partial authoring holds block new builds.
This does not acquire missing supplier files, perform real claim approvals,
modernise every legacy utility or install a production storefront.

## Family coverage and validation

Open `/admin/knowledge` on the local server. It uses existing named Product
Research accounts and HttpOnly sessions; the sales key does not grant access.
The protected data endpoint is `/api/research/knowledge`, supporting `q`,
`manufacturer`, `gap`, `offset` and `limit`. The page includes every family,
including families without commercial rows, and links to its research detail.

Guide presence, identity state, source integrity, extraction state, research,
model audit, draft human review, effective publication and commercial coverage
are separate dimensions. No aggregate "complete" badge is provided. Refresh
inspects existing files and never starts extraction, research, downloading or
an Ollama job. Read-only access cannot approve or publish.

At the reviewed baseline, 283 families span 26 manufacturers; 414 distinct SKU
rows cover 30 families. The index linked existing sources to 90 families, while
104 PDFs were held across the local libraries. All 29 baseline evidence items
were pending human review. These are baseline observations, not permanent
constants or measurements of the private active publication overlay. Run the
inventory or use the signed-in page for current counts.

Document roles from extracted text are heuristics. An SDS is not a substitute
for TDS performance evidence. Missing or scanned pages remain gaps. Manual
guides, generated research and model `ok` states cannot authorise public facts.

## Local developer commands

From the worktree containing the current changes:

```powershell
python scripts\deployment_inventory.py
python scripts\knowledge_workflow.py overview
python scripts\knowledge_workflow.py families --query batt
python scripts\knowledge_workflow.py family YOUR_FAMILY_ID
python scripts\knowledge_workflow.py validation
python -m pytest tests\test_product_research.py tests\test_sku_catalogue.py tests\test_customer_dialogue.py -q
```

The inventory reads baseline files and static imports; it does not open private
review/customer databases, run models, download sources or write files. If desired,
save its stdout explicitly to an ignored local path:

```powershell
python scripts\deployment_inventory.py > data\local\deployment_inventory.json
```

Start the local prototype without models:

```powershell
$env:AGENT_USE_LLM = 'false'
$env:USE_HYBRID_RANKING = 'false'
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8001
```

Use [research account CLI](../scripts/research_accounts.py) for named accounts.
Never put passwords in commands, committed files or browser storage.
These are local development instructions, not a production exposure recipe.

## Deployment path and remaining gates

Represent every family and its unknowns at launch; only current reviewed facts
can be answered. Supplier files and the refreshed SKU workbook remain owner
inputs, not data to invent or fetch automatically.

Use deterministic local-file mapping/intake, then the versioned serving artifact
with source/review bindings, citations, revocations and commercial eligibility.
The default release shares canonical family knowledge while isolating enquiries;
an explicit release-bound visibility manifest can restrict facts, brief candidates
and derived exports per site. Subsets are never inferred from store names.
All sites use one pinned release.
Preview and explicit activation are separate from import. Withdrawal history
blocks a rollback that would resurrect a revoked claim.

The first storefront delivery is a small platform-independent widget and enquiry
handoff over the existing multi-site service. Live stock, prices, carts, orders,
automatic CRM transfer and store-specific commerce plugins are deferred. The
development `/chat` page is deliberately disabled in production; do not repackage
its embedded site key as a public widget secret.

The iframe widget uses per-conversation, per-site public chat capabilities rather
than a privileged browser API key. The runtime-only import gate, source holds,
two-site token isolation, browser rendering and backup/restore have synthetic
coverage. `/health/live` and `/health/ready` support local readiness checks.
Before actual deployment, install on two owner-controlled staging stores,
configure persistent state and TLS/admin exposure, establish retention rules,
and rehearse operational withdrawal/restart and consistent backup/restore.

Measure memory, cold startup, concurrent reply latency and restart persistence on
the intended host. Unit tests and historical completion reports do not establish
production capacity. No deployment was performed by the foundation changes.

## Documentation ownership

This handbook is the current engineering entrypoint, with
[README](../README.md) for quick start and [Bot policy](../BOT_POLICY.md) for
behavior. Preserve manufacturer guides and immutable source/review history.
Older P2 completion/status documents record earlier milestones, not current
deployment acceptance. Reconcile and label them incrementally rather than
concatenating or deleting them.

[Standalone local rebuild handover](LOCAL_REBUILD_HANDOVER.md) explains the
maintenance proposal tool, not deployment readiness. The
[admin rebuild contract](LOCAL_ADMIN_REBUILD_CONTRACT.md) retains the broader
knowledge, competitor and new-code catalogue requirements. Named competitor
notes/decisions and private JSON/text exports are implemented. Local intake keeps
every page and supports source-checked typed owner annotations across the
document-field categories; comprehensive automatic PDF table interpretation is
not claimed. Existing research publication still governs every customer fact.

`release_exports.py` and `scripts/export_knowledge_release.py` provide one
activated-release contract for retrieval cards, voice knowledge and structured
SQLite exports. The legacy raw-research builders remain authoring/historical
tools; their outputs must not be substituted for reviewed production releases.
Commercial versions preserve source bytes/raw codes and start with all new
eligibility held. Exact-variant continuity remains a named human review, never
an automatic transfer.
