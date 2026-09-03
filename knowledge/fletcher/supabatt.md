---
family_id: FLETCHER_SUPABATT
manufacturer: Fletcher Insulation
canonical_name: SupaBATT Insulation
category: Glasswool batt
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/supabatt/
---

# SupaBATT Insulation

## Canonical description

SupaBATT is Fletcher's glasswool batt family for thermal and acoustic contribution in suitable building cavities. Treat each wall/ceiling/application and R-value as a distinct SKU even when the brand is shared. Manufacturer-supported claims such as recycled content, fire performance, warranty or certification must be checked against the current product page/TDS scope.

## Selection position

Use SupaBATT where the project or channel specifies this range and its dimensions/R-values suit the cavity. Do not assume it is interchangeable with Pink Batts, Soundbreak or Pink Partition: compare application, density, thickness, width, certification, region and commercial availability. For acoustic-first separating walls, Soundbreak is the stronger purpose-led starting point.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | Medium | Strong bulk-insulation role; exact SKU matters. |
| Acoustic comfort | 3 | Medium | Useful system contribution, not standalone Rw. |
| Sustainability | 4 | Medium | Confirm product scope of recycled content/EPD. |
| Installation practicality | 4 | Medium | Batt format; cavity fit controls result. |
| Compliance readiness | 3 | Medium | Verify current TDS/certification for selected SKU. |
| BAL suitability | Gate | High | No family-only BAL conclusion. |

## Mandatory inputs

Capture building element, frame material, centres, cavity depth, target R-value, state, climate/condensation design, acoustic target and fire/BAL clauses. Escalate exact SKU where current product table and spreadsheet disagree or a legacy code appears.

## Approved bot language

> SupaBATT may suit this cavity as a thermal batt family. Before quoting, we will match the exact application, R-value, thickness and width to the current Fletcher range and your project requirements.

## Source

[Fletcher SupaBATT](https://insulation.com.au/product/supabatt/)

```json
{"family_id":"FLETCHER_SUPABATT","recommendation_level":"family_only","required_inputs":["building_element","frame","centres","cavity_depth","target_r","state"],"compare_with":["FLETCHER_PINK_BATTS_WALL","FLETCHER_PINK_BATTS_CEILING","FLETCHER_SOUNDBREAK"],"human_gates":["sku","range_scope","certification","total_r","BAL"]}
```
