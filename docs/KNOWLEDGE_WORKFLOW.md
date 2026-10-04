# Knowledge workflow

Product Research and the offline CLI share `KnowledgeService.family`.
The dossier preserves raw guides, research, tables, unknown fields and origins.
Literal alternatives remain visible; neither duplicate copies nor historical
`ok`/approved headings prove a current claim. Lost originals remain
`legacy_supplied_original_unavailable`, not discarded knowledge.

## Fresh Desktop TDS build

`scripts\fresh_tds_build.py` orchestrates existing download URL handling, full-page
PDF extraction and local Ollama access. The workbook is read-only; all sheets are
read. Explicit family IDs or unique exact family names associate rows; fuzzy
matches never silently create identity. Displayed/hyperlink conflicts are held.
Simple local cell references are resolved as candidate values, not evaluated
Excel formulas. Existing-page links are not silently used as additional TDS.

The managed archive is `C:\Users\ganes\Desktop\Cache\AuroraKnowledge`:
`originals` contains immutable content-hash PDFs/DOCX, `extraction` persists all
page/paragraph text, and `builds` holds original workbook, input manifest,
download/model receipts and versioned private family packs. Existing Desktop
cache/worktree documents remain untouched. Identical originals are deduplicated;
all family associations survive. Unknown hash-named files stay unassigned.

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' preview --workbook 'D:\Aurora\missing_tds_products.xlsx'
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' start --workbook 'D:\Aurora\missing_tds_products.xlsx' --confirm EXACT_BUILD_ID
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' download EXACT_BUILD_ID --family FAMILY_ID --limit 10
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' extract EXACT_BUILD_ID --family FAMILY_ID
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' model EXACT_BUILD_ID --family FAMILY_ID --limit 5
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' status EXACT_BUILD_ID
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' packs EXACT_BUILD_ID --family FAMILY_ID
```

The importer also accepts a progress-table sheet with `Family` values ending in
an exact `(FAMILY_ID)` and a `TDS link` column. Unknown IDs and displayed-link /
hyperlink disagreements remain held; progress states are never approvals.
For an updated workbook, pass `--extend-from PREVIOUS_BUILD_ID` to both `preview`
and `start`. The new immutable build retains previous archived documents and
their family bindings, matching download receipts, model history and task splits.
Existing originals and older drafts are not overwritten. Stop the previous
writer before starting the additive build; then download new links and extract
their documents before resuming the serial family queue on the new build ID.

Only `download` contacts supplied public HTTPS URLs. Cross-host redirects are
held for review; private-address targets, HTML masquerading as documents,
oversized responses and timeouts fail explicitly. Failed receipts are retained;
one additional attempt requires explicit `--retry` on download/model commands.
Do not repeatedly retry bad URLs, missing mappings or unsupported documents.

### Local gap reconciliation

`scripts\audit_family_gaps.py` reconciles remaining completion gaps against the
current supplied workbook, download receipts and checksummed cached extractions.
It asks installed `llama3.1:8b` on literal-loopback Ollama to review two families
per request. It never downloads documents or models, changes family bindings,
approves claims or replaces family packs. Failed supplied links are distinguished
from absent links; keyword-ranked cached matches remain advisory, not evidence
of applicability. Raw local review receipts are saved and reused for identical
inputs; malformed or truncated reviews stop explicitly.

```powershell
python scripts\audit_family_gaps.py EXACT_BUILD_ID --cache 'C:\Users\ganes\Desktop\Cache' --output 'C:\Users\ganes\Desktop\Cache\AuroraKnowledge\reports\family-gap-audit'
```

Read `audit.md` for advisory findings and `audit.json` for exact supplied rows,
download errors, extraction gaps, cached candidates and held workbook rows.

### Frozen collection and the TDS register

Once collection is frozen, compile the existing cache rather than retrying
blocked downloads. No document is moved/deleted or claim approved:

```powershell
python scripts\review_unassigned_tds.py EXACT_BUILD_ID --cache 'C:\Users\ganes\Desktop\Cache'
python scripts\compile_tds_register.py EXACT_BUILD_ID --cache 'C:\Users\ganes\Desktop\Cache'
```

The first command uses installed local Llama serially for only unassigned
document suggestions, reusing exact-input receipts. Suggestions remain advisory.
The second streams PDF/DOCX hashes across the selected cache, excluding generated
managed build/report/model folders and directory links. It retains every actual
location, hash duplicate, supplied URL, failed/held row and unmatched identity.
Versioned private `reports\tds-register-*\register.md`, `.csv` and `.json` outputs
preserve filenames and full Windows paths; CSV cells are formula-neutralised.
`data\local\tds_register.json` activates only the complete checked snapshot.

`family_completion.md` itself includes per-family TDS URLs, clickable local files
and copyable Windows paths, with same-file links from the summary. Refreshing the
report preserves these details. Local file-link launching depends on the viewer;
the displayed Windows path remains usable independently.

Private `KnowledgeService.family` and internal `SalesBriefBuilder` evidence read
the compiled snapshot, source excerpts/locators and retained Llama findings.
Changed files/extractions are marked stale; pointer tampering fails explicitly.
This is provenance/context integration, **not** a recommendation/ranking change
or public release. Origin, edition/region and logo authenticity remain unverified
unless independently supported. A logo alone does not authenticate a document.
Complete extracted text and original family packs stay referenced and retained.

Local Llama supplied bounded inventory/reconciliation code and semantic findings;
minimal deterministic orchestration/export glue was needed after invalid local
code proposals. `local_tds_code_task.py` preserves bounded proposals without
automatically applying them. No remote inference or document discovery is used.

### Source review queue and readable export

Product Research now shows a per-family source/variant queue, including retained
local Llama findings and proposed unattributed-document matches. Reviewers can
record `accepted`, `needs_information` or `rejected` with a meaningful rationale.
These are source identity/provenance decisions, **not** automatic family bindings,
technical claim approvals or publication. Source hashes and queue IDs must still
match; existing reviewer authentication, same-origin CSRF and optimistic revision
checks apply. Accessory/source-less families keep a standalone-TDS need question.

```powershell
python scripts\export_source_review_queue.py
```

This writes `source_review_queue.md` and `.json` alongside the current private TDS
register, without models/downloads. Refresh it after saving identity decisions.

**Export readable brief** fetches the complete stored readable family pack, not a
JSON-style rendering of summary fields. It exposes a read-only full-text panel
and Copy button before attempting the attached-link download. If the app viewer
blocks downloads, select/copy the panel text into a local text file. Clipboard
failures and missing stored packs are explicit; JSON export stays available.
Locking/signing out or changing family clears the private export panel. Browser
validation uses installed Edge with local synthetic data and no external pages.

`extract` reuses `checked_pages` for every PDF page, not a 12-page excerpt.
Blank/scanned/unreadable pages remain gaps; no OCR is silently invented.
DOCX retains paragraph and table-cell text with paragraph locators, not rendered
page numbers; image/header/footer/embedded-object extraction is not asserted.
Adjacent DOCX paragraphs are grouped into bounded model chunks with paragraph
ranges, avoiding one model request for every short table cell or paragraph.
The complete original extraction remains retained independently of grouping.
PDF tables retain parser text order, not a guarantee of correct row alignment.
No extraction or model success approves a family or exact SKU.

`model` runs a synthetic pilot first, then sequential bounded 1,000-character
chunks on installed `llama3.1:8b`, with two CPU threads, bounded context/output,
180-second request timeout and explicit unloading. Replies contain only
topic-labelled selections of numbered source lines. The script copies the exact
selected lines, preventing the model from silently normalising OCR text. This is
source-grounded candidate extraction, not semantic correctness validation.
Initial quote-writing pilots were rejected for exceeding the candidate limit
and altering OCR spacing. Those failure receipts are preserved. The revised
schema permits three bounded line selections, not model-written product facts.
Ollama structured JSON Schema constrains required line/topic fields; local
validators additionally reject out-of-range spans and unsupported values.
Generation also constrains the span's end relative to its start, not merely
the overall document line count. Twice-failed tasks may be explicitly narrowed
with `narrow-failed BUILD_ID --family FAMILY_ID`; this retains the failed parent
receipts and splits its complete text into two bounded child tasks. It is not
an automatic retry or deletion of failed data. Already narrowed failures stop
for inspection instead of recursively splitting indefinitely.
Pause if the PC becomes unresponsive. No model downloads, remote AI fallback,
silent regex completion or automatic retry occurs.
Input/prompt/options hashes allow resumable model batches without a Copilot turn
per family. Full cached text remains intact independently of model failures.
Validated document-chunk model receipts can be reused across build versions for
identical source/parser/prompt/model/options inputs.

After starting a confirmed build, a bounded orchestration command runs downloads,
extraction, local model tasks and pack generation without Copilot interaction:

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' run EXACT_BUILD_ID --family FAMILY_ID --download-limit 10 --model-limit 5
```

