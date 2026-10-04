# Local agent handover

## Mission and hard boundaries

The combined PR #26 and recent code is on the current development branch.
Use [the complete Aurora handover](docs/AURORA_PACKAGE_HANDOVER.md) for verified
retention, private backup/restore limits and VS Code resume instructions.
Only accepted code/documentation is pushed to GitHub; private documents,
databases, generated outputs and credentials remain local.

After repeated weak local-model drafts, the owner approved a deterministic
deployment-readiness path preserving the existing multi-site FastAPI service.
Use [the developer handbook](docs/DEVELOPER_HANDBOOK.md) for current architecture,
coverage and outstanding launch gates. All families must be represented; missing
facts stay unknown and only current reviewed technical claims may be served.
The first deployment scope is a reusable widget and enquiry handoff, not stock,
pricing, cart or order integrations.

The shared `knowledge_service.py`, `/admin/knowledge`, local PDF intake, commercial
version staging, named `/admin/competitors` review/export, site-scoped serving
release bundles, reviewed retrieval/voice/SQLite exports, iframe widget and
serving-only dependency profile are implemented. Follow the
[deployment runbook](docs/LOCAL_DEPLOYMENT.md). No real catalogue version or
evidence approvals were activated. Remaining supplier inputs, production site
configuration, retention policy and target-host capacity approval still gate launch.
Do not describe real deployment as complete.
Intake supports explicit typed page-quoted candidates, not automatic exhaustive
PDF interpretation. Release/version content IDs stay full SHA-256 even though
short filenames avoid Windows path failures. Current local regression runs
with models disabled and synthetic activations only; never manufacture real
approvals to make coverage appear complete.
The [admin contract](docs/LOCAL_ADMIN_REBUILD_CONTRACT.md) retains these boundaries.

The [standalone maintenance tool](docs/LOCAL_REBUILD_HANDOVER.md) remains available
for optional small local proposals. Do not retry the failed policy-map queue
as a deployment prerequisite. Candidate changes still need human review,
deterministic checks and explicit apply; no model can approve evidence.

Continue work on the insulation enquiry agent entirely on the local machine.
Do not use cloud infrastructure, hosted AI APIs, web search, or external
research services unless the owner explicitly changes this instruction. Do not
spend cloud model credits. Do not pull or install a new model; use only a model
already available through the local Ollama instance when a language model is
actually needed. Prefer deterministic code and tests for ordinary engineering
work.

Do not send customer data or repository content to external services. Keep test
data synthetic. Run the FastAPI service on loopback only during local work.
Never expose the lead endpoint or SQLite files to a network.

