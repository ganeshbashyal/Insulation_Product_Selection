# Oracle and Matrix local workspaces

## Release boundary

Oracle and Matrix are owner/operator tools for the local workstation. **Oracle
must remain separate from, and must not ship in, the V1 Alpha customer
serving release.** Oracle conversations, notes, tasks, prompt, owner credential,
and endpoints are not customer data and must not be copied into Aurora or Neo.

Matrix and Neo are also local-only management/sales tools. They are excluded
from the V1 Alpha runtime package along with Oracle. The release builder uses
an explicit serving allowlist; do not add `matrix_api.py`, `neo_api.py`,
`neo_assistant.py`, `neo_store.py`, `templates\matrix.html`,
`templates\neo.html`, or any Oracle resource to that allowlist. The package
manifest records the owner-only exclusions. Production and serving-only
processes do not mount these routes.

## Four Matrix workspaces

The local Matrix manager is `/matrix` and has four tabs:

| Tab | Purpose |
| --- | --- |
| Aurora | Local customer-enquiry/demo harness, separate from internal Neo and private Oracle. |
| Neo | Internal local sales copilot with local model selection, product/TDS evidence citations, separate conversation storage, and human-review sales briefs/tasks. |
| Oracle | Link to the passphrase-protected owner assistant, with its own conversations, notes, tasks, and evidence search. |
| Admin | Links to existing knowledge, product research, competitor review, catalogue, sales-brief, and health pages. Existing authentication and review gates still apply. |

Matrix, Neo, and Oracle accept loopback connections only. Neo's conversation
and draft records are in its own `data\local\neo.sqlite3`; Oracle uses a
different private database. Neo retrieves governed local product evidence but
does not retrieve Oracle's owner-provided private pricing snapshots. Neo model
calls use local Ollama only. No tab sends email, changes CRM/customer records,
approves product claims, or activates releases.

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
$env:AURORA_ENV = "development"
$env:AURORA_SERVING_ONLY = "false"
$env:ORACLE_ENABLED = "true"
$env:MATRIX_ENABLED = "true"
$env:AGENT_USE_LLM = "false"
python -m uvicorn web_agent:app --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002/matrix`. The app must bind to loopback; do not
change the host to `0.0.0.0` for these owner/operator interfaces. The Aurora
tab is a local demo harness, not a production/customer endpoint.

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
task before sharing it.

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