It resumes saved progress, stops model processing on the first failed task and
still writes explicitly incomplete private packs. A model failure returns a
nonzero exit status. Run `status` and inspect the receipt before an explicit
retry; do not hide failures in an unattended retry loop.

**Owner-directed family-by-family processing:** download/extract/model/packs/run
now require `--family`. The broad initial archive/download/extraction work is
retained. Individual commands do not advance families. Review a family's
old/new coverage, pending chunks, conflicts, exact variant applicability and
source gaps before explicitly selecting the next family. Shared documents reuse
hash-bound extraction/model results; a shared PDF is not shared claim approval.
Each family's private pack pointer is independent, so generating the next family
does not hide or replace a previously reviewed family's draft.

Process families alphabetically by **manufacturer, then family name**, with ID
as a stable tie-breaker. The first current family is `ACOUSTICA_ACCESSORY`.
Generate/refresh the completion report without making a model call:

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' report EXACT_BUILD_ID
```

Reports are saved as `AuroraKnowledge\reports\completion.md`, `completion.csv`
and `completion.json`, with hash-versioned JSON history. Each family shows source
and extraction counts, validated/pending/failed current-schema model chunks,
verified draft existence/freshness, held links and download failures.
`needs_source`/`draft_with_source_gap` are not completed processing.
`draft_ready_for_human_review` means processing-ready, never public approval.
Packs generated before later model results need refreshing before being labelled
ready. Overall status retains failed older-schema pilot receipts independently.
An ignored local `data\local\family_completion.md` copy supports opening the report
in the app's editor; Desktop reports remain the primary progress artifacts.

A resumable **single-family** worker can finish the chosen family's pending
chunks without Copilot interaction. It uses sequential requests and refreshes
the private pack and completion reports after every five tasks. The call budget
is a hard ceiling; failures stop the worker without retries. It never advances
to another family or publishes claims:

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' work-family EXACT_BUILD_ID --family FAMILY_ID --max-calls 20
```

