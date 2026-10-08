# Insulation Product Enquiry Knowledge Base

This repository contains a local-first product knowledge and enquiry bot for Australian insulation and building-material enquiries.

The current [developer handbook](docs/DEVELOPER_HANDBOOK.md) documents the
deterministic deployment path, data ownership and outstanding launch gates.
`/admin/knowledge` shows all-family source/review/publication gaps using existing
Product Research accounts. It does not approve facts or start ingestion.

The [shared knowledge workflow](docs/KNOWLEDGE_WORKFLOW.md) covers combined
family dossiers, the matching offline CLI, private authoring backup, guided
source/retained-field review, preview-first projections and scoped hold limits.
Existing IDs and lost-original knowledge are retained; no registry migration
or automatic deletion is required.

For optional bounded **standalone local-model proposals**, follow
[`docs/LOCAL_REBUILD_HANDOVER.md`](docs/LOCAL_REBUILD_HANDOVER.md).
The bootstrap stages Ollama proposals, verifies bounded candidates and requires
human confirmation before applying changes. Run it from ordinary PowerShell
with Copilot paused. Deployment work now uses deterministic tooling first;
the [deployment runbook](docs/LOCAL_DEPLOYMENT.md) describes the new serving-only
release profile and reusable widget. Real site installation remains owner-gated.
For local Alpha operating procedures, see the
[management guide](docs/AURORA_MANAGEMENT.md) and its
[process-management notebook](notebooks/aurora_alpha_management.ipynb).

The local POC answers product facts and gathers a review-ready enquiry. Multiple provisional product families appear only in a protected sales brief; the customer is not given an automatic recommendation. Selection, quantities and compliance decisions remain human-gated by [`BOT_POLICY.md`](BOT_POLICY.md).

## Current architecture

The repository has four related data layers:

1. **Family metadata** — `knowledge/*/families.json` contains the stable family identity, applications, ranking signals, source provenance and human gates for 283 families across 26 manufacturers.
2. **Research evidence** — `knowledge/*/research/*.json` contains extracted or attempted family research records. The contract includes range rows, technical properties, installation, clearances, limitations and source links; a populated record is not human approval.
3. **Human-readable knowledge** — `knowledge/*/*.md` preserves hand-authored family guidance and adds generated physical/technical and installation sections. Every family document now has both generated sections; missing evidence is marked as pending rather than inferred.
4. **Optional generated catalogue** — `data/local/family_catalogue.sqlite3`, when built, provides family, variant and installation tables. It is not required by the discovery/brief path and does not replace source verification.

The bot path is deliberately deterministic first: canonical family metadata supports internal discovery, while reviewed evidence controls public product claims. Stored PDF text is not model training and is not installation approval. Local models do not choose products or fill missing facts.

`agent_core.py` owns serializable adaptive discovery and contact state;
`enquiry_discovery.py` supplies application-specific questions and completeness tracking.
`conversation_service.py` applies routing, local tools, RAG, policy linting and
interaction logging for the local FastAPI service. There is one supported
conversation interface; the retired desktop demo is not part of the runtime.

Conversation flow is customer-led: general definitions and named-product
questions receive direct local answers without qualification or contact
capture. Selection requests gather missing installation and project details,
reuse volunteered answers, accept unknown/skip and support early handoff.
Corrections invalidate context specific to the old building element. Product
references survive interruptions and session restoration. `product_answers.py`
uses local family identity, glossary, confirmed catalogue links and verified
performance evidence; raw extracted ratings are not approved claims. Stock,
prices and arranged callbacks are not available from this local prototype.

### Conversation quality evaluation

Run the synthetic multi-turn scenarios without a model or real lead data:

```powershell
python scripts\eval_customer_conversations.py
python -m pytest tests\test_customer_dialogue.py tests\test_conversation_service.py tests\test_lead_capture.py -q
```

