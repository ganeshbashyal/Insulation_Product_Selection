# Insulation Product Enquiry Knowledge Base

This repository contains validated product knowledge for a customer enquiry and callback bot.

The local POC may recommend a manufacturer-supported product family. Exact product selection and all production behaviour remain governed by [`BOT_POLICY.md`](BOT_POLICY.md).

## Structure

### Complete Manufacturer Coverage (26 manufacturers, 2,359 products)

**Deep-dive documentation** (complete validation):
- [`knowledge/thermotec/`](knowledge/thermotec/README.md) — Thermotec product-family guides (13 families, 280 products)
- [`knowledge/fletcher/`](knowledge/fletcher/README.md) — Fletcher product-family guides (18 families, 134 products)

**Initial documentation** (all other manufacturers - 24 families each):
- [`knowledge/autex/`](knowledge/autex/README.md) — Autex (3 families, 324 products)
- [`knowledge/bradford/`](knowledge/bradford/README.md) — Bradford (4 families, 154 products)
- And 22 additional manufacturers: Kingspan, Rockwool, Proctor, Trade Select, Ecowool, Higgins Insulation, Knauf, Foilboard, Sonata, Polyester Solutions, Acoustica, Aircell, Metecno, Misc, DCTech, Stinger, Paroc, Ametalin, James Hardie, Hushtec, Polyair, Martini

See [`knowledge/LITERATURE_REVIEW_STATUS.md`](knowledge/LITERATURE_REVIEW_STATUS.md) for complete manufacturer list and status.

### Knowledge Base Files

- [`knowledge/{manufacturer}/families.json`](knowledge/autex/families.json) — Structured family metadata for discovery and ranking (one per manufacturer)
- [`knowledge/{manufacturer}/README.md`](knowledge/autex/README.md) — Family index and retrieval rules (one per manufacturer)
- [`knowledge/{manufacturer}/{family}.md`](knowledge/autex/batt.md) — Product family documentation files
- [`knowledge/performance_evidence.json`](knowledge/performance_evidence.json) — normalized R, Rw, NRC/αw, fire, vapour and temperature evidence with variant, scope, test context and provenance.
- [`knowledge/LITERATURE_REVIEW_STATUS.md`](knowledge/LITERATURE_REVIEW_STATUS.md) — Documentation status and next steps for technical validation

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

## Data model

The Google Sheet remains the structured product catalogue and source dataset. The Markdown files provide context the enquiry bot needs to interpret customer questions, including:

- intended applications and product roles;
- enquiry-routing and exclusion rules;
- important limitations and installation constraints;
- approved response language;
- links to official manufacturer sources.

Ratings guide follow-up questions, candidate ordering and the callback brief. In local demo mode, they may support a family-level recommendation when the application also matches; they never authorise SKU, grade, quantity or compliance selection.

Performance values must retain their test metric and system context. For example, `R` and `Rw` represent different properties and must never be treated as interchangeable.

## Validation convention

Each product-family file includes front matter with a stable `family_id`, manufacturer, validation status, and validation date. Product claims should be traceable to the official sources listed in that file.

The knowledge base now covers all 26 manufacturers represented in the source data. Deep-dive validation is complete for Thermotec and Fletcher. All other manufacturers have initial categorization structure ready for technical validation. A family may be recommended only when its identity is supported; exact SKU selection still requires row-level evidence and human review.

Rebuild the normalized SKU dataset from a validated local workbook export:

```powershell
python scripts/build_sku_dataset.py --source "C:\path\to\Product_Master_Bot_KB_SKU_Matched_cleaned.xlsx" --source-retrieved-at "2026-09-05T07:00:00Z"
python scripts/validate_catalogue.py
pytest -q
```

The checked-in CSV records the source workbook filename, source row, retrieval timestamp and SHA-256 hash. `sku_evidence_manifest.csv` provides the SKU → family → evidence chain. Only rows marked `PASS` and `READY`, attached to an evidence-eligible family with verified evidence, can set `sku_selection_eligible=true`. The demo still does not select that SKU automatically.

Aircall does not currently accept spreadsheet files as AI Voice Agent knowledge. `scripts/build_aircall_pack.py` converts the same governed family/evidence records into a concise paste-ready content block. Its manifest binds the generated pack to the exact source hashes, and validation prevents blocked families from entering the supported section.

## Evidence and approval workflow

Use [`scripts/ingest_evidence.py`](scripts/ingest_evidence.py) to put a PDF/HTML extraction into the ignored human-review inbox. Extraction never publishes a claim or changes recommendation eligibility. Approved claims must be normalized manually in `performance_evidence.json`.

Completed demo enquiries are written to an append-audited local SQLite review queue. Approval unlocks only the mock MYOB step. A live CRM/ticket adapter is intentionally not configured: the chosen platform, field mapping, credentials, retention and privacy controls require owner approval before any external submission is enabled.

See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for the control mapped to each identified gap and the remaining production work.

## Team demonstration