Inspect the saved report before increasing the budget or selecting the next
family. Reports are generated artifacts; edits to them are replaced on refresh.

For owner-directed autonomous alphabetical processing, the **serial queue**
explicitly advances only after the current family finishes its processing and
passes retained-dossier/full-text verification. It skips already processing-ready
drafts, preserves missing-source drafts with gaps, and stops on the first model/
retention error. It is not parallel processing or human technical approval:

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' work-alphabetical EXACT_BUILD_ID --max-families 1 --max-calls 20
```

Increase `--max-families` only to authorise additional sequential families.
The **total** model-call budget applies across the queue, not per family.
The current saved report determines resume order. No web downloads, fuzzy
family mapping, approvals or deployment run inside this queue.

For low-credit overnight operation, the local controller chains **five-family
batches** without a Copilot turn between batches:

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' work-overnight EXACT_BUILD_ID --max-batches 60 --max-calls 10000
```

Both ceilings apply to the entire run. Each batch refreshes the saved reports,
reuses matching validated model results and runs sequentially. The controller
stops on the first error without retrying, or when processing/budgets are
exhausted. Verified drafts with no extractable text remain explicit source gaps,
not an endlessly reprocessed family. Thirty-minute Copilot check-ins monitor
the single controller; they do not launch parallel workers or gate each batch.
Final retention verification and backup remain required before completion.
Generation schemas exclude empty-only line spans without removing source text
or changing line numbers. Pending/rejected blank-containing tasks receive a new
schema-based identity; earlier failures remain in their original receipts.
Previously validated exact-input selections are checked and reused.

