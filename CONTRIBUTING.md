# Catalogue and evidence governance

## Roles

- **Catalogue editor:** may propose descriptions, mappings, synonyms and evidence candidates. Cannot mark evidence verified or promote an unresolved identity.
- **Evidence reviewer:** a named person authorised by the product owner. Checks the original hashed source and records `verified_by`, `verified_at`, source locator, test context, standard, variant and scope.
- **Release approver:** reviews the diff, triage report and test result before merging/publishing to Aircall.

Record the actual people assigned to these roles in the private operating register; do not put personal credentials in Git.

## Pending to manufacturer-supported checklist

Before changing a family confidence to `manufacturer_supported`:

1. Confirm current manufacturer identity using a primary HTTPS source.
2. Confirm the knowledge file, applications, exclusions and human gates.
3. Add at least one identity or performance evidence pointer.
4. For performance claims, retain exact variant, unit, value type, scope, standard, test context and page/region.
5. Have an authorised reviewer set the claim to `verified` with their identity and an ISO-8601 timestamp.
6. Rebuild the SKU catalogue, evidence manifest and Aircall pack.
7. Review `reports/evidence_triage.csv`.
8. Run all release commands below.

## Release commands

```powershell
python scripts/validate_catalogue.py
python scripts/validate_aircall_pack.py
python scripts/evidence_triage.py
pytest -q
```

## Correcting an erroneous verification

Immediately change the evidence status to `pending_human_review`, clear `verified_by` and `verified_at`, record the reason in `notes`, rebuild the derived outputs and publish a corrective commit. Revert the bad commit with `git revert <commit>` if the correction cannot be prepared safely in the same release. Refresh/remove the affected Aircall source before further calls.

Never rewrite Git history to hide an evidence error. The correction must remain auditable.
