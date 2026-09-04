# Evidence intake and approval

`scripts/ingest_evidence.py` downloads a manufacturer PDF or HTML page, stores the immutable binary as `evidence/raw/<sha256>.<type>`, records its URL and retrieval timestamp, and writes page/region-aware extraction candidates into `evidence/inbox/`.

The raw store and inbox are deliberately ignored by Git because they can contain copyrighted source material. Neither is read by the recommendation engine. Image-only PDFs are flagged `ocr_required`; the pipeline does not invent OCR output or confidence. A reviewer must compare every proposed claim with the hashed source and then add a concise normalized record to `knowledge/performance_evidence.json`, including:

- metric and unit;
- product, material, component or system scope;
- exact variant/SKU;
- test standard and tested construction/context;
- primary source URL;
- source page/region, extraction method and extraction/OCR confidence;
- reviewer identity and full verification timestamp.

Example:

```powershell
python scripts/ingest_evidence.py --family-id THERMOTEC_NUWAVE_BASE_MLV --url "https://manufacturer.example/current-tds.pdf"
```

An ingestion result is research material only. `auto_promotion_allowed` is always false. It cannot enable a family or SKU automatically.

Run `python scripts/evidence_triage.py` to generate `reports/evidence_triage.csv`. It lists low-confidence extractions, missing standards/context, unresolved source locators and invalid verification metadata.
