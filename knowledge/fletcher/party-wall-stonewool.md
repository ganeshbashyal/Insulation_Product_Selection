---
family_id: FLETCHER_PARTY_WALL_STONEWOOL
manufacturer: Fletcher Insulation
canonical_name: Fletcher Protect Party Wall Stonewool
category: Party-wall stonewool system components
validation_status: manufacturer_supported_system_selection_required
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/fletcher-protect-party-wall-stonewool-batts/
---

# Fletcher Protect Party Wall Stonewool

## Canonical description

This family groups Fletcher Protect stonewool components used in specified party-wall/fire/acoustic systems, including party-wall batts, foil-faced stonewool blanket and Fire Stop party-wall batts. These are not one interchangeable SKU. Their role depends on the proprietary/tested wall detail, location within the system, thickness, density, facing and required fire/acoustic performance.

## System rule

Recommend only as a family when the customer has a party-wall system or recognised detail. Never promise an FRL, Rw/Rw+Ctr or BAL result from the insulation component alone. Plasterboard, shaftliner, framing, junctions, roof-space continuation, penetrations, cavity barriers and workmanship determine the system result.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Compliance/fire | 5 | High | Core use is within documented party-wall/fire systems. |
| Acoustic comfort | 4 | High | Important system contribution. |
| Energy efficiency | 3 | Medium | Thermal contribution varies by component/system. |
| Sustainability | 3 | Low | Confirm applicable stonewool environmental evidence. |
| Installation practicality | 2 | Medium | Detail-critical system components. |
| BAL suitability | Gate | High | Party-wall fire evidence is not automatically BAL evidence. |

## Mandatory inputs and source hierarchy

Capture exact system/detail number, wall type, required FRL, acoustic target, storeys, roof/junction condition, penetrations, component description, thickness/facing and project specification. The system manual/test report outranks a reseller row.

## Sources

- [Party Wall Stonewool Batts](https://insulation.com.au/product/fletcher-protect-party-wall-stonewool-batts/)
- [Foil Faced Party Wall Stonewool Blanket](https://insulation.com.au/product/fletcher-protect-party-wall-foil-faced-stonewool-blanket/)
- [Fire Stop Party Wall Batts](https://insulation.com.au/product/fire-stop-party-wall-batts/)

```json
{"family_id":"FLETCHER_PARTY_WALL_STONEWOOL","recommendation_level":"family_only_with_system_reference","components":["party wall batts","foil-faced blanket","fire stop batts"],"required_inputs":["system_reference","wall_type","FRL","acoustic_target","junctions","penetrations"],"human_gates":["component_sku","tested_system","frl","rw","BAL"]}
```