The local Streamlit demonstration compares all 287 manufacturer-classified product families across 26 manufacturers. The knowledge base supports acoustic, thermal, membrane, HVAC, pipe, roof and accessory applications. The user can filter by manufacturer or application, or compare across all manufacturers. It recommends the best supported family (with deep validation for Thermotec and Fletcher), exposes evidence limitations, includes a searchable range explorer, produces a callback brief and demonstrates a human-approved mock MYOB quote handoff. It does not access live Aircall, Google Drive or MYOB data.

Run it from Anaconda Prompt:

```powershell
cd "C:\Users\ganes\OneDrive\Documents\GitHub\Insulation_Product_Selection"
streamlit run app.py
```

### Optional: product literature (sales/SEO pages + DOCX)

[`scripts/generate_family_literature.py`](scripts/generate_family_literature.py) mines the deep-dive docs, `families.json` and the SKU catalogue to produce a concise, customer-facing page (`output/literature/<manufacturer>/<family>.md`) and a matching Word document (`.docx`) for every family, structured like the Thermotec 4-Zero literature draft (description, key features, applications + selection checklist, range table, technical data, compliance, install, safety, sustainability, warranty, spec clause, source register, review actions). Each page carries SEO `title`/`description`/`keywords`. Runs locally with no LLM; content-hashed so repeat runs only regenerate changed families:

```powershell
python scripts/generate_family_literature.py            # all 287 families
python scripts/generate_family_literature.py --only Autex
```

### Optional: deep-dive TDS research agent (local, background)

[`scripts/tds_research_agent.py`](scripts/tds_research_agent.py) fetches each family's real manufacturer datasheet PDF (from the SKU catalogue, the official `source_url`, or a web/sitemap search on the manufacturer's domain), extracts the text, and asks your **local Ollama** model to structure it into a JSON spec — real R-values, densities, fire indices, install steps, applications — stored at `knowledge/<manufacturer>/research/<family>.json` with the source URL recorded. Nothing leaves your machine; only the local model processes the text. Re-running the literature generator then folds that real data into the MD/DOCX instead of thin placeholders.

Run it one family at a time (reliable on a local LLM; safe to schedule in the background):

```powershell
ollama serve                                   # keep the local model running
python scripts/research_next_family.py         # process the next pending family, then stop
python scripts/research_next_family.py --loop --delay 3   # or keep going until done
python scripts/research_next_family.py --status           # progress
python scripts/tds_research_agent.py --only Fletcher      # or a whole manufacturer at once
```

Resumable: each family writes its own JSON, so you can stop and restart any time. Families whose PDF can't be found are marked `no_pdf_found` and skipped on later runs until you supply a link (via the TDS CSV) or one becomes discoverable. Web search can be blocked in some environments; the sitemap crawl is the fallback, and hand-filled links in `data/processed/tds_links_to_source.csv` always take precedence.

### Optional: deployable website agent

[`web_agent.py`](web_agent.py) serves the same conversation flow as a self-hosted FastAPI app (no Streamlit), so it can be embedded on a website. It reuses the deterministic ranker/gates and logs every conversation for interaction learning:

```powershell
uvicorn web_agent:app --host 0.0.0.0 --port 8000
# embed: <iframe src="https://your-server/chat" style="width:420px;height:640px;border:0"></iframe>
```

Interaction learning ([`interaction_store.py`](interaction_store.py)) records each completed conversation and its recommended family; reviewers then record an outcome (`approved` / `edited` / `rejected`, with an optional corrected family). Per-family stats (`/api/learning/families`), pending reviews (`/api/learning/pending`) and recent rejections (`/api/learning/rejections`) show where the deterministic ranker misfires so the team can tune it. Learning informs human tuning — it never auto-changes live recommendations.

### Optional: natural reply phrasing via a local LLM

By default the chat's questions and recommendation replies are built from fixed template text — safe, but repetitive. To have replies phrased more naturally, run a local [Ollama](https://ollama.com) server (no external API, no data leaves your machine/server):

```powershell
ollama pull llama3.1:8b   # or any chat model you have pulled, e.g. gemma4:latest
ollama serve
```

Then restart the Streamlit app. A "Natural phrasing (local LLM)" toggle appears in the sidebar and turns on automatically once the local server is detected (`http://localhost:11434` by default; override with the `OLLAMA_HOST` and `OLLAMA_MODEL` environment variables). The LLM only rephrases text the rules engine has already decided — it never selects the recommended family, chooses a SKU, or asserts compliance; if the server is unreachable the app silently falls back to the fixed wording.

If phrasing feels slow: use a smaller model (`ollama pull gemma3:4b` then set `OLLAMA_MODEL=gemma3:4b` — 3-4B models rephrase a short sentence in ~1-2s on CPU), keep `ollama serve` running so the model stays warm, and note the app caps reply length (`num_predict=160`), keeps the model loaded for 30 minutes, and caches successful phrasings — the demo asks the same questions every conversation, so repeat runs are instant.

