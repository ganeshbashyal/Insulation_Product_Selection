# POC hardening status

| Identified gap | Implemented control | Current boundary |
|---|---|---|
| Normalized performance metrics | `knowledge/performance_evidence.json` stores metric, value, unit, variant, scope, test standard/context, source and review status. R, Rw and NRC/αw remain separate. | Empty or pending records stay visibly incomplete; exact SKU/system claims need source review. |
| Unresolved identity/evidence | One gate in `bot_engine.recommendation_allowed()` blocks `identity_unverified`, secondary-source and identity-review states. Schema validation cross-checks blocked families. | Review and change the family confidence only after primary evidence confirms identity. |
| Missing SKU dataset | `data/processed/product_catalogue_skus.csv` contains 414 Thermotec/Fletcher rows and source SHA-256 provenance. `scripts/build_sku_dataset.py` rebuilds it. | The original workbook is not committed; keep controlled exports in local/Drive storage. |
| No JSON schema | Draft 2020-12 schemas cover both family catalogue and evidence registry. `scripts/validate_catalogue.py` checks schemas, IDs, files, gates and every SKU row. | Schema changes must be versioned with migrations when production consumers exist. |
| No tests/CI | Pytest covers thermal/acoustic placement, paraphrase/typo matching, identity gates, schema/data checks and immutable review decisions. GitHub Actions runs validation and tests. | Add production-channel and connector tests when those integrations exist. |
| Fragile keyword matching | Canonical synonyms, phrase/token matching and conservative fuzzy-word fallback are isolated in `bot_engine.py`. | This is deterministic and auditable, not semantic AI search. Evaluate embeddings only with a labelled enquiry set and a safe fallback. |
| No TDS ingestion | `scripts/ingest_evidence.py` downloads PDF/HTML, hashes it and extracts candidates into an ignored review inbox. | It never promotes claims automatically. OCR for scanned PDFs and reviewer UI remain future work. |
| No audit/approval workflow | `audit_store.py` persists enquiries and immutable approval/rejection events in local SQLite; the Streamlit approval action uses the review ID. | CRM/ticket submission is not enabled until a platform, credentials, privacy/retention rules and field mapping are approved. |
| Aircall cannot ingest the catalogue CSV as knowledge | `scripts/build_aircall_pack.py` publishes a paste-ready knowledge block, agent instructions, intake questions and a source-hash manifest from the governed catalogue. | Trial users paste/configure these files manually. A hosted knowledge page or API Action can replace this after the trial. |
| Matching false positives | `config/matching.json` controls vocabulary, fuzzy matching and a mandatory no-reliable-match threshold; tests cover unrelated enquiries and placement language. | Tune only against a growing labelled enquiry set and track precision/recall before production. |
| Evidence extraction auditability | Raw downloads are stored by SHA-256 outside Git; candidates retain page/region and extraction/OCR confidence; CI produces an evidence triage artifact. | Scanned documents are flagged for OCR rather than interpreted automatically. An authorised reviewer must verify every promoted claim. |
| Callback PII | Optional Fernet encryption, reviewer allowlist and per-record retention deadlines are implemented; production can require encryption through environment configuration. | Local SQLite has no network API. Production requires authenticated RBAC, TLS and a managed encrypted database. |

## Release rule

Run both commands before merging catalogue or ranking changes:

```powershell
python scripts/validate_catalogue.py
python scripts/validate_aircall_pack.py
pytest -q
```

The POC may recommend a supported product family. It must not automatically select a SKU or claim NCC, BAL, fire, thermal-system or acoustic-system compliance.
