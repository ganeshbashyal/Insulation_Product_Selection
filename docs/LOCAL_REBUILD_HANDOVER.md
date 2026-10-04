# Standalone local rebuild handover

## Status and scope

Deployment strategy now uses deterministic local tools first, following repeated
weak model policy-map drafts. See the [developer handbook](DEVELOPER_HANDBOOK.md).
This document describes the optional proposal tool and its historical task queue,
not a requirement to keep retrying that queue or proof of deployment readiness.
The read-only Knowledge Validation foundation is implemented; the full deployment
programme is not.

The **standalone bootstrap is implemented**. The full-stack rebuild is not yet
performed. The owner chose a slower local Ollama workflow rather than further
Copilot-led implementation. This document is the portable execution handover;
the eventual consolidated developer handbook will be written by accepted local
tasks, not automatically generated or applied by this bootstrap.

`scripts\run_local_maintenance.py` uses standard Python, local files and HTTP
requests exclusively to literal loopback Ollama on port 11434. It does not
call Copilot, Gemini, hosted AI, web search or a model-download endpoint.
Preparation in Copilot still consumes Copilot usage; running this script from
ordinary PowerShell with Copilot paused does not invoke Copilot.

Work in the checkout containing these changes. Do **not** archive/delete this
app worktree, reset it to merged main, or run against the D-drive clone/main
checkout accidentally. The current uncommitted work is the input baseline.
No commit or push was performed by the bootstrap.

## What to preserve

- Source PDFs, original workbooks, supplied-link fields and source hashes.
- All 283 canonical family IDs and 414 distinct child `sku_record_id` values.
  Shared product codes must not collapse distinct rows.
- Product guides, hand-authored notes and immutable technical-review history.
- Saved sales-brief snapshots, customer privacy and consent boundaries.
- Draft review versus explicit publisher activation. Models cannot approve
  evidence, customer suitability, compliance, installation, quantities or orders.
- The functioning FastAPI chat, sales briefs and family-first research page.
  Rebuilds must not enable a second customer UI or a competing recommender.

Similar data is not necessarily redundant. Sources, research attempts,
generated views, reviewed claims and historical snapshots have different roles.
Consolidate ownership and readers before deciding whether files can be retired.
Do not delete source libraries or manually edited workbooks as cleanup.

## Model allocation

These models were already installed; no pull is needed:

| Model | Approximate weight size | Role |
| --- | --- | --- |
| `deepseek-coder:6.7b` | 3.56 GiB | Small code/refactor proposals |
| `llama3.1:8b` | 4.58 GiB | Handbook chapters and grounded summaries |
| `llama3.2:latest` | 1.88 GiB | Small summaries and smoke tasks |
| `phi4-mini:latest` | 2.32 GiB | Explicit lightweight alternate |

At inspection the machine had about 10 GiB free RAM out of 31.63 GiB.
Model weights are not the total memory requirement. `gemma4:26b` is installed
but its approximately 17.44 GiB weights exceed that free memory; it is not an
allowed default in this runner. `mistral:7b` and `nomic-embed-text:latest` are
also installed but are not scheduled here.

Run one model/task at a time. The runner refuses to start when a different
model is resident and does not unload another user's model. It unloads a model
it loaded itself; an already-resident same model is left alone. No cloud
fallback, model pull or automatic retry exists. Smaller models may produce
bad JSON, truncated files or unsafe suggestions: inspect every diff.

After the CPU-only 8B attempt caused resource pressure, new tasks default to
`llama3.2:latest`. The runner now requests a 4,096-token context and at most
1,024 output tokens, with a 4,000-byte input limit. Existing tasks retain their
recorded model; do not retry an 8B task expecting the default to change it.
Use `reject --model llama3.2:latest` to prepare a smaller replacement while
preserving the failed attempt. No inference is started by rejection.
These limits reduce memory demand, not guarantee desktop responsiveness.

## Start from ordinary PowerShell

Pause Copilot before running the actual rebuild. Keep this checkout available.
Run commands from its repository root. These commands do not start a background
agent, schedule automation or activate research evidence.

```powershell
python scripts\run_local_maintenance.py --help
python scripts\run_local_maintenance.py inventory
python scripts\run_local_maintenance.py status
python scripts\run_local_maintenance.py next
python scripts\run_local_maintenance.py init
```

