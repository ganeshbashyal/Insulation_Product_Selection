# Evidence intake and approval

`scripts/ingest_evidence.py` downloads a manufacturer PDF or HTML page, records its URL and SHA-256 checksum, extracts candidate performance lines, and writes a `pending_human_review` item into `evidence/inbox/`.

The inbox is deliberately ignored by Git because it can contain copyrighted source text. It is not read by the recommendation engine. A reviewer must compare every proposed claim with the source and then add a concise normalized record to `knowledge/performance_evidence.json`, including:

- metric and unit;
- product, material, component or system scope;
- exact variant/SKU;
- test standard and tested construction/context;
- primary source URL;
- evidence status and review date.

Example:

```powershell
python scripts/ingest_evidence.py --family-id THERMOTEC_NUWAVE_BASE_MLV --url "https://manufacturer.example/current-tds.pdf"
```

An ingestion result is research material only. It cannot enable a family or SKU automatically.
