# Insulation Product Enquiry Knowledge Base

This repository contains a local-first product knowledge and enquiry bot for Australian insulation and building-material enquiries.

The local POC may recommend a manufacturer-supported product family. Exact SKU selection, quantities, compliance decisions and all production behaviour remain governed by [`BOT_POLICY.md`](BOT_POLICY.md).

## Current architecture

The repository has four related data layers:

1. **Family metadata** — `knowledge/*/families.json` contains the stable family identity, applications, ranking signals, source provenance and human gates for 283 families across 26 manufacturers.
2. **Research evidence** — `knowledge/*/research/*.json` contains the normalized research contract for 259 extracted or attempted family research records. Each file has the same top-level and `spec` fields, including range rows, technical properties, installation, clearances, limitations and source links.
3. **Human-readable knowledge** — `knowledge/*/*.md` preserves hand-authored family guidance and adds generated physical/technical and installation sections. Every family document now has both generated sections; missing evidence is marked as pending rather than inferred.
4. **Structured local catalogue** — `data/local/family_catalogue.sqlite3` provides queryable family, variant and installation tables for deterministic retrieval. It complements Markdown; it does not replace the source and policy layers.

The bot path is deliberately deterministic first: family metadata and approved evidence drive ranking and gates, while a local LLM may phrase an already-decided response. The LLM does not choose products or invent technical claims.

`agent_core.py` owns serializable qualification and recommendation state.
`conversation_service.py` applies routing, local tools, RAG, policy linting and
interaction logging for the local FastAPI service. There is one supported
conversation interface; the retired desktop demo is not part of the runtime.

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

Ratings guide follow-up questions, candidate ordering and the callback brief. In local demo mode, they may support a family-level recommendation when the application also matches; they never authorise SKU, grade, quantity or compliance selection.

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

The knowledge base covers all 26 manufacturers represented in the source data. Research and evidence status remain family-specific. A family may be recommended only when its identity is supported; exact SKU selection still requires row-level evidence and human review.

Rebuild the normalized SKU dataset from a validated local workbook export:

```powershell
python scripts/build_sku_dataset.py --source "C:\path\to\Product_Master_Bot_KB_SKU_Matched_cleaned.xlsx" --source-retrieved-at "2026-09-05T07:00:00Z"
python scripts/validate_catalogue.py
pytest -q
```

The checked-in CSV records the source workbook filename, source row, retrieval timestamp and SHA-256 hash. `sku_evidence_manifest.csv` provides the SKU → family → evidence chain. Only rows marked `PASS` and `READY`, attached to an evidence-eligible family with verified evidence, can set `sku_selection_eligible=true`.

### Planned SKU recommendation stage

The current bot supports family ranking and direct size/R-value availability lookup through [`size_index.py`](size_index.py). The next SKU capability should be implemented as a separate, gated retrieval stage:

1. Filter candidate rows by family, application, region and the customer's stated constraints.
2. Require `sku_selection_eligible=true`, verified product evidence, current source provenance and a matching variant record.
3. Rank possible SKU candidates deterministically; never let the LLM choose the row.
4. Present results as possible matches, including product code, published dimensions, R-value and source status.
5. Require human confirmation before quoting, ordering, selecting quantity or claiming compliance.

The response contract should distinguish `family_recommendation`, `possible_sku_matches` and `human_review_required`. A missing dimension, conflicting source, stale product code, unverified identity or compliance request must produce an escalation rather than a confident SKU recommendation.

Aircall does not currently accept spreadsheet files as AI Voice Agent knowledge. `scripts/build_aircall_pack.py` converts the same governed family/evidence records into a concise paste-ready content block. Its manifest binds the generated pack to the exact source hashes, and validation prevents blocked families from entering the supported section.

## Evidence and approval workflow

Use [`scripts/ingest_evidence.py`](scripts/ingest_evidence.py) to put a PDF/HTML extraction into the ignored human-review inbox. Extraction never publishes a claim or changes recommendation eligibility. Approved claims must be normalized manually in `performance_evidence.json`.

Completed demo enquiries are written to an append-audited local SQLite review queue. Approval unlocks only the mock MYOB step. A live CRM/ticket adapter is intentionally not configured: the chosen platform, field mapping, credentials, retention and privacy controls require owner approval before any external submission is enabled.

See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for the control mapped to each identified gap and the remaining production work.

## Local FastAPI chat

The local chat compares manufacturer-classified product families, exposes
evidence limitations, and captures a callback lead and project brief after
showing the recommendation. The service uses local SQLite and can use a local
Ollama model for optional phrasing; it does not require cloud infrastructure.
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
conversations and recommendations; reviewers can record outcomes (`approved`,
`edited` or `rejected`, with an optional corrected family). Per-family stats
(`/api/learning/families`), pending reviews (`/api/learning/pending`) and recent
rejections (`/api/learning/rejections`) show where the deterministic ranker
misfires. Learning informs human tuning; it never auto-changes recommendations.

### Optional: natural reply phrasing via a local LLM

By default the chat's questions and recommendation replies are built from fixed template text — safe, but repetitive. To have replies phrased more naturally, run a local [Ollama](https://ollama.com) server (no external API, no data leaves your machine/server):

```powershell
ollama list               # use a model already installed locally
ollama serve
```

Set `AGENT_USE_LLM=true` and restart the FastAPI service to enable optional local
phrasing when Ollama is reachable (`http://127.0.0.1:11434` by default;
override with `OLLAMA_HOST` and `OLLAMA_MODEL`). The LLM only rephrases text
already decided by the rules engine—it never selects the recommended family,
chooses a SKU or asserts compliance. If the local server is unreachable, the
service falls back to fixed wording.

For a setup designed to stay local, use an already-installed local model and
avoid cloud-hosted model APIs. If phrasing feels slow, a smaller local model may
help; model generation and datasheet research are not required to run the chat.