`packs` includes all existing retained dossiers plus fresh source inventories and
quoted candidates. It reports pending model chunks, held rows, download failures
and unassigned originals; incomplete processing is never labelled complete.
Original guides, research and approvals are not rewritten. Generated packs are
not recursively ingested or public bot retrieval inputs. Product Research's
Both JSON and Markdown also include complete supported extracted source text;
the up-to-three model selections per chunk are suggestions, not an exhaustive
replacement. Source-to-family applicability remains pending human review even
when a workbook name or existing source hash matches. A family-level match
cannot approve all variants/SKUs.
Product Research's
**Stored private family draft pack / Read stored draft** shows the readable
pack through named-reader access; sign-out clears it. The older download-button
repair remains separate.

`training_candidates` exports only rights/review eligibility metadata when
permissions are unknown, not copyrighted document text as training-ready
targets. This build prepares a retrieval cache; it does not fine-tune models.
Customer data, logins and credentials are excluded.

The worktree authoring snapshot does **not** protect the external Desktop archive.
It includes the private cache pointer and local progress copy only; restored
pointers require cache availability and operator review, not automatic activation.
Use a new independent private backup directory:

```powershell
python scripts\fresh_tds_build.py --cache 'C:\Users\ganes\Desktop\Cache' backup --target C:\AuroraPrivate\desktop-cache-NEW --confirm
```

Each copied file is checksum-verified and `backup-manifest.json` records the
inventory. For recovery, verify all declared checksums before copying to a
**new** cache location; do not overwrite active originals. Restore paths in
receipts refer to the original cache and require operator review/rebinding
before processing. A Desktop backup is still local, not offsite disaster recovery.

### Existing-input-only pack commands

The alternative deterministic worktree pack builder never downloads or calls a
model unless explicitly requested. Preview/write confirmation applies to all
families; private JSON retains full original dossier data and Markdown retains
values, origins, conflicts and historical content. Storage is ignored
`data\local\family_knowledge_drafts`; versioned checksummed batches are included
in authoring backups, but excluded from authoring-input discovery.

```powershell
python scripts\knowledge_workflow.py draft-preview
python scripts\knowledge_workflow.py draft-write --confirm EXACT_PREVIEW_ID
python scripts\knowledge_workflow.py draft-family FAMILY_ID
python scripts\knowledge_workflow.py draft-annotate EXACT_BATCH_ID --limit 5
python scripts\knowledge_workflow.py draft-status EXACT_BATCH_ID
```

`draft-annotate` is optional excerpt-based organisation classification only;
it does not replace the full-document Desktop extraction pipeline. Annotation
status and pending/failed occurrences are distinct from lossless pack coverage.
When a Desktop pack is activated for private inspection, `draft-family` reads
it instead; no public serving-release pointer is changed.

## Local commands

Run one command at a time from this C-drive worktree:

```powershell
python scripts\knowledge_workflow.py overview
python scripts\knowledge_workflow.py families --query batt
python scripts\knowledge_workflow.py family FAMILY_ID
python scripts\knowledge_workflow.py validation
```