`inventory`, `status` and `resume` are read-only. They do not create a journal,
call a model or run tests. `init` explicitly creates an empty journal.
Inventory includes imports/functions/Markdown links, not a proof of dead code:
CLI, decorators, callbacks, function lists and notebook consumers need review.
Inventory does not read live databases, customer leads or binary source content.

Use **`next`** for routine progress without sending logs back to Copilot. It
reports task state, errors, artifact locations and the next explicit local
command. It never calls a model, retries, verifies, applies or clears a lock.
Proposals report the model/input budget at start and announce staged/failed
completion in the owning terminal. While a model is running, wait in that
terminal; do not start another runner or ask Copilot to poll it.

| Local status | Meaning / action |
| --- | --- |
| pending | Ready only after dependencies are accepted; explicitly propose |
| running / lock present | Inspect owning terminal/PID; do not relaunch or auto-clear |
| staged | Local model ran, but content is not approved; read the entire diff |
| verified | Mechanical checks only; human semantic acceptance still required |
| verification_failed / failed | Inspect error/log; reject or narrow the task |
| rejected | Attempt retained; follow its explicit replacement |
| applied | Accepted files changed locally; not committed or evidence-approved |
| applying / apply_interrupted | Inspect precise backup/current files; no automatic rollback |

### Reject the weak first draft and prepare a smaller task

The observed `doc-policy-map` run succeeded locally and staged a document,
but its draft invented a `primary` eligibility state and failed to provide the
requested inconsistency map. Do not apply it. A model finishing is not proof of
semantic correctness. Subsequent checkout changes also make old previews stale.

This explicit action preserves the rejected artifacts and prepares a replacement;
it does **not** call a model, consume a retry or modify project documentation:

```powershell
python scripts\run_local_maintenance.py reject doc-policy-map `
  --feedback "The draft invents a primary identity state and omits the inconsistency map. Use exact supplied statements and citations only." `
  --replacement doc-policy-map-narrow `
  --instruction "Write a short table of CURRENT versus STALE documentation statements using only supplied excerpts. Cite filename and L-line for each statement. Use actual state names only. If evidence is insufficient write unknown. Do not invent rules or product claims. Output only the inconsistency map." `
  --read README.md@1:12 `
  --read IMPLEMENTATION_STATUS.md@1:17 `
  --read BOT_POLICY.md@1:24

python scripts\run_local_maintenance.py next
```

Run the reported `propose` command only when ready. Read the new diff before
verification and apply. Split an inadequate excerpt into another task instead
of repeated broad model prompts. `--retry` also archives previous attempt files.
If the original task is already rejected, use its saved replacement; do not
repeat the rejection or recreate an existing task.

The bounded Copilot setup has now preserved the observed first draft as
rejected and prepared `doc-policy-map-narrow` with zero model attempts.
That replacement subsequently failed with HTTP 500. Run `next` to check your
actual journal; do not repeat it on the 8B model. The lower-memory follow-up
uses a smaller model and shorter excerpts. Its content still needs human review.

Only unresolved genuine implementation blockers should return to Copilot,
with the smallest relevant error excerpt. Ordinary next/status/diff/testing
and local proposals need no cloud conversation or automated cloud agent.

Working files are ignored under `data\local\maintenance\`: journal, task prompt,
raw reply, candidate JSON/diff, verification log and precise apply backups.
Keep these files local; do not commit credentials, source documents or private
exports. Accepted developer documentation is written into the repository only
after explicit apply.

### First small documentation task

```powershell
python scripts\run_local_maintenance.py add doc-policy-map `
  --model llama3.2:latest `
  --instruction "Compare only the supplied documentation. Write a short, cited inconsistency map for current internal recommendations, reviewer UI and exact-SKU eligibility. Do not approve products or change sources. Preserve uncertainty." `
  --read README.md@11:11 --read IMPLEMENTATION_STATUS.md@11:11 --read BOT_POLICY.md@11:18 `
  --write docs/REBUILD_POLICY_MAP.md