Full transcripts are written to the ignored
`data\local\conversation_eval_report.json`; lead/conversation records use a
temporary database. Inspect the answers and follow-ups, not just pass counts.
The dashboard exposes the same model-off evaluation as an approval-gated action.

Optional wording evaluation uses an already-installed loopback Ollama model,
serially, without downloads or hosted AI:

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "llama3.2:latest"
python scripts\eval_customer_conversations.py --local-wording --case greet-then-select --case resume-name --output data\local\conversation_wording_report.json
```

The report records actual model calls, replies and latency. Discovery/contact
questions now stay deterministic even when wording is enabled: these scenarios
may correctly make zero model calls. Direct facts remain evidence-led;
wording opt-in does not start a knowledge embedding/rebuild job.

Canonical application signals also remain separate from research-enriched
retrieval terms: enrichment cannot make a pipe-only family eligible for a wall
enquiry. Evidence and catalogue quality still limit internal candidate discovery;
missing or unverified properties require technical review.

## Structure

### Complete Manufacturer Coverage (26 manufacturers, 283 families)

**Deep-dive documentation and generated research:**
- [`knowledge/thermotec/`](knowledge/thermotec/README.md) — Thermotec product-family guides
- [`knowledge/fletcher/`](knowledge/fletcher/README.md) — Fletcher product-family guides

All other manufacturer directories contain the same family metadata, Markdown structure and normalized research contract. Technical completeness varies by family and is visible in each file's generated pending-evidence notices.

See [`knowledge/LITERATURE_REVIEW_STATUS.md`](knowledge/LITERATURE_REVIEW_STATUS.md) for complete manufacturer list and status.

### Knowledge Base Files

- [`knowledge/{manufacturer}/families.json`](knowledge/autex/families.json) — Structured family metadata for discovery and ranking (one per manufacturer)
- [`knowledge/{manufacturer}/README.md`](knowledge/autex/README.md) — Family index and retrieval rules (one per manufacturer)
- [`knowledge/{manufacturer}/{family}.md`](knowledge/autex/batt.md) — Product family documentation files
- [`knowledge/performance_evidence.json`](knowledge/performance_evidence.json) — normalized R, Rw, NRC/αw, fire, vapour and temperature evidence with variant, scope, test context and provenance.
- [`knowledge/LITERATURE_REVIEW_STATUS.md`](knowledge/LITERATURE_REVIEW_STATUS.md) — Documentation status and next steps for technical validation
- [`knowledge/industry/`](knowledge/industry/README.md) — General (not manufacturer-specific) Australian insulation industry reference: NCC/compliance intelligence, thermal/acoustic principles, product/material overviews, customer-support triage and a Q&A training corpus. Intended as background/RAG context for the enquiry bot, not a source of manufacturer-supported product claims.
- `data/local/family_catalogue.sqlite3` — generated, machine-local SQLite catalogue containing family metadata, structured variants and installation/clearance/limitation rows; it may not exist in a fresh clone until rebuilt.
- [`schemas/families.schema.json`](schemas/families.schema.json) — family metadata contract for the multi-manufacturer catalogue.
- [`scripts/normalize_family_json.py`](scripts/normalize_family_json.py) and [`scripts/normalize_research_json.py`](scripts/normalize_research_json.py) — normalize JSON records without discarding existing values.

### Supporting Files

- [`data/processed/product_catalogue_skus.csv`](data/processed/product_catalogue_skus.csv) — normalized SKU catalogue for all manufacturers. Stock-control fields are deliberately excluded.
- [`notebooks/01_thermotec_poc.ipynb`](notebooks/01_thermotec_poc.ipynb) — legacy validation notebook for Thermotec
- [`scripts/validate_fletcher.py`](scripts/validate_fletcher.py) — legacy validation script for Fletcher
- [`scripts/family_scoring.py`](scripts/family_scoring.py) — classification-aware priority scoring (scores follow the manufacturer's stated product use, not physical form alone); used by both generators and [`scripts/rescore_family_scores.py`](scripts/rescore_family_scores.py)
- [`scripts/audit_datasheet_links.py`](scripts/audit_datasheet_links.py) — audits every family's datasheet link against verified official manufacturer domains plus a live HTTP check; writes [`data/processed/datasheet_audit.csv`](data/processed/datasheet_audit.csv). [`scripts/fix_datasheet_links.py`](scripts/fix_datasheet_links.py) repoints wrong-domain links to the verified manufacturer site root (flagged `manufacturer_site_root_tds_pending`, old link kept as `legacy_source_url`). Ecowool, Hushtec and misc-brand links remain flagged `UNVERIFIED_MFR` pending a confirmed official domain.
- [`scripts/build_sku_dataset.py`](scripts/build_sku_dataset.py) — builds normalized SKU dataset from source Excel (now processes all manufacturers)
- [`scripts/generate_all_manufacturers.py`](scripts/generate_all_manufacturers.py) — generates knowledge base structure for new manufacturers
- [`schemas/`](schemas/) and [`scripts/validate_catalogue.py`](scripts/validate_catalogue.py) — machine-enforced structures and cross-file safety checks.
- [`tests/`](tests/) and [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — ranking, gating, catalogue and audit regression checks run on every push and pull request.
- [`aircall/`](aircall/README.md) — generated trial knowledge, agent instructions and four-question intake configuration derived from the governed catalogue.
- [`config/matching.json`](config/matching.json) — reviewed synonyms, fuzzy threshold, singularisation exceptions and the no-reliable-match threshold.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AUDIT_SECURITY.md`](AUDIT_SECURITY.md) — evidence approval, rollback, access, encryption and retention controls.
- [`MANUFACTURERS_EXPANSION.md`](MANUFACTURERS_EXPANSION.md) — Documentation of expansion from 2 to 26 manufacturers (2026-09-05)

