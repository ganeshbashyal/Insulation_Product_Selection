# Insulation Product Enquiry Knowledge Base

This repository contains validated product knowledge for a customer enquiry and callback bot.

The local POC may recommend a manufacturer-supported product family. Exact product selection and all production behaviour remain governed by [`BOT_POLICY.md`](BOT_POLICY.md).

## Structure

- [`knowledge/thermotec/`](knowledge/thermotec/README.md) — Thermotec product-family guides used to understand and qualify enquiries.
- [`knowledge/thermotec/families.json`](knowledge/thermotec/families.json) — the 13-family structured catalogue used by the Streamlit matching and range-explorer views.
- [`knowledge/fletcher/`](knowledge/fletcher/README.md) — Fletcher product-family guides for all 134 Fletcher-labelled rows in `Sheet1`.
- [`knowledge/fletcher/families.json`](knowledge/fletcher/families.json) — the 18-family Fletcher catalogue used in cross-manufacturer comparison.
- [`notebooks/01_thermotec_poc.ipynb`](notebooks/01_thermotec_poc.ipynb) — maps and validates all 280 Thermotec rows currently in `Sheet1`.
- [`scripts/validate_fletcher.py`](scripts/validate_fletcher.py) — maps and validates the 134 Fletcher rows and writes `reports/fletcher_validation_report.csv`.
- [`data/processed/product_catalogue_skus.csv`](data/processed/product_catalogue_skus.csv) — the checked-in, normalized 414-row SKU catalogue for Thermotec and Fletcher. Stock-control fields are deliberately excluded.
- [`knowledge/performance_evidence.json`](knowledge/performance_evidence.json) — normalized R, Rw, NRC/αw, fire, vapour and temperature evidence with variant, scope, test context and provenance.
- [`schemas/`](schemas/) and [`scripts/validate_catalogue.py`](scripts/validate_catalogue.py) — machine-enforced structures and cross-file safety checks.
- [`tests/`](tests/) and [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — ranking, gating, catalogue and audit regression checks run on every push and pull request.
- [`aircall/`](aircall/README.md) — generated trial knowledge, agent instructions and four-question intake configuration derived from the governed catalogue.
- [`config/matching.json`](config/matching.json) — reviewed synonyms, fuzzy threshold, singularisation exceptions and the no-reliable-match threshold.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AUDIT_SECURITY.md`](AUDIT_SECURITY.md) — evidence approval, rollback, access, encryption and retention controls.

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

The proof of concept currently compares Thermotec and Fletcher. A family may be recommended only when its identity is supported; exact SKU selection still requires row-level evidence and human review.

Rebuild the normalized SKU dataset from a validated local workbook export:

```powershell
python scripts/build_sku_dataset.py --source "C:\path\to\Product_Master_Bot_Sheet1_Validated.xlsx" --source-retrieved-at "2026-09-04T07:00:00Z"
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

The local Streamlit demonstration compares 31 Fletcher and Thermotec families across acoustic, thermal, membrane, HVAC, pipe, roof and accessory applications. The user can compare both manufacturers or restrict the result to one. It recommends the best supported family, exposes evidence limitations, includes a searchable range explorer, produces a callback brief and demonstrates a human-approved mock MYOB quote handoff. It does not access live Aircall, Google Drive or MYOB data.

Run it from Anaconda Prompt:

```powershell
cd "C:\Users\ganes\OneDrive\Documents\GitHub\Insulation_Product_Selection"
streamlit run app.py
```