Preserve the downloaded source library: do not delete, move, rename, overwrite
or clean `data/tds/`, `data/tds_inbox/`,
`C:\Users\ganes\Desktop\Data Gathering\data\TDS\`, or
`C:\Users\ganes\Desktop\Aurora-POC\data\tds\`. These local/desktop materials
are still needed for the ongoing datasheet work and are not disposable build
artifacts. The desktop checkout has a shared Git worktree pointer; do not edit
or commit from it.

## Supported application

The supported chat entry point is `web_agent.py`, a local FastAPI service. The
retired desktop UI, its voice widget, configuration, and dependency have been
removed. Do not recreate another UI; keep customer-chat changes on the FastAPI
conversation path.

Main flow:

- `agent_core.py` / `enquiry_discovery.py`: serializable adaptive discovery,
  missing/unknown/skipped field tracking, lead capture, contact parsing and
  deterministic project-brief assembly.
- `conversation_service.py`: API turn orchestration, routing, local tools, RAG
  and policy linting.
- `product_answers.py`: read-only product identity, glossary, catalogue
  dimensions and verified performance answers; explicit evidence gaps.
- `sales_brief.py` / `local_source_review.py`: internal provisional alternatives,
  installation/source checks and all-page provenance report.
- `web_agent.py`: local chat page at `/chat`, conversation API, and protected
  lead/brief endpoints and read-only operator preview at `/admin/briefs`.
- `interaction_store.py`: SQLite conversation learning/outcome records and
  lead records in `data/local/interactions.sqlite3`.
- `DEMO_CHAT_CHEATSHEET.md`: local server and API troubleshooting.
- `BOT_POLICY.md`: customer-facing and product recommendation boundaries.
- `AUDIT_SECURITY.md`: current PII/storage limitations and security boundary.

Direct product enquiries do not enter the lead flow. Selection requests retain
facts supplied across turns and ask only missing application-specific questions:
placement, project stage/use, construction, access, depth, area, existing
insulation, moisture/exposure, requirements, locality and timing. Pipe/duct
questions include service/temperature; thermal wall/roof questions include
airspace. Unknown and skipped answers are explicit; "finish now" allows an
early handoff with visible gaps. Name is optional, not a required question.
Direct questions interrupt without advancing intake; element corrections
invalidate stale construction/access facts. Discovery and consent do not use
model wording.

After discovery, offer voluntary contact and optional callback timing.
No product is recommended publicly. `sales_brief_json` stores multiple
provisional candidates or a justified empty result, known facts, remaining
customer questions and source checks. Approval is always unset; saved is not
sent, and a callback is not booked. Operator outcomes do not approve candidates.

Commercial/compliance questions do not close qualification. The local tools
state their limitations without promising a callback or external handoff.
Completed leads are saved locally, not automatically sent to a CRM or person.

Leads are stored locally. Lead retrieval is disabled unless
`AURORA_LEAD_ADMIN_KEY` is set and presented in the
`X-Aurora-Lead-Admin-Key` header to `GET /api/admin/leads`. This is a
single shared local secret, not production-grade user authentication. Lead
fields are currently stored in plaintext and have no automatic retention or
deletion. Do not use real customer PII until the remaining controls documented
in `AUDIT_SECURITY.md` are implemented and approved.

Use `/admin/briefs` for the local preview and `/api/admin/briefs?site_id=local`
for site-scoped JSON. Pending/rejection/outcome learning endpoints also require
the operator secret. Preview keys remain in memory/header only; records are
never embedded in the unauthenticated page. Keep exported JSON private.

The preview now renders one readable card per saved enquiry, with facts,
contact/callback preference, unresolved information, provisional candidates
and expandable evidence provenance. Filter loaded cards and refresh after
the chat saves an enquiry; incomplete conversations are not saved briefs.
Clear and lock or changing the site removes both the records and page-memory
key. Legacy records remain marked as unreviewed, with completeness unknown.

This worktree's current loopback server loads its separate key from the ignored
`data\local\sales-operator-key.txt`. Keep that local file private; do not commit,
copy to the public site configuration, or put it in a URL. To restart with it:

```powershell
$env:AURORA_LEAD_ADMIN_KEY = (Get-Content -Raw "data\local\sales-operator-key.txt").Trim()
```

For a local UI execution check using an already-installed Edge browser:

```powershell
$env:AURORA_TEST_EDGE = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
python -m pytest tests\test_sales_briefs_display.py -q
```

That opt-in check uses a separate temporary browser profile and synthetic
records; it does not load real enquiries or download browser packages.

Run `python scripts\review_local_sources.py` only for supplied local sources.
The all-page report is `data\local\source_review.json`; source files are not
modified. The local run found 104 PDFs across TDS/inbox, with 3 needing
OCR/read review. Roles are heuristic, all text is pending human review, and
family-linked safety coverage is not established by an SDS URL.

## Local development

### Family-first Product Research workspace

`/admin/products` is a separate named-account research page; `/api/research`
protects its data and document endpoints. `product_research.py` joins all
canonical families with child CSV rows, source provenance, existing accuracy/
manual-input/triage outputs, guides and derived literature. It preserves all
283 families and 414 child record IDs, including duplicate codes and no-SKU
families. Missing reports are not interpreted as active/inactive tasks.

`research_store.py` stores local accounts, expiring sessions, immutable notes/
reviews, publication proposals and audit events. Bootstrap with
`python scripts\research_accounts.py create YOUR_USERNAME --roles reviewer publisher`;
choose the password interactively. No real account or default password was
created as part of implementation. The sales key is not a reviewer identity.

`research_workflow.py` validates exact source hashes/pages/quotes, scoped metric
fields, SKU applicability and row-conflict resolutions. Approval is draft-only.
Separate publisher preview/confirmation changes the active local snapshot;
`ProductAnswers.metrics` refreshes effective evidence on use and the default
`sku_catalogue.skus_for_family` uses published exact rows only, without inferring
dimensions or stock. Explicit alternate SQLite lookups retain their legacy
read semantics; they are not a replacement for the publication gate.
Generated CSVs remain source records with selection eligibility false.

Bound input changes invalidate the whole published overlay conservatively.
Source files/workbooks/baseline evidence are never rewritten by GUI review.
Revocations remain withdrawn even if other inputs become stale. Public chat
still cannot automatically select a family or SKU, quote or approve installation.

Selected-family audit actions reuse `validate_research_accuracy.validate_family`
with installed loopback `llama3.2:latest`, stage results/diffs in the review DB
and accept only model annotations. No downloads, competing research queue or
automatic manual-input rebuild. Run this research prototype with one server
worker; serial model locking is process-local. In-flight cancellation discards
the output, not the underlying Ollama computation. Following a process crash,
a job may remain `running`; inspect its journal before restarting that work.

Synthetic review/publication/API tests are in `tests\test_product_research.py`.
The opt-in installed-Edge test exercises actual GUI JS without real approvals:
`$env:AURORA_TEST_EDGE='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'`.
Tests use temporary accounts, PDFs and publication stores; never “verify” real
evidence as a test fixture. Local llama test suggestions were checked manually,
and suggestions that contradicted stale-preview/exact-row/source-preservation
requirements were rejected.

Open `notebooks/00_project_dashboard.ipynb` for the executable project document.
Default Run All is read-only. Tests, generated-data rebuilds and local chat
startup each require an exact approval value; reset approvals when done.
Downloaded TDS files are never synchronised or restored by this notebook.

From the repository root in PowerShell:

```powershell
$env:AURORA_RATE_LIMIT_BACKEND = "sqlite"
$env:AURORA_SESSION_BACKEND = "sqlite"
$env:AGENT_USE_LLM = "false"
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/chat`. Use the local demo API key already present
in `config/sites/local.json`; never copy it into new documentation or commit
any real secret. For optional local phrasing, check `ollama list` first and set
`AGENT_USE_LLM=true` only if Ollama and an already-installed local model are
available. Do not pull a model.

Run focused tests while iterating, then the complete offline suite:

```powershell
python -m pytest tests\test_lead_capture.py tests\test_conversation_service.py tests\test_web_agent_p2.py -q
python scripts\eval_customer_conversations.py
python -m pytest tests\test_sales_discovery.py -q
python -m pytest -q
python scripts\validate_catalogue.py
python scripts\validate_aircall_pack.py
python scripts\check_generated_artifacts.py
```

Read `data\local\conversation_eval_report.json` for synthetic full transcripts.
The evaluator uses a temporary SQLite store, leaving real leads untouched.
The dashboard's `evaluate-conversations` action is model-off. Local wording
evaluation is a separate explicit `--local-wording` option, requiring an
already-installed loopback model; run it serially and inspect actual fallback
and latency rather than claiming that mocks prove naturalness. Discovery
scenarios can correctly make zero model calls even with that flag enabled.

Some data-research scripts fetch manufacturer files or call hosted APIs. Do not
run `scripts/gemini_research_agent.py`, web/sitemap search, datasheet-download
pipelines, or other network-based research tools under this task's local-only
constraint.

## Remaining work from the current project

- Continue the missing-TDS handoff only when the owner supplies the outstanding
  family links or workbook. Preserve all downloaded source records listed
  above; do not replace them with network retrieval.
- Re-check the local evidence and identity findings for
  `ACOUSTICA_ACOUSTIC_BARRIER` and `HUSHTEC_BATT`; do not change evidence state
  without supporting source files and review.
- Extend the synthetic conversation corpus with owner-reviewed examples,
  particularly ambiguous product names and evidence gaps, before relaxing
  factual-answer or recommendation boundaries.
- Before real lead data is used, implement and get approval for encrypted lead
  storage, explicit consent handling, retention/deletion, operator
  authentication and access logging.
- Local packaging and runtime dependency separation remain future work. Keep
  any such changes offline and do not introduce hosted services.

## Git handoff

Continue on the current worktree branch. Do not create a branch, rebase, force
push, or publish repository contents elsewhere unless the owner explicitly
requests it. The owner requested the completed desktop-UI removal be committed
and pushed with the release tag `Aurora-V1`; create that tag only after the
changes are complete and verified, and only if that tag does not already exist.