## Data model and enrichment

The validated workbook export is an input snapshot, not the bot's live runtime database. [`scripts/build_sku_dataset.py`](scripts/build_sku_dataset.py) converts an approved workbook export into the normalized SKU CSV and SKU-to-evidence manifest. The local SQLite catalogue is built from family metadata and research JSON and is the runtime-friendly structured layer.

The Markdown files provide context the enquiry bot needs to interpret customer questions, including:

- intended applications and product roles;
- enquiry-routing and exclusion rules;
- important limitations and installation constraints;
- approved response language;
- links to official manufacturer sources.

Ratings guide internal candidate ordering, not customer recommendations. The private brief includes canonical element overlap, installation prerequisites, source provenance and gaps. Every candidate remains HOLD/REVIEW/REJECTED until separate human review.

Run the enrichment pipeline after new research is approved:

```powershell
python scripts/normalize_research_json.py
python scripts/normalize_family_json.py
python scripts/enrich_knowledge_docs.py
python scripts/build_family_sqlite.py
python scripts/build_aircall_pack.py
python scripts/validate_catalogue.py
python scripts/validate_aircall_pack.py
```

The Markdown generator only writes between its `AUTO:VARIANTS` and `AUTO:INSTALL` markers. It preserves hand-authored descriptions, selection logic, safeguards, approved language and source notes. When a family lacks usable range or installation evidence, it writes a pending notice and does not manufacture dimensions or product combinations.

Performance values must retain their test metric and system context. For example, `R` and `Rw` represent different properties and must never be treated as interchangeable.

## Validation convention

Each product-family file includes front matter with a stable `family_id`, manufacturer, validation status, and validation date. Product claims should be traceable to the official sources listed in that file.

The knowledge base covers all 26 manufacturers represented in the source data. Research and evidence status remain family-specific. Supported identity is necessary for provisional discovery but is not approval of installation or product suitability.

Rebuild the normalized SKU dataset from a validated local workbook export:

