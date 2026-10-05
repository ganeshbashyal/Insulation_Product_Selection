# Local admin rebuild contract

**Local implementation delivered; real-data acceptance is owner-gated.**
Knowledge Validation, all-page local PDF intake with typed owner candidates,
private cited competitor inspection/notes/review/export and versioned commercial
preview/stage/activation now exist. The real refreshed workbook and competitor
library have not been supplied. The current chat, sales briefs and Product Research
remain supported; this contract does not itself approve facts or replace records.
Use deterministic local tools first; installed Ollama annotations are optional.
See [the developer handbook](DEVELOPER_HANDBOOK.md) for current delivery boundaries
and [the local handover](LOCAL_REBUILD_HANDOVER.md) for maintenance-tool instructions.
The [deployment runbook](LOCAL_DEPLOYMENT.md) covers exact input contracts,
site-scoped releases, reviewed export adapters, portable runtime and operations.
No supplier fact, commercial continuity or live site installation is approved
by implementing these tools.

## Knowledge Validation

Add a dedicated `/admin/knowledge` view over the shared family/document index,
reusing named research accounts and existing review/publish permissions.
Include every canonical family, including families without commercial SKUs.

Show independent states, with reasons and source timestamps:

| Dimension | What it establishes |
| --- | --- |
| Identity / canonical guide | Family record and human/generated document ownership |
| Research | Existing successful, failed or missing extraction attempt; not approval |
| TDS/SDS | Held local files, reliable family association and source hash integrity |
| Full-page extraction | Page coverage, read errors, blank/scanned pages and OCR/manual gaps |
| Model audit | Existing staged/accepted model annotation, not human verification |
| Human review | Pending, approved draft, rejected or revoked claims with named history |
| Publication | Active, absent or stale effective snapshot |
| Commercial coverage | Active catalogue version and child-row mapping/conflicts |

Do not use one “complete” badge to imply everything is verified. Generated
literature is a derived draft, not primary evidence. Unknown is not absent.
Filters should expose missing/stale documentation, awaiting owner input,
extraction failures and pending review. Drill down into existing family research,
exact source pages, manual request/workbook fields and immutable reviews rather
than duplicate those records. Refresh starts no downloader or model job.

Acceptance: all families accounted for; no-SKU cases visible; source/hash/OCR
and review/publication states stay distinct; same account boundaries; existing
manual inputs and sources unchanged.

## Competitor Comparison

Add `/admin/competitors` for **locally supplied competitor evidence only**.
No scraping, external search, source fetch, automatic superiority ranking or
winner selection. An empty/pending comparison workspace is valid.

Keep competitor records under stable separate IDs linked to our family IDs,
not inserted as our commercial SKU rows. Preserve original document hashes,
supplier identity, variants and local citations. Use bounded owner-confirmed
ingestion and existing citation contracts, not a parallel approval engine.
Named internal notes and side-by-side JSON/readable exports support review.

Compare exact metric/unit/variant, thickness, material/product/component/system
scope, test standard/context and installation limitations. Flag non-equivalent
ratings and unknown fields explicitly. Product-only Rw is not a wall-system Rw;
thermal R is not acoustic Rw. Do not invent conversions, treat missing values
as zero, infer NCC suitability or call a product better without comparable
evidence and human judgement.

Competitor imports/comparisons do not approve our evidence, unlock SKUs or flow
into public answers. Read access and changes use the existing named-account
roles, with no sales-key shortcut.

Acceptance: citation and untrusted-text handling, empty and missing evidence,
scope/standard/unit conflicts, no web requests, no public/runtime claim leakage.

## New SKU catalogue version

The owner will provide a latest SKU list. **Codes change; families stay the
same.** No file is assumed received, and no sheet/columns or mappings are guessed.

