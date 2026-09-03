---
family_id: FLETCHER_FF_HD_LEGACY
manufacturer: Fletcher Insulation
spreadsheet_identity: FF HD
category: Legacy insulation record
validation_status: blocked_identity_unverified
last_validated: 2026-09-04
recommendation_scope: none
---

# FF HD — Legacy Evidence Dossier

## Status and ambiguity

“FF HD” in the spreadsheet is not a sufficiently specific current Fletcher product identity. It may refer to a historical/high-density/faced line, but guessing would risk mapping the row to FI32, Pink Partition, a foil facing or another unrelated family. No automatic recommendation, quote or compliance statement is permitted.

| Priority | Result | Reason |
|---|---|---|
| Thermal/acoustic fit | Unknown | Material, density, thickness and application unresolved. |
| Sustainability | Unknown | No evidence scope. |
| Installation practicality | Unknown | Format and facing unresolved. |
| Compliance/BAL | Blocked | No current primary evidence. |

## Evidence required and bot action

Obtain original catalogue/date, full description, manufacturer code, photo/label, material, dimensions, density, R-value, facing, test reports and current availability. Capture the customer's intended application and specification clause. Route to purchasing/Fletcher; do not propose an alternative until the performance and system role are known.

## Approved bot language

> “FF HD” appears to be an abbreviated legacy record and is not enough to select safely. Please share the product code, label or specification and our team will verify the current equivalent.

```json
{"family_id":"FLETCHER_FF_HD_LEGACY","recommendation_level":"blocked_identity_unverified","required_evidence":["full_name","catalogue_date","product_code","material","dimensions","facing","performance","availability"],"human_gates":["identity","equivalence","substitution","quote","compliance","BAL"]}
```