```powershell
python scripts/build_sku_dataset.py --source "C:\path\to\Product_Master_Bot_KB_SKU_Matched_cleaned.xlsx" --source-retrieved-at "2026-09-05T07:00:00Z"
python scripts/validate_catalogue.py
pytest -q
```

The checked-in CSV records the source workbook filename, source row, retrieval timestamp and SHA-256 hash. `sku_evidence_manifest.csv` provides the SKU → family → evidence chain. Generated CSV eligibility stays false: a verified family metric alone must not unlock a SKU. Exact-row eligibility is a separate named-reviewer decision, activated only by local publication, with resolved conflicts, active/READY content and explicitly applicable product/component evidence.

### Planned SKU recommendation stage

The current bot supports internal family discovery and direct documented product facts. Any future SKU capability must be a separate operator-only, gated retrieval stage:

1. Filter candidate rows by family, application, region and the customer's stated constraints.
2. Require published exact-row eligibility, verified applicable product/component evidence, current source provenance and a matching variant record.
3. Rank possible SKU candidates deterministically; never let the LLM choose the row.
4. Present results as possible matches, including product code, published dimensions, R-value and source status.
5. Require human confirmation before quoting, ordering, selecting quantity or claiming compliance.

A future private response contract should distinguish provisional candidates, evidence and human approval. Public chat responses must not expose these internal lists. Missing dimensions, conflicting sources or unverified identities must never produce confident SKU selection.

Aircall does not currently accept spreadsheet files as AI Voice Agent knowledge. `scripts/build_aircall_pack.py` converts the same governed family/evidence records into a concise paste-ready content block. Its manifest binds the generated pack to the exact source hashes, and validation prevents blocked families from entering the supported section.

## Evidence and approval workflow

Use [`scripts/ingest_evidence.py`](scripts/ingest_evidence.py) to put a PDF/HTML extraction into the ignored human-review inbox. Extraction never publishes a claim or changes recommendation eligibility. The local Product Research page supports named human reviews and a separate immutable publication overlay; it leaves `performance_evidence.json` and source files unchanged.

## Local Product Research

Open `http://127.0.0.1:8001/admin/products` on the same single-worker local
FastAPI server. Navigation is **product-family first**, including all 283
families; 414 commercial SKU records appear as child records under 30 families.
Search includes child codes without collapsing duplicate codes. Compare 2-4
families, inspect raw research/ranges/installation/safety gaps, read local PDF
pages, and export full JSON or a readable brief.

Create individual local accounts from this worktree using an owner-chosen
password (14-256 characters, entered interactively, not in command arguments):

```powershell
python scripts\research_accounts.py create YOUR_USERNAME --roles reviewer publisher
python scripts\research_accounts.py create READ_ONLY_USERNAME --roles reader
python scripts\research_accounts.py disable YOUR_USERNAME
```

There are no default credentials. `reader`, `reviewer` and `publisher` roles
separate reads, notes/reviews and publication. The sales operator key gives no
research permissions. Sessions use expiring HttpOnly/SameSite cookies and
same-origin/CSRF checks; account/review/publication events remain local in
ignored `data\local\product_research.sqlite3`. Protect and back up that file,
source files and exports; local filesystem access remains an administrative
trust boundary, not an enterprise identity or encrypted-storage service.

Existing script outputs remain authoritative research inputs. **Refresh existing
results** reads files only: it never starts the downloader, regenerates an edited
workbook or runs Gemini. The page shows the existing missing-TDS CSV and the
`supplied_tds_url` fields from the worktree copy of
`reports\missing_tds_products.xlsx`, without overwriting either. Missing pipeline
reports mean “no local report found,” not proof that a task is running or complete.

Reviewers must enter exact document/page/section/quote citations, variant,
scope, units and test context. Source quotes are checked against that page's
local extracted text; scanned/unreadable pages need separate manual/OCR work.
Notes and decisions retain immutable history with stale-edit conflicts.
SKU approval additionally requires explicit conflict/shared-code resolutions
and exact claim applicability. Family ranges are not exact-SKU dimensions,
and no live stock feed is implied.

