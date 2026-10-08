# Oracle and Matrix local workspaces

## Assistant roles and policy management

The assistants share a small behavior contract implemented in
`assistant_policy.py`, but remain separate products:

| Assistant | Role | Policy and evidence boundary |
| --- | --- | --- |
| Aurora | Customer enquiry flow | `BOT_POLICY.md` remains authoritative. `llm_client.py` may only rephrase deterministic application text; it does not retrieve or decide product claims. |
| Neo | Internal sales support | `neo_assistant.py` supports natural live-call conversation through a selected local model while grounding product/technical claims in governed evidence; it cannot access Oracle-private pricing or conversations. |
| Oracle | Free-flowing private owner assistant | `oracle_assistant.py` supports general conversation through a selected loopback-only local model and searches the owner's allowed local sources for workspace-specific facts; it cannot expose private context to Aurora or Neo. |

Keep role-specific prompts, APIs, authentication, evidence retrieval and stores
separate. Shared policy changes should be covered by tests for all three
assistant entry points; role-specific changes should use that assistant's
focused tests. All three run against local resources only in this workspace;
their different capabilities must not be inferred from the shared prompt.
The shared policy module is included in Aurora's allowlisted runtime package
because `llm_client.py` imports it; this does not include Oracle or Neo routes,
prompts, stores, or owner-only data. The Alpha package remains Aurora-only:
Neo and Oracle stay on the owner's PC, and local Ollama model weights are not
copied into the package. Each PC uses its own locally installed model.

## Release boundary

Oracle and Matrix are owner/operator tools for the local workstation. **Oracle
must remain separate from, and must not ship in, the V1 Alpha customer
serving release.** Oracle conversations, notes, tasks, prompt, owner credential,
and endpoints are not customer data and must not be copied into Aurora or Neo.

Matrix and Neo are also local-only management/sales tools. They are excluded
from the V1 Alpha runtime package along with Oracle. The release builder uses
an explicit serving allowlist; do not add `matrix_api.py`, `neo_api.py`,
`neo_assistant.py`, `neo_store.py`, `operations_api.py`,
`local_operations.py`, `templates\matrix.html`,
`templates\neo.html`, or any Oracle resource to that allowlist. The package
manifest records the owner-only exclusions. Production and serving-only
processes do not mount these routes.

## Matrix workspaces

The local Matrix manager is `/matrix` and has six tabs:

| Tab | Purpose |
| --- | --- |
| Aurora | Local customer-enquiry/demo harness, separate from internal Neo and private Oracle. |
| Neo | Internal local sales copilot with local model selection, product/TDS evidence citations, separate conversation storage, human-review sales briefs/tasks, and a transient deterministic Decimal pricing calculator with exact-SKU Melbourne V3 price lookup. Calculator inputs/results are not saved and do not use local models or Oracle-private pricing. |
| Oracle | Link to the passphrase-protected owner assistant, with its own conversations, notes, tasks, and evidence search. |
| Compare agents | Side-by-side Aurora/Neo/Oracle view that forwards one prompt after each local session is ready; the existing sessions and stores remain isolated. |
| Admin | Links to existing knowledge, product research, competitor review, catalogue, sales-brief, and health pages. Existing authentication and review gates still apply. |
| Operations | Live status for known local services, installed/resident Ollama models, and recognized long-running local service/model/script processes. Requires the Oracle owner session for status and control actions. |

The **Compare agents** tab loads the three existing local interfaces side by
side. After Aurora and Neo report ready and Oracle is unlocked, one submitted
prompt is forwarded to each frame using same-origin browser messaging. This
uses each assistant's existing API, selected local model, session and
conversation store; prompts and histories are not copied between bots. The
same prompt is stored in each bot's own local conversation, and the Aurora
frame is the development enquiry harness, so do not enter customer personal
information. The tab is a comparison aid, not an Alpha feature or shared
assistant runtime.

Matrix, Neo, and Oracle accept loopback connections only. Neo's conversation
and draft records are in its own `data\local\neo.sqlite3`; Oracle uses a
different private database. Neo retrieves governed local product evidence but
does not retrieve Oracle's owner-provided private pricing snapshots. Neo model
calls use local Ollama only. It selects a resident local model by default when
available. Oracle's model selector lists every installed chat-capable model and
defaults to a resident installed chat-capable model when one is available; each conversation
keeps its selected model, and choosing no model uses local-source-only
responses. Embedding-only models are not presented as chat choices. Neo retrieval
candidates are structured catalogue records and must
be formatted before being added to clarification prompts; complete user/assistant
exchanges are saved atomically so failed answers do not leave orphan user turns.
Greetings and call-planning conversation are free-flowing; technical
product claims still require applicable verified evidence and citations. No tab
sends email, changes CRM/customer records, approves product claims, or activates releases.

The Operations tab reads process ownership from Windows and permits stopping
only processes owned by the current Windows account. It blocks core Windows
and security processes, the dashboard's own process, and the serving-only
Aurora Alpha listener. A process stop requires inspection and typing the
displayed PID confirmation. Ollama controls can only load already-installed
models for 1, 5, or 30 minutes or unload a model already resident in local
Ollama. It never downloads models, launches arbitrary commands, restarts
services, or stores dashboard runtime/task state. Process command-line
arguments are not returned to the browser.

## Local password manager

Use the separate Windows desktop utility to keep local service credentials:

```powershell
python scripts\password_manager.py
```