Use the `family_id` returned by `families`. Optional `--root` precedes the
command. The CLI trusts local OS access and prints private authoring data.
Read commands do not sign in, create a research database, call models/network
services, approve claims, publish or rewrite retained inputs. Source staging is
an explicit additional command:

```powershell
python scripts\knowledge_workflow.py source-preview data\source_manifest.json
python scripts\knowledge_workflow.py source-stage data\source_manifest.json --confirm EXACT_PREVIEW_ID
```

The same source preview/stage functions are available in the named-reviewer
family GUI. The manifest declares existing PDF paths, exact family IDs, roles
and optional page-quoted typed candidates; see `local_intake.checked_candidates`
for its enforced shape. Staging is idempotent for an identical immutable receipt
and cannot approve a claim or mutate originals. Both data-library and
`evidence\raw` PDFs are supported; URLs are not fetched.

Review and publication commands call the same application methods as the GUI.
They prompt interactively for a named account's password (never a shell argument
or printed token), enforce reviewer/publisher roles and close the login session
after the operation:

```powershell
python scripts\knowledge_workflow.py review FAMILY_ID data\review.json --username REVIEWER --expected 0
python scripts\knowledge_workflow.py retained-review FAMILY_ID data\retained-review.json --username REVIEWER --expected 0
python scripts\knowledge_workflow.py publication-preview --username PUBLISHER --scoped
python scripts\knowledge_workflow.py publish PROPOSAL_ID --username PUBLISHER --confirm PROPOSAL_ID
```

Review JSON is the existing typed claim/SKU payload; retained review JSON contains
`dossier_id`, `group`, zero-based `position`, `decision` and `rationale`.
`--expected` is the current target revision, not the global history count.
Approval is a review draft, not publication. Publishing still requires a current
unblocked preview and exact proposal confirmation. Release build/activation and
site-scoped exports retain the existing separate explicit adapters described in
the deployment runbook; no command runs a hidden rebuild/model/network chain.

## Local Llama development

Llama drafts use `scripts\run_local_maintenance.py` with explicit bounded read
and write paths. `propose` stages, `verify` checks, and `apply --confirm TASK_ID`
is a separate decision after semantic review. Code verification requires
`--approve-tests`; tests execute locally and are not a sandbox. Generation uses
two CPU threads, bounded context/output and no download/cloud fallback.

The CLI dispatch was drafted by installed `llama3.1:8b`, corrected through local
feedback and checked before application. This document adapts a local Llama
draft; its invalid combined command was corrected, not blindly applied.

## Remaining work

### Private retention

Authoring backup is separate from customer/runtime backup. It covers knowledge,
source libraries, raw workbooks, reports, intake/commercial/competitor receipts,
and the authoring review database. Treat the destination as private: it contains
reviewer accounts. Use a **new directory outside the checkout**.

```powershell
python scripts\authoring_backup.py backup --target C:\AuroraPrivate\snapshot-NEW --confirm
python scripts\authoring_backup.py restore-preview --source C:\AuroraPrivate\snapshot-NEW --target C:\AuroraPrivate\restore-NEW
python scripts\authoring_backup.py restore --source C:\AuroraPrivate\snapshot-NEW --target C:\AuroraPrivate\restore-NEW --confirm
```

Pause authoring writes first. File checksums are checked before restore writes;
SQLite uses the consistent backup API. Existing directories are never replaced.
Restored logins are cleared and active publication is held; revisions, account
identities, proposal history and withdrawal records are retained. Review before
reactivation. This is not a runnable application package or an independent/offsite
disaster-recovery copy. A verified local snapshot of 1,104 files was made in this
session's private artifacts; no D-drive changes occurred.

### Current read and preview tools

