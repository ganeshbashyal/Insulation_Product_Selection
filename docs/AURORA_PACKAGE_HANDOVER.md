# Complete Aurora developer handover

## PR #26 and the recent work are cumulative

[PR #26, Aurora](https://github.com/ganeshbashyal/Insulation_Product_Selection/pull/26)
was merged into `main` on 2 October 2026. Its original head is `8b87fea`;
the merge commit is `c50f162`. Those two commits have identical file trees.
The recent work is commit `0b8d72c` on
`ganeshbashyal-development-deep-dive`, whose parent is `8b87fea`.

The branch therefore contains the original PR #26 code **plus** the recent
changes. It is not a partial replacement or a separate code package.
The branch does not contain the merge commit itself; that does not mean its
code is missing. Do not cherry-pick PR #26 again or reset this branch to main.
The follow-up PR brings the cumulative changes into main; it is not an
automatic merge. Until that PR is merged, main alone is not the latest version.

The verified delta from PR #26's merged tree to `0b8d72c` is 116 added/modified
paths, with no deleted paths. Some existing behavior was intentionally changed;
file retention is not a claim that every historical behavior remains unchanged.

## What "complete package" includes

| Layer | Location and boundary |
| --- | --- |
| Code, canonical metadata, tests and documentation | Git branch; includes PR #26 and the recent knowledge/review/export work |
| Private authoring inputs and review state | Existing checkout's ignored libraries and `data\local`; backed up separately |
| Desktop archive and original documents | `C:\Users\ganes\Desktop\Cache\AuroraKnowledge` and retained cache source locations; never upload to GitHub |
| Live enquiry/session/audit state and operator credentials | Original checkout; deliberately separate from authoring/archive snapshots and GitHub |
| Public serving distribution | Smaller allowlisted output from `scripts\package_runtime.py`; requires an explicitly activated reviewed release, not private drafts |

Pushing code does not transfer the private documents, extracted text, generated
packs, local databases, model replies or credentials. A fresh Git checkout alone
cannot recreate the current private research workspace. Collection remains
frozen; do not redownload documents as a substitute for restoring local data.

## Verified local retention

On 5 October 2026, deterministic reconciliation checked:

- All 283 canonical families, 414 distinct SKU rows and 283 retained family
  packs, with the current authoring preview unchanged.
- 130 unique document hashes across 235 cache locations; all 738 register rows
  and all 271 supplied workbook rows remain represented.
- Original document hashes, extraction hashes, compiled-register hash and
  retained-pack hashes; no source binding or technical approval was changed.
- A new 1,107-file authoring snapshot and a 6,942-file managed Desktop archive
  snapshot, plus deduplicated source blobs and a 235-location receipt.
- Isolated authoring and Desktop archive restores with matching checksums.
  The restored authoring preview and exact family/SKU records match.
  All six reviewer/account/history tables match the authoring snapshot;
  sessions and active publication are intentionally cleared by restore.

The previous 6,940-file Desktop snapshot was also verified. No previous files
were removed or changed; the two additional files are the Markdown and JSON
source-review queue exports.

Local Llama reviewed the reconciliation in two bounded requests. Its incorrect
Git ancestry assertions were rejected, not published as evidence. Git tree
comparisons and checksums, not model prose, establish these retention results.

The local handover directory contains `reconciliation.json`,
`authoring\manifest.json`, `desktop-archive\backup-manifest.json`,
`source-locations.json`, `source-blobs`, and isolated restore results.
Its exact owner-specific path is provided in the local session handoff, not as
an artifact to upload. Keep this directory and the original worktree private.

## Continue in VS Code on this machine

**Preferred:** open the existing Copilot worktree folder in VS Code. It already
contains the ignored authoring inputs, account database, operator key and live
runtime state. Opening a folder does not require changing branches or restoring
anything. Do not archive/delete that worktree while it remains the working copy.

For another checkout, fetch the latest branch without overwriting local edits:

```powershell
git fetch origin
git switch ganeshbashyal-development-deep-dive
git pull --ff-only
```

Stop if Git reports local changes or divergent history; do not force/reset.
If the branch does not exist locally, use
`git switch --track origin/ganeshbashyal-development-deep-dive`.
Keep the existing Desktop cache available.

### Private authoring restore into a new staging directory

Use the existing restore tool, setting these two paths to private locations.
The destination must not already exist:

```powershell
$Snapshot = 'C:\AuroraPrivate\HANDOVER\authoring'
$Staging = 'C:\AuroraPrivate\NEW-authoring-restore'
python scripts\authoring_backup.py restore-preview --source $Snapshot --target $Staging
python scripts\authoring_backup.py restore --source $Snapshot --target $Staging --confirm
```

`restore-preview` checks the manifest before writes. Actual restore checks
checksums and SQLite integrity, clears research sessions and holds publication.
It does not copy executable code or customer/runtime databases. For a new clean
code checkout, inspect and overlay only the restored authoring libraries and
receipts enumerated by `authoring_backup.py`; do not overwrite another working
checkout, its live databases or user edits. Preserve the staging snapshot.

**Path limit:** the restored JSON receipts/registers retain their original
absolute cache paths. Same-machine use with the original Desktop cache was
validated; moving the cache to another drive/machine was not. An alternate-cache
restore needs a separately reviewed pointer/register rebind, including cached
source locations and extraction paths. Do not rewrite content-addressed build
manifests to pretend migration succeeded. A byte-perfect archive restore alone
does not certify working links at a new location.

Keep live sessions, interactions, audit/rate-limit stores and the operator key
in the original checkout unless separately migrating them. The authoring backup
does contain research accounts/history: it is sensitive despite excluding
customer enquiries. Use `scripts\runtime_backup.py` for a separate runtime
backup/restore after stopping the serving process, and transfer credentials
privately. Never commit any of these files.

## Acceptance and remaining boundaries

The code baseline passed 692 tests with 13 skipped before its commit, plus fresh
isolated-serving and Edge-export checks. Handover acceptance additionally passed
71 targeted authoring/archive/retention/release tests and the real-data restore
checks above. Skipped tests are not described as passed.

This handover does not approve source identity, regional/variant applicability,
product claims or suitability. The human review queue remains open.
WooCommerce hosting/TLS and real deployment remain deferred; there is no native
WordPress plugin or cart/order integration.

See [the developer handbook](DEVELOPER_HANDBOOK.md),
[the knowledge workflow](KNOWLEDGE_WORKFLOW.md) and
[the deployment runbook](LOCAL_DEPLOYMENT.md) for their respective operations.