It uses Windows Credential Manager generic credentials for the currently
signed-in Windows account. It does not create a custom vault file, add another
master password, or put credentials in Matrix/Neo/Oracle conversations or the
Git repository. Entries are listed without passwords; a user explicitly
chooses to copy a password to the Windows clipboard. Clear the clipboard after
use. The local Windows account and its sign-in protection are the access
boundary, so protect the computer and its Windows account. Windows account
recovery or a profile migration should follow Windows' supported credential
backup/recovery process; this small utility is not a cross-device vault or
backup system.

The password string that appeared in the setup conversation should be treated
as exposed and changed before it is saved or used. Do not prefill it in the
manager or put credentials in commands, screenshots, source control, or
documentation.

## Start the local manager

From the repository root in PowerShell:

```powershell
.\scripts\start_local_stack.ps1
```

This sequential helper starts/restarts the development services on ports 8001
and 8002, verifies local Ollama and the separately managed Alpha release on
8011, and loads the private operator key from the ignored local key file. For
preflight without process changes, append `-WhatIf`. See
[`LOCAL_STACK.md`](LOCAL_STACK.md). Open `http://127.0.0.1:8002/matrix`. The
app must bind to loopback; do not change the host to `0.0.0.0` for these
owner/operator interfaces. The Aurora tab is a local demo harness, not a
production/customer endpoint.

If using the standalone Oracle page, set up its passphrase once in a separate
PowerShell window at the same repository root:

```powershell
python scripts\oracle_owner.py
```

Enter and confirm a 14-character-or-longer passphrase at the hidden prompts.
Use `python scripts\oracle_owner.py --reset` only to replace the credential;
reset invalidates active Oracle sessions. The passphrase does not go in command
arguments or this document. Open Oracle at `http://127.0.0.1:8002/oracle`.

Neo is available from Matrix's Neo tab or directly at
`http://127.0.0.1:8002/neo`. Select a model listed by the local Ollama service,
or use the grounded evidence-only fallback. Neo history and review outputs are
local and isolated from Oracle and Aurora. Review any generated sales brief or
task before sharing it. The pricing calculator can read the exact Melbourne
SKU from `Insulation_Easy_Sell_Price_List_V3_Final_Staff_Release.xlsm` in the
signed-in user's Downloads folder, or from the local path in
`NEO_PRICING_WORKBOOK`. It reads the workbook without modifying it, rejects
inactive, unavailable, ambiguous, or unpriced SKUs, and shows the source
workbook and sheets. Price lookup and calculations remain transient.

## Operational limits

- Do not expose the manager, Neo or Oracle port to a LAN, reverse proxy, or
  public deployment.
- A local-only UI is not a substitute for filesystem protection. Restrict and
  back up the SQLite state directory according to the owner's policy.
- Local citations identify current files and their review status. An unreviewed
  guide or extracted TDS text is not an approved technical claim.
- NCC/ABCB literature lookup does not establish compliance or project
  suitability.
- V1 Alpha package checks must continue to prove that the manager, Neo, Oracle,
  and their owner state are absent.

## Overnight local agent regression

Use only the installed local `llama3.2:latest` model. This is an agent
regression, not a model comparison: there are 500 fixed synthetic cases per
assistant (Neo and Oracle), repeated deterministically from 12 scenarios.
There is at most one generation per case; Matrix receives deterministic tests
and no model calls. No customer/owner history, generated paraphrases, LLM
critic, hosted model, or downloads are used. Findings are for human review.
Repeated runs are repeatability checks, not unique-scenario coverage. Focused
contracts require Neo's requested single question and application-first
clarification for unresolved batt purchases; Oracle's product-selection check
distinguishes neutral product mentions from recommendations, and citation
checks reject malformed source markers as well as out-of-range references.

Start with one calibration case for each assistant. The runner checks Windows
CPU and memory and pauses for recovery before the next inference. It blocks
inference below 4 GiB available RAM. Do not switch to another model if Llama is
missing or resource-blocked:

```powershell
python scripts\local_agent_overnight_eval.py --agent pilot --run-id neo-oracle-llama32-pilot-v1 --batch-size 1
```

Continue in small, resumable batches. Run one command at a time and allow the
runner to finish its resource checks; do not use `--agent all` for an
unattended 1,000-case run. The maximum batch is ten cases, inference is
serial with two Ollama threads, and there is a one-minute cooldown between
batches. The default batch size is five. For direct per-agent commands, wait
one minute between invocations and check the Operations tab or local resource
sample before proceeding. If a model call fails, the batch stops and the
partial trace is kept. Resume a pairing with the same run ID and model:

```powershell
python scripts\local_agent_overnight_eval.py --agent neo --run-id neo-oracle-llama32-v1 --model llama3.2:latest --batch-size 5
Start-Sleep -Seconds 60
python scripts\local_agent_overnight_eval.py --agent oracle --run-id neo-oracle-llama32-v1 --model llama3.2:latest --batch-size 5
```

Matrix receives deterministic authorization, loopback, handoff, privacy, and
operations checks only; no chat inference is started:

```powershell
python scripts\local_agent_overnight_eval.py --agent matrix --run-id neo-oracle-llama32-v1
```

Per-stratum `manifest.json`, `sessions.jsonl`, and `report.json`, resource
samples, progress state, and the aggregate report are written under ignored
`data/local/evaluations/other-agents-overnight/<run-id>/`. Keep pilot and main
run IDs separate so calibration does not count toward the 1,000 cases. Keep
local traces out of commits. The aggregate distinguishes completed, failed,
and blocked cases and never presents a partial run as complete.