**Approval alone changes nothing in the chatbot.** A publisher must preview
changes, removals and eligibility impact, then explicitly publish. The active
snapshot updates factual-answer evidence without restarting the chatbot.
Revocations withdraw claims; disabling a reviewer or changing bound inputs
holds published additions/eligibility for renewed review. This first version
conservatively binds the whole snapshot to the indexed input baseline, so an
input change may hold more than the directly edited family. Customer selection,
installation advice, quantities, quotes and compliance remain human-gated.

An explicit selected-family local audit reuses the existing accuracy validator
with installed loopback `llama3.2:latest`; no model is downloaded. Jobs run
serially within the single-worker research server and are staged separately.
Inspect the before/proposed comparison, discard it or accept it only as a
model-audit annotation. Original successful research and reports remain unchanged.
Cancellation discards the result; an in-flight model request may finish.
The inherited audit uses bounded text (12 pages/12000 characters) and is never
human verification; the source-page view can inspect every PDF page.

Completed FastAPI enquiries and private brief snapshots are saved in local SQLite. No candidate is automatically approved, no callback is booked, and no CRM/ticket delivery is configured. Production retention, authentication and storage safeguards still require separate work.

See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for the control mapped to each identified gap and the remaining production work.

## Local FastAPI chat

For a read-only project overview and explicitly enabled local commands, open
[`notebooks/00_project_dashboard.ipynb`](notebooks/00_project_dashboard.ipynb)
in your existing Jupyter environment or VS Code notebook editor. Its default
Run All inspects Git, TDS storage and data health without starting a server,
running rebuilds or calling AI services.

The local chat gathers an application-specific brief before voluntary contact:
construction, placement, access, usable depth, area, existing insulation,
exposure, project stage/use, requirements, location and timing. Pipe/duct
enquiries include service temperature; thermal wall/roof enquiries include
airspace. It asks only missing questions, allows unknown/skip or "finish now",
and does not show a product recommendation. The service uses local SQLite;
it does not require cloud infrastructure.
Run it on loopback for local development:

```powershell
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8001
```

Then open `http://127.0.0.1:8001/chat`. See
[`DEMO_CHAT_CHEATSHEET.md`](DEMO_CHAT_CHEATSHEET.md) for local setup and
troubleshooting. Leads are stored in `data/local/interactions.sqlite3`; reading
them requires the separate `AURORA_LEAD_ADMIN_KEY` configured on the server.
See [`AUDIT_SECURITY.md`](AUDIT_SECURITY.md) before using any real customer
contact details.

Open `http://127.0.0.1:8001/admin/briefs` for the read-only operator preview.
Each saved enquiry has its own readable card with captured facts, contact and
callback preference, unresolved questions, provisional candidates and expandable
source checks. Filter loaded records by enquiry ID, problem or product; refresh
after completing an enquiry. Unfinished chats and direct product questions do
not yet produce saved sales briefs. Legacy briefs are labelled for review.
Set `AURORA_LEAD_ADMIN_KEY` privately **before starting the server**, then enter
it in that page; it is sent only in `X-Aurora-Lead-Admin-Key`, never a URL or
browser storage. The page contains no records until authenticated. Select the
site explicitly; JSON reads use `/api/admin/briefs?site_id=local` and
`/api/admin/briefs/{conversation_id}?site_id=local`. Individual JSON exports
contain private data and must remain local.
The key remains in page memory for refresh only. **Clear and lock**, changing
the site, or leaving the page clears the loaded data and in-memory key.

To start or refresh the local Aurora/Matrix/Neo/Oracle stack in sequence, use
[`scripts/start_local_stack.ps1`](scripts/start_local_stack.ps1); see the
[local stack runbook](docs/LOCAL_STACK.md). Aurora Alpha on port 8011 remains
under its separate gated management notebook.