Stage a new version bound to original file bytes/hash, selected sheet and
explicit column mapping. Keep every source row/raw field, including blank and
duplicate codes, inactive/superseded products and ambiguous associations.
Create version-scoped unique row IDs; do not identify continuity using codes
that have changed or reuse legacy active-row deduplication assumptions.

Keep these mapping decisions separate:

1. Canonical family association.
2. Exact variant continuity using manufacturer/MPN/spec/material/dimensions/
   pack/facing or explicit owner-accepted equivalence.
3. Old/new commercial-code crosswalk.
4. Reviewed evidence applicability and eligibility for the new row/version.

Preview additions, changes, retirements, unmatched/conflicting rows, mapping
reasons, family totals, provenance and ambiguities. No first match, shared
generic-name token or fuzzy score silently accepts variant equivalence.
Historical rows/codes and saved enquiry briefs remain unchanged.

Until explicit authorised preview-and-confirm activation, current consumers
use the existing version. Activation is audited and stale-preview protected;
research, knowledge-validation, lookup and eligibility read one active version.
Archived rows stay labelled historical and cannot act as current order rows.

**Old SKU approvals do not automatically transfer.** Family evidence can remain
family evidence where source/scope are valid, but new commercial rows begin
held until exact applicability/continuity is reviewed and published. Maintain
fail-closed source/publication invalidation; the current global baseline may
hold the whole overlay. Do not weaken that boundary merely to avoid a warning,
silently resurrect revoked evidence or infer eligibility from family identity.

Acceptance: all-new codes, duplicate/blank identifiers, different variants in
one family, inactive/retired rows, ambiguous mapping, exact source preservation,
staged non-impact, stale activation, aligned consumers, held new eligibility,
and unchanged historical enquiry snapshots.

## Local task sequence

Inventory and shared framework-independent readers precede these features.
Knowledge Validation can then reuse the existing records. Competitor support
needs bounded local-source ingestion and isolated records. Catalogue versioning
needs deterministic staging/activation, migration tests and the owner's file.
Read-only scaffolding need not wait for the upload; real import does.

Split each feature into small source-grounded tasks and synthetic tests.
The maintenance runner may propose allowlisted feature code; it cannot write
protected source/data/config paths or approve evidence. Implement a separately
reviewed deterministic importer/migration rather than widening model write
permissions to overwrite catalogue state.

Document final implemented behaviour, limitations, schemas, provenance,
permissions, commands and tests in the eventual comprehensive developer
handbook. Keep this contract labelled planned until acceptance. No automatic
server restart, external activation, commit or push is authorised.
# Delivery update

The `/admin/knowledge` and `/admin/competitors` views use existing named accounts.
Local intake and new-code version staging/activation use explicit owner manifests
and confirmations; no actual supplier-data approvals or real catalogue activation
were performed. See [the deployment runbook](LOCAL_DEPLOYMENT.md).
See the [developer handbook](DEVELOPER_HANDBOOK.md) for current boundaries.
A dedicated `/admin/catalogue` page now exists for staging/previewing/activating
catalogue versions (role-gated: readers can list, reviewers can preview/stage,
publishers can activate), reusing the existing named research accounts.
The server regenerates a preview from its unchanged local source before staging;
client payloads cannot transfer approval or bypass HOLD/blocker defaults.
Recorded-version corruption is an explicit error, not an empty listing.
Activation requires the full version ID and the explicitly supplied expected
active ID (including null for the baseline). It does not publish claims;
running serving releases remain pinned until explicitly rebuilt/restarted.
Filesystem modification timestamps in Knowledge Validation are labelled as
file metadata, not manufacturer publication dates. No real catalogue was
activated during these synthetic checks.

Local acceptance on 5 October 2026: 699 tests passed, 13 skipped. The installed
Edge browser exercised named sign-in, preview, staging, typed activation, reader
controls, failed-preview cleanup and logout/stale-response clearing against an
isolated synthetic API/data directory. This is not a real catalogue activation
or a storefront deployment rehearsal.
