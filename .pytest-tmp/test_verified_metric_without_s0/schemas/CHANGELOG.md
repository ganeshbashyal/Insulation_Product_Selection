# Schema versions and migration

## 2.0

Breaking changes:

- family and evidence source URLs are HTTPS URI values or `null` where identity is unresolved;
- family confidence uses a closed set of canonical tokens;
- evidence adds value type, source locator, extraction method/confidence, OCR confidence and verifier identity/timestamp;
- evidence IDs use uppercase letters/numbers separated by hyphens or underscores;
- legacy evidence without an attributable human verifier is migrated to `pending_human_review`.

Run `python scripts/migrate_schema_v1_to_v2.py` on a v1 checkout, review the diff, then rebuild SKU and Aircall outputs. The migration is idempotent and never marks evidence verified.