`sales_brief.py` keeps answered facts separate from unknown/skipped/unasked
fields, so sales need not repeat basic questions. Candidates include source
checks, not numerical confidence or automatic approval. Legacy leads remain
explicitly marked for review. Only synthetic contacts should be used until
plaintext-storage and retention limitations are resolved.

To review supplied PDFs offline, without fetching or modifying sources:

```powershell
python scripts\review_local_sources.py
```

The ignored `data\local\source_review.json` retains every extracted page,
hashes, blank/read-error pages and heuristic document roles. Internal briefs
link to this report only when its hash matches the current source. A URL,
research `ok` state or text extraction does not establish reviewed TDS/SDS
coverage. Missing or scanned sources stay pending; no evidence is promoted.

### Optional: product literature (sales/SEO pages)

[`scripts/generate_family_literature.py`](scripts/generate_family_literature.py) mines the deep-dive docs, `families.json` and the SKU catalogue to produce a concise, customer-facing Markdown page (`output/literature/<manufacturer>/<family>.md`) for every family, structured like the Thermotec 4-Zero literature draft (description, key features, applications + selection checklist, range table, technical data, compliance, install, safety, sustainability, warranty, spec clause, source register, review actions). Each page carries SEO `title`/`description`/`keywords`. Runs locally with no LLM; content-hashed so repeat runs only regenerate changed families:

```powershell
python scripts/generate_family_literature.py            # all 283 families
python scripts/generate_family_literature.py --only Autex
```

### TDS research tooling (not part of local-only chat runs)

The repository retains [`scripts/tds_research_agent.py`](scripts/tds_research_agent.py)
for future research. It can fetch manufacturer PDFs and search websites, so it
uses network resources and is not part of local-only chat runs. Do not run it
unless the owner explicitly authorises that research.

When TDS research is explicitly authorised, use the local model already
installed on the machine; do not pull a model or use an external AI service.

```powershell
ollama list
ollama serve
```

The pipeline is resumable and writes one family record at a time. Internet
retrieval must remain off unless authorised; supplied local TDS files and links
are the approved source material for that separate research task.

### Optional: deployable website agent

[`web_agent.py`](web_agent.py) serves the local FastAPI conversation flow and
reuses deterministic ranking/gates while logging conversations for interaction
learning:

```powershell
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8001
```

Interaction learning ([`interaction_store.py`](interaction_store.py)) records
conversations and internal discovery; reviewers can record enquiry outcomes (`approved`,
`edited` or `rejected`, with an optional corrected family). Per-family stats
(`/api/learning/families`), pending reviews (`/api/learning/pending`) and recent
rejections (`/api/learning/rejections`) show where the deterministic ranker
misfires. Pending reviews, rejections and outcome writes require the separate
operator header, not the public site key, and are site-scoped. An enquiry
outcome does not approve a candidate or change a saved brief's approval field.

### Optional: natural reply phrasing via a local LLM

Discovery and consent are deterministic and make no model calls. Optional
local phrasing remains available for supported wording paths; it cannot
choose products, fill missing customer facts or approve evidence. Use only
installed loopback models, without downloads:

```powershell
ollama list               # use a model already installed locally
ollama serve
```

Set `AGENT_USE_LLM=true` and restart the FastAPI service to enable optional local
phrasing when Ollama is reachable (`http://127.0.0.1:11434` by default;
override with `OLLAMA_HOST` and `OLLAMA_MODEL`). The LLM only rephrases text
already decided by the rules engine—it never selects a product,
chooses a SKU or asserts compliance. If the local server is unreachable, the
service falls back to fixed wording.

For a setup designed to stay local, use an already-installed local model and
avoid cloud-hosted model APIs. If phrasing feels slow, a smaller local model may
help; model generation and datasheet research are not required to run the chat.
