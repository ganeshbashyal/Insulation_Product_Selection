# Evidence deep-dive strategy

Last updated: 2026-09-13

## Objective

Improve product evidence without weakening the bot's family-only recommendation
boundary. All work is performed from locally held source files. Automated
extraction may create candidates, but only an authorised reviewer may promote
technical evidence to `verified`.

## Source-of-truth chain

| Layer | Authoritative input | Generated derivative |
|---|---|---|
| Family identity and routing | `knowledge/*/families.json` | retrieval cards, SQLite catalogue, Aircall pack |
| Product research | `knowledge/*/research/*.json` | retrieval text and generated literature |
| Approved performance claims | `knowledge/performance_evidence.json` | validation and customer-safe summaries |
| Compliance corpus | `knowledge/industry/compliance/raw/*` and curated Markdown | `compliance_rag_chunks.jsonl` |
| Building classes | `knowledge/building_classes/building_class_source.json` | building-class RAG chunks and local database |
| SKU provenance | approved local workbook export | SKU CSV and evidence manifest |

## Per-family workflow

1. Confirm identity using current primary manufacturer material already held locally.
2. Reconcile family name, product codes, variants, applications, and exclusions.
3. Extract technical claims with exact source locator, scope, units, and test context.
4. Keep unverified extraction in research/evidence candidate fields.
5. Obtain authorised human review before setting evidence to `verified`.
6. Rebuild derived artifacts and run the complete local gate.
7. Review customer language to ensure it does not imply SKU selection, compliance,
   quantity, availability, price, or guaranteed installed performance.

## Prioritisation

Process work in this order:

1. Items in `reports/evidence_triage.csv` that block otherwise useful families.
2. High-frequency families identified in `interaction_store.family_stats()`.
3. Families with SKU rows but incomplete evidence linkage.
4. Families with identity conflicts, legacy aliases, or secondary-only sources.
5. Remaining low-volume catalogue families.

## Completion criteria

A deep dive is complete only when:

- family identity and application boundaries are explicit;
- each numerical claim has metric, unit, variant, scope, test context, source, and review state;
- conflicting or missing evidence remains visibly unresolved;
- retrieval and generated artifacts match their sources;
- catalogue, Aircall, artifact-drift, evidence-triage, and test gates pass.
