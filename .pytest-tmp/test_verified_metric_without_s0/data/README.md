# Published data provenance

`processed/product_catalogue_skus.csv` is generated from the validated `Sheet1` export. Each row records:

- a deterministic `sku_record_id` based on manufacturer, source row and source SKU identifiers;
- source workbook filename and source sheet row;
- SHA-256 of the exact raw workbook bytes;
- ISO-8601 source retrieval timestamp;
- family and SKU eligibility flags.

`processed/sku_evidence_manifest.csv` maps every `sku_record_id` through its family to the evidence IDs and statuses current at publication. SKU selection eligibility also requires at least one attached `verified` evidence item; family-level discovery can remain available while performance review is pending.

SHA-256 generation is deterministic: `hashlib.sha256(source.read_bytes()).hexdigest()` over the unmodified workbook byte stream. Re-saving or copying through software that changes the workbook bytes correctly produces a different hash. For repeatable releases, pass the recorded acquisition time with `--source-retrieved-at`.
