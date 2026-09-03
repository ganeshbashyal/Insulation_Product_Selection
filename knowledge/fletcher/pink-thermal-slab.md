---
family_id: FLETCHER_PINK_THERMAL_SLAB
manufacturer: Fletcher Insulation
canonical_name: Pink Thermal Slab
category: Foil-faced semi-rigid glasswool slab
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/pink-thermal-slab/
---

# Pink Thermal Slab

## Canonical description and range

Pink Thermal Slab is semi-rigid foil-faced glasswool for suitable soffits, concrete floors, walls and roof applications. The current Fletcher range lists R1.5 at 50 mm, R2.0 at 68 mm, R2.2 at 75 mm and R3.0 at 100 mm. These are material R-values; the completed slab/soffit construction has a separate Total R-value.

## Selection logic

Use where a robust semi-rigid faced board is required against concrete or in a specified commercial construction. FI32 is the broader fabrication/HVAC family with multiple facings; Pink Batts are cavity batts; Permastop is a flexible roof blanket. Confirm whether the foil faces an airspace, is a vapour control layer, or is simply protective—those functions are not interchangeable.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Direct slab/soffit thermal application. |
| Acoustic comfort | 3 | Medium | Glasswool can contribute within the assembly. |
| Sustainability | 4 | Medium | Verify current glasswool EPD and facing scope. |
| Installation practicality | 3 | Medium | Semi-rigid format is useful; fixing and edges require design. |
| Compliance readiness | 4 | Medium | Current range evidence exists; system/fire fixing details matter. |
| BAL suitability | Gate | High | Complete external construction determines BAL. |

## Mandatory inputs

Capture substrate/location, exposed or concealed finish, target R-value, panel size, fixings, airspace/vapour strategy, moisture/exposure, fire specification and desired appearance. Do not leave facing, joints or cut edges in an unapproved condition.

## Approved bot language

> Pink Thermal Slab is the Fletcher semi-rigid foil-faced family for suitable soffit and concrete applications. We will confirm R-value, thickness, fixing, facing orientation and fire requirements for the complete construction.

## Source

[Fletcher Pink Thermal Slab](https://insulation.com.au/product/pink-thermal-slab/)

```json
{"family_id":"FLETCHER_PINK_THERMAL_SLAB","recommendation_level":"family_only","current_range":{"R1.5":50,"R2.0":68,"R2.2":75,"R3.0":100},"required_inputs":["application","substrate","target_r","fixing","facing_role","exposure","fire_requirement"],"human_gates":["sku","total_r","fixing_design","facing_continuity","BAL"]}
```