python scripts\run_local_maintenance.py propose doc-policy-map
Get-Content -Raw data\local\maintenance\doc-policy-map\candidate.diff
python scripts\run_local_maintenance.py verify doc-policy-map
Get-Content -Raw data\local\maintenance\doc-policy-map\verification.json
```

Manifest `--read`, `--write` and `--test` values use relative forward-slash
**identifiers**, not OS paths. The runner converts these into local `Path`
objects on Windows. No absolute paths, drive letters, `..`, symlinks or private
lead directories are accepted. The surrounding PowerShell filesystem commands
use Windows backslashes.

The runner includes existing output content in the prompt so hand edits are
visible to the model. Use `path@START:END` to provide explicit inclusive line
ranges of large files; line labels are metadata, not file content. Unseen lines
are retained by bounded line replacements. It refuses input over 4,000 bytes instead of silently
truncating; split such a task into smaller sections/files. Candidate JSON is
bounded and must contain a rationale plus complete file replacements, or
`start_line`/`end_line` replacements of existing lines, at explicitly allowed
paths. The runner reconstructs the complete candidate and shows the exact diff.
Empty-file/deletion operations are rejected. Read and token budgets leave
headroom for ordinary prose in the configured 4,096-token context; output is limited to 1,024
tokens and truncated output is rejected. Split large changes instead of
increasing memory limits blindly.
No model-proposed shell command is executed.

### Accept a verified diff explicitly

Only after reading the entire diff, checking original documentation/code and
reviewing the verification log:

```powershell
python scripts\run_local_maintenance.py apply doc-policy-map --confirm doc-policy-map
python scripts\run_local_maintenance.py status
python scripts\run_local_maintenance.py resume
```

`--confirm` is a **human approval token**, not a suggestion to automate apply.
The runner prints the diff again, checks the exact verified candidate and
rechecks source fingerprints. Existing dirty files are included in the baseline
and precise changed-file bytes are backed up before apply. No Git reset,
checkout, automatic rollback, commit or push occurs.

`resume` only reports the journal and ready tasks. It does not propose, retry,
run tests, apply edits or mark an interrupted task complete.
Add subsequent small tasks using `--depends doc-policy-map` where it is a real
prerequisite. Dependencies require the previous task to be accepted/applied.

### Code tasks and tests

Add one module/interface change at a time, with an existing synthetic test
selector using repeated `--test tests/test_NAME.py` arguments. Test selection
cannot be supplied by model output. No package install is attempted.

Verification builds a disposable **text snapshot**, including current dirty
files, under that task's maintenance directory. It is not an empty Git clone
and not an OS sandbox. Original binary PDFs/workbooks and live databases are
not copied; their source bytes are fingerprinted to detect changes. The log
lists omitted sources. Tests requiring those files need synthetic fixtures or
separate owner-controlled validation; absence is not treated as a passing test.

Python syntax and local Markdown file links are checked without executing
candidate code or fetching links. Documentation anchors are not validated by
the lightweight file-link check; inspect anchors separately. HTML/JS behaviour,
type safety, policy semantics and whole-repository correctness require the
workstream's actual targeted tests/browser checks.

If tests are selected, inspect the diff first and explicitly opt into execution:

```powershell
python scripts\run_local_maintenance.py verify TASK_ID --approve-tests
```

Candidate Python/tests **can execute code**. `--approve-tests` is not isolation:
inspect imports, fixtures and side effects before granting it. Environment
credentials are filtered, model wording/hybrid ranking are disabled, Ollama
points to an unavailable loopback test port and the fixed pytest command runs
in the candidate snapshot. This is not a firewall or a security sandbox.
Use audited offline tests; do not grant execution to unreviewed model code.

The runner does not allow changes to source/data/configuration/approval paths,
its own runner or its safety tests. It supports `.py`, developer `.md` and UI
`.html/.css/.js` edits, not schema/config migrations. Such migrations require a
separate owner-reviewed extension of the write contract; do not bypass it.

## Failures and interrupted work

- A model failure is `failed`; no fallback runs. Inspect `reply.txt` when
  available and the journal error. One additional attempt requires `--retry`.
  After that, create a smaller task or resolve it manually.
- Invalid JSON, unexpected paths, empty/truncated/oversized replies, stale files,
  syntax/link errors and failing/timed-out tests block acceptance.
- A crash can leave `runner.lock`. Inspect its PID and confirm that specific
  process is no longer running before manually removing that exact lock file.
  Never use name-based process killing or broad directory cleanup.
- Multi-file apply is **not transactional across files**. An interruption may
  leave some edits applied. It is reported as `applying`/`apply_interrupted`,
  not success. Compare current files, candidate diff and `apply-backup.json`
  before manually restoring only affected files or creating a new task.
  Do not overwrite newer human edits or automatically reset the checkout.
- Candidate directories/logs are retained for inspection; cleanup is manual
  and limited to an explicitly identified completed task, never source folders.

Small-model success is not evidence approval. Tests passing is not sufficient
for semantic acceptance. The owner remains the final diff reviewer.

## Rebuild workstreams, executed locally

The added [admin rebuild contract](LOCAL_ADMIN_REBUILD_CONTRACT.md) covers
Knowledge Validation, supplied-evidence Competitor Comparison and versioned
new-code SKU import. These are planned local workstreams, **not implemented
admin pages**. They reuse stable families/shared readers and must preserve
historical rows without transferring SKU approvals automatically.

| Order | Work | Required outcome |
| --- | --- | --- |
| 1 | Full-stack inventory | Module/entry-point/caller register; source-to-consumer graph; writes, network/model behaviour, tests, optional versus dead-code candidates; Markdown ownership manifest |
| 2 | Developer handbook | Consolidate most developer documents into `docs/DEVELOPER_HANDBOOK.md` with TOC/stable anchors; retain unique history and old navigation links; product guides remain separate |
| 3 | Shared governed readers | Extract data/publication services from HTTP routes; align supported facts/eligibility consumers and refresh/revocation contracts; exact variant rows, never inferred code dimensions |
| 4 | Generators/validators/lifecycle | One owning generator per output; dry-run/diff; preserved human markers/manual fields; all-family validation; compatible SQLite migrations and local backup contracts |
| 5 | Dormant internal capabilities | Prove usefulness and safe local source availability before adapting health/source verification/construction context/evaluation into research or briefs; no public behaviour change by default |
| 6 | Verification and handover | Offline regression, installed-Edge checks, all family/SKU joins, source byte preservation, handbook links/commands and explicit remaining limitations |

Inventory must precede documentation consolidation and shared-reader design.
Generator/store work follows shared-reader contracts. Internal activation follows
both governed readers and lifecycle safety. Final validation follows all three.
Execute serially even where logical workstreams are independent.

### Findings to confirm before changing code

- `IMPLEMENTATION_STATUS.md` still treats research UI as future work and allows
  public recommendations; current policy keeps provisional families private.
- `data/README.md` equates any verified family metric with SKU eligibility;
  local publication requires exact child-row applicability.
- `CONTRIBUTING.md` describes baseline-file releases, not the distinct local
  review/publication overlay. Do not mix Git releases with local activation.
- `product_answers.py` and `sku_catalogue.py` obtain data through `research_api`;
  the framework-independent service should own that access.
- `size_index.py` flattens dimensional/rating sets and parses codes; prove
  reachable use before replacing it with source-scoped variant tuples.
- RAG, Aircall builders, baseline evidence and local publication have different
  consumers/caches. Do not assume a publication updates every export.
- There are several Markdown writers. `enrich_knowledge_docs.py` preserves
  generated markers; `generate_deep_dive_docs.py` can rewrite documents and
  family metadata. Do not run whole-library generators casually.
- `validate_catalogue.py` still has a two-manufacturer assumption.
- `data_health` is used indirectly by the notebook. Missing optional DBs do
  not mean broken chat or justify an automatic rebuild.
- `SmartQuestioner` is statically test-only and uses the legacy fixed question
  list; preserve useful concepts without restoring that flow.
- The experimental `improvements` ranker uses different gates; do not activate
  it wholesale. Building-class context already reaches RAG through generated
  chunks, even though its CLI/database helpers are separate.
- Separate `audit_store`, `research_store` and lead stores have different
  purposes. Shared SQLite helpers do not justify merging PII and evidence DBs.
- Some construction/notebook commands download data, pull models or rebuild
  manually edited reports. Keep them out of standalone default actions.

## Handbook contents and final checks

The comprehensive handbook should document purpose/policy, runtime paths,
data ownership/provenance, local configuration, chat/discovery, protected sales
briefs, family research/accounts, review/publish/revoke, TDS/manual inputs,
capability register, generator dependency matrix, tests/evaluation,
schema migration/backups, privacy/retention limits, troubleshooting and known
issues. Keep [BOT_POLICY](../BOT_POLICY.md) as the normative safety contract;
do not create a competing recommendation policy in the handbook.

Do not flatten product-source evidence into the developer handbook. Keep
human family guidance, sourced industry context, immutable review decisions and
generated drafts distinguishable. Older developer documents can become clear
superseded references after unique information is retained and links tested.

Rebuild acceptance requires actual targeted/full regression and browser results,
not a model-written “complete” statement. Protect sources byte-for-byte; never
use real evidence approval or private customer contacts as test fixtures.
Restart only an explicitly owned local server after owner acceptance. No
external channel activation, source fetching, dependency downloads, commit or
push is included.
