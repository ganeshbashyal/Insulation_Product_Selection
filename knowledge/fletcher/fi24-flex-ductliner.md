---
family_id: FLETCHER_FI24_FLEX_DUCTLINER
manufacturer: Fletcher Insulation
canonical_name: FI24 Flexible Ductliner
category: Flexible HVAC glasswool ductliner
validation_status: manufacturer_supported_spreadsheet_alias_review
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/fi24-flexible-ductliner/
---

# FI24 Flexible Ductliner

## Canonical description

FI24 is Fletcher's flexible glasswool ductliner family for internal lining of sheet-metal ductwork, providing thermal resistance and sound absorption/attenuation within a correctly designed HVAC system. It is distinct from FI32 semi-rigid board/roll and from external duct wrap.

The spreadsheet includes a “FI22 FLEX DLINER” line (including code 4005560) inside this grouping. Treat that as an alias/identity exception until the current FI24 table or manufacturer documentation confirms it; do not silently rename or quote it.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 4 | High | Thermal duct-lining role. |
| Acoustic comfort | 5 | High | Internal duct sound control is core. |
| Sustainability | 4 | Medium | Verify recycled-content/EPD scope for exact line. |
| Installation practicality | 4 | Medium | Flexible lining conforms to ducts; fabrication quality is critical. |
| Compliance readiness | 3 | Medium | Exact fire, erosion, hygiene and air-velocity scope must match. |
| BAL suitability | Gate | High | Not a family-level BAL product. |

## Mandatory inputs and boundaries

Capture duct dimensions, internal lining area, thickness/R-value, air velocity, operating temperature, condensation risk, noise target, facing/surface, fire/hygiene requirement and access for fabrication. Do not promise room NC/NR, insertion loss or system R-value without the tested design. Adhesive/pins, joints, exposed edges and transitions must follow current instructions.

## Approved bot language

> FI24 is the flexible internal ductliner family when both HVAC thermal and duct-noise control matter. Exact thickness, facing, air-velocity suitability and product code need confirmation from the current duct design.

## Source

[Fletcher FI24 Flexible Ductliner](https://insulation.com.au/product/fi24-flexible-ductliner/)

```json
{"family_id":"FLETCHER_FI24_FLEX_DUCTLINER","recommendation_level":"family_only","best_for":["internal sheet-metal duct lining","duct sound attenuation"],"spreadsheet_exception":"FI22 FLEX DLINER identity requires review","required_inputs":["duct_size","thickness","air_velocity","temperature","noise_target","fire_hygiene"],"human_gates":["sku","FI22_alias","fabrication","system_performance","BAL"]}
```