```powershell
python scripts\knowledge_function_map.py
python -m data_health --profile authoring
python scripts\validate_catalogue.py --profile authoring
python scripts\build_missing_tds_report.py
python scripts\generate_family_literature.py --dry-run
python scripts\review_local_sources.py
```

The callable inventory includes syntactic references, decorators and notebook
actions. It labels unresolved usage for review, never as proof of dead code.
Legacy validation remains `--profile legacy`. Report and source-audit commands
default to previews; `--confirm-write` is required for intentional writes.
Missing-source reports include families without research and staged intake
associations; manual fields, formulas and historical requests survive rebuilds.
Ambiguous IDs or multiple manual sheets block workbook replacement.
Audit updates retain immutable receipts in `data\local\source_reviews`.
Literature is an **unreviewed draft**, uses explicit-ID research and hashes all
commercial-row values, not just row counts. Writes require `--confirm-draft-write`.

### Retained review and scoped publication

The family GUI offers named review of each exact retained occurrence, bound to
the dossier hash. `retained_confirmed`, `needs_information` and `rejected`
revisions retain the literal value and its origin. This private attestation is
**not** public approval, a manufacturer citation or SKU eligibility. Lost-original
information can therefore be reviewed and retained without fake PDF references.
Public technical claims still use the existing quoted-source claim/SKU review,
publisher preview and explicit activation.

Publishers may opt in on a new preview to `source_scoped_v1`. Explicit citation
paths bind claims; exact SKU decisions bind their own citation and applicable
claims. A changed PDF or unauthorised reviewer holds only those bound additions.
Non-PDF changes, unknown/missing bindings and historical publications retain the
global fail-closed hold. The first implementation intentionally does **not**
infer field-level locality for JSON, workbook or schema changes. Partial authoring
holds are visible and block new release builds; existing serving releases remain
immutable and need separate operator withdrawal/redeployment.

### Maintained function responsibilities

`scripts\knowledge_function_map.py` generates function-level line references,
known workflow ownership/gates, tests, decorators, capability signals and
notebook entrypoints directly from current source. Name matches are syntactic,
not resolved call graphs. Unclassified and apparently uncalled functions remain
`review_required`; absence of a Python import is not deletion authority.

| Primary function/adapter | Inputs | Outputs / gate |
| --- | --- | --- |
| `load_families`, `load_research` | canonical JSON, explicit family IDs | one shared identity/read policy; duplicates error |
| `ResearchIndex.detail`, `KnowledgeService.family` | identity, guide, research, sources, commercial rows, reviews | lossless private dossier; no read writes |
| `checked_pages` | path + live byte hash | full-page cache; source changes require refresh |
| `source_preview`, `source_stage` | owner manifest + exact preview ID | ignored intake receipt; candidate-only |
| `review_retained` | dossier ID + occurrence + rationale | named immutable attestation; never public claims |
| `validate_review`, `publication_preview`, `publish` | scoped claim/SKU citation + reviewer + publisher | draft, preview, atomic activation; no automatic selection |
| `retain_review` | unreviewed extraction audit | immutable source-review receipts + compatibility pointer |
| `authoring_backup.backup/restore` | allowlisted authoring libraries/history | private checksummed snapshot; new-directory restore |
| report / enrichment / literature / cards | canonical IDs + retained research | preview-first drafts; manual boundaries retained |
| `ReleaseLibrary`, `release_exports` | reviewed publication + site visibility | immutable public runtime/export boundary |

Legacy downloading, filename matching, seeded range data, raw SQLite and baseline
voice builders are labelled in the inventory, not automatically executed or
deleted. Existing compatibility validators retain explicit legacy profiles.
No D-drive synchronisation or cloud/model downloads occur.

The incremental streamlining implementation preserves legacy utilities as
explicitly classified adapters/reference code. Replacing every historical
writer or deleting apparently unused functions is not part of this change.
Real supplier completeness, human claim approvals, refreshed commercial inputs
and production-site installation remain owner-gated work, not software-generated
completion claims.
