# Aurora Alpha management

This is the owner/operator playbook for the local Aurora Alpha **serving-only**
runtime. It complements the detailed [local deployment runbook](LOCAL_DEPLOYMENT.md)
and the [developer handbook](DEVELOPER_HANDBOOK.md). It is not a product-claim
approval, customer-data policy beyond the retention rules below, or proof of a
public storefront deployment.

## Current local instance

The most recently verified local Alpha package is:

| Item | Current local value |
| --- | --- |
| Runtime profile | Serving-only; one Uvicorn worker |
| Package | `data\local\distribution\aurora-chat-fix-20261006` |
| Knowledge release | `1134bcd195cba93072f0f7190219b0a572d6c7dc899ac27cbbbaf11c5eae72f6` |
| Listener | `127.0.0.1:8011` only |
| Chat surface | `/widget` and `/widget.js`; development `/chat` intentionally returns 404 |
| Site config | Package-local synthetic `local` demo; origin limited to `http://127.0.0.1:8011` |
| State | `%LOCALAPPDATA%\Aurora\staging\state-1134bcd1` |

These are local staging values, not production credentials or a reusable store
configuration. Recheck the package manifest and active release before operating
after any rebuild. Never replace the existing site config or state directory
merely to follow an example. The package is ignored local output; it is not
included in Git or the Alpha release source.

## Roles and boundaries

Aurora Alpha is a local, deterministic-first customer-enquiry runtime over one
explicitly activated immutable knowledge release. It can collect a project
brief, present local responses and save a consented enquiry for human review.
It does not automatically select/approve a product, approve technical claims,
book callbacks, send customer messages, or connect to stock, prices, carts,
orders, or CRM.

Serving-only mode disables development `/chat`, research/admin authoring routes,
model phrasing, and Oracle/Neo/Matrix. The public widget uses a site-scoped,
short-lived conversation capability; it is not customer identity authentication.
The local demo site is synthetic. Do not enter real customer or personal
information in it.

## Start, inspect, and stop

The companion [Aurora Alpha process notebook](../notebooks/aurora_alpha_management.ipynb)
is the recommended local control panel. Run All is read-only. To start, stop, or
restart, explicitly enable process actions in its configuration cell, then run
only the requested cell and confirm the displayed release or exact listener PID.
The notebook manages only this Aurora process; it does not control Ollama, Neo,
Oracle, or other local services.

For manual inspection from PowerShell:

```powershell
$Port = 8011
Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, OwningProcess
Invoke-RestMethod http://127.0.0.1:8011/health/live
Invoke-RestMethod http://127.0.0.1:8011/health/ready
```

The only acceptable deployment listener for this local demonstration is
`127.0.0.1`. Do not bind to `0.0.0.0`, a LAN address, or an externally reachable
interface. Readiness must report `serving_only: true` and the expected full
release ID. The following GET checks do not create a chat session:

```powershell
Invoke-WebRequest 'http://127.0.0.1:8011/widget.js'
Invoke-WebRequest 'http://127.0.0.1:8011/widget?site_id=local&parent_origin=http%3A%2F%2F127.0.0.1%3A8011'
```

Opening `/widget` in a browser starts a local demo conversation and creates a
transient session/token; the widget/API is designed to create sessions on use.
`/chat` returning 404 is expected for the serving-only runtime, not a health
failure. Stop only the verified Aurora PID. Never use broad process-name killing
or terminate an unidentified listener.

If the server does not start, check port ownership and the package's local log
file when launched by the notebook:
`%LOCALAPPDATA%\Aurora\staging\logs\aurora-alpha-managed.log`. Treat logs as
private operational data. Do not paste customer text, tokens, configuration
values, or credentials into tickets or shared outputs.

## Package and release lifecycle

The package and knowledge release are separate:

1. Review source identity, exact family/variant scope, citations, held facts,
   publication state, and withdrawal requirements in the authoring tools. A
   generated or model-reviewed draft is not approval.
2. Preview a release locally with `python scripts\build_knowledge_release.py`.
   Review its full release ID, family/claim counts, eligibility, site visibility,
   and expected current release.
3. Activate only after human review, with the exact candidate ID and the exact
   expected active ID:

   ```powershell
   python scripts\build_knowledge_release.py --activate EXACT_CANDIDATE_RELEASE_ID --confirm EXACT_CANDIDATE_RELEASE_ID --expected-active EXACT_CURRENT_RELEASE_ID
   ```

   For first activation, use the tool's documented expected-active value for an
   empty active pointer; do not guess it.
