# Local agent handover

## Mission and hard boundaries

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

- `agent_core.py`: serializable conversation state, qualification questions,
  deterministic family ranking handoff, lead capture, contact parsing and
  deterministic project-brief assembly.
- `conversation_service.py`: API turn orchestration, routing, local tools, RAG
  and policy linting.
- `web_agent.py`: local chat page at `/chat`, conversation API, and protected
  lead-read endpoint.
- `interaction_store.py`: SQLite conversation learning/outcome records and
  lead records in `data/local/interactions.sqlite3`.
- `DEMO_CHAT_CHEATSHEET.md`: local server and API troubleshooting.
- `BOT_POLICY.md`: customer-facing and product recommendation boundaries.
- `AUDIT_SECURITY.md`: current PII/storage limitations and security boundary.

The lead flow asks the customer's name after their opening problem. It gives a
family recommendation before asking for a phone number or email, then asks for
a preferred callback time. A deterministic brief combines the customer's
actual answers; it does not call an LLM. The optional local model is only for
phrasing.

Leads are stored locally. Lead retrieval is disabled unless
`AURORA_LEAD_ADMIN_KEY` is set and presented in the
`X-Aurora-Lead-Admin-Key` header to `GET /api/admin/leads`. This is a
single shared local secret, not production-grade user authentication. Lead
fields are currently stored in plaintext and have no automatic retention or
deletion. Do not use real customer PII until the remaining controls documented
in `AUDIT_SECURITY.md` are implemented and approved.

## Local development

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
python -m pytest -q
python scripts\validate_catalogue.py
python scripts\validate_aircall_pack.py
python scripts\check_generated_artifacts.py
```

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
- Investigate the outstanding conversation-routing issue where a reply may not
  acknowledge the customer's latest message. Keep the fix deterministic,
  locally testable and on the FastAPI path.
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