4. Build a **new, unique** allowlisted runtime folder from the activated release:

   ```powershell
   python scripts\package_runtime.py --releases data\local\releases --name UNIQUE_PACKAGE_NAME
   ```

   Check `package_manifest.json`, file hashes, exclusions, and the full release
   ID. Copy only an intentionally reviewed site configuration into the package;
   never copy live databases, backups, private documents, or credentials.
5. Stop the old process by its verified PID, point the next process to the new
   package and its release directory, then verify loopback binding, health,
   release ID, widget frame and cross-site/token protections before use.

Activation does not change the release already pinned in a running process.
Restart is required. Preserve prior immutable packages and releases until the
new one is accepted and recoverable. If a fact is withdrawn, activate a
withdrawal-bearing release and restart promptly. Rollback is not a way around
withdrawals: release activation must continue to reject resurrection of revoked
claim IDs. Never edit an immutable release snapshot or `active.json` by hand.

## State, housekeeping, and privacy

The configured Aurora state directory contains separate SQLite stores for
transient sessions, interaction/lead records, audit events, rate limits, and
widget capabilities. Keep the state directory private and writable only by the
service owner. Do not serve it as static content or commit it.

The local runtime automatically runs housekeeping at startup and every 24
hours:

| Data | Active-store retention |
| --- | --- |
| Transient widget sessions | 24 hours after last access |
| Conversation/interaction records and linked reviewer outcomes | 30 days |
| Lead/contact records | 12 calendar months from creation |

Housekeeping reports aggregate deletion counts only. A startup cleanup failure
prevents startup; scheduled errors are logged and retried on the next interval.
Backup archives are not purged by this task and may retain older copies. SQLite
WAL behavior and storage hardware mean database deletion is not secure erasure.
Apply separate access, encryption, and retention controls to backups.

## Back up and restore

Stop the service before backup or restore. Use a new backup directory outside
the state directory; the tool uses SQLite's backup API and verifies checksums
and database integrity:

```powershell
$State = Join-Path $env:LOCALAPPDATA 'Aurora\staging\state-1134bcd1'
$Backup = Join-Path $env:LOCALAPPDATA 'Aurora\backups\NEW_UNIQUE_BACKUP'
python scripts\runtime_backup.py backup --state $State --backup $Backup --confirm-server-stopped
```

The backup includes only existing named runtime databases; it does not include
release withdrawal history, site configs, site credentials, logs, authoring
documents, or model files. Protect and back up those separately under the
appropriate owner-controlled procedure. A backup contains sensitive session
and customer data.

Restore only into a new empty staging state directory, never over live state:

```powershell
$Restored = Join-Path $env:LOCALAPPDATA 'Aurora\staging\restore-NEW_ID'
python scripts\runtime_backup.py restore --state $Restored --backup $Backup --confirm-server-stopped
```

Verify the restore, correct package/release/site configuration, and readiness
before routing any traffic to it. Do not point an active instance at a restore
until an operator has explicitly validated the recovery.

## Routine checks and incident response

- **Before a demonstration:** confirm serving-only readiness, expected release,
  loopback-only binding, synthetic site config, and no real personal/customer
  data in prompts.
- **After a package or release change:** verify its manifest/checksums, explicit
  release pointer, startup log, `/health/ready`, widget frame and expected
  release; confirm `/chat` and authoring routes remain disabled.
- **If health is unavailable:** inspect the exact process/port, package path,
  release directory, site-config validity, state-directory access and private
  logs. Do not kill processes by name, replace state, or expose the port to
  “test” connectivity.
- **If the widget frame is 403:** compare its requested parent origin with the
  site's literal `allowed_origins`. Do not use wildcards or edit the original
  site config as a quick workaround.
- **If the chat reports an unexpected-token/JSON error:** inspect the local
  server log for the underlying 4xx/5xx. A non-JSON internal error is a server
  failure, not a browser JSON syntax issue; verify the current package manifest
  and required runtime modules before rebuilding a new package.
- **If technical information may be wrong or withdrawn:** stop using the
  affected response path, review the exact evidence and publication state,
  create/activate the appropriate withdrawal release, and restart the service.
  Never patch the running release file directly.
- **If customer data or credentials may have been exposed:** stop the service,
  restrict local state/log/backup access, preserve evidence for owner review,
  and rotate affected credentials through their protected procedure. Do not
  include secrets or personal data in this guide.

## Readiness gates before real use

The local loopback rehearsal is not a public deployment. Before customer-facing
use, complete human/source review of served claims, configure real site origins
and protected credentials outside the package, establish a supported TLS/proxy
boundary and operator authentication, test on owner-controlled staging stores,
measure capacity and latency on the target host, and rehearse backup/restore,
withdrawal, restart, and incident procedures. Do not call Alpha production-ready
until these gates are accepted by the owner.
