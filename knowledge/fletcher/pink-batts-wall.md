---
family_id: FLETCHER_PINK_BATTS_WALL
manufacturer: Fletcher Insulation
canonical_name: Pink Batts Wall Insulation
category: Glasswool wall batt
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/pink-batts-insulation/
---

# Pink Batts Wall Insulation

## Canonical description

Australian-made FBS-1 biosoluble glasswool batts for external and internal wall cavities. Fletcher documents thermal insulation, acoustic contribution, non-combustibility, up to 80% recycled content, a consumer lifetime warranty and CodeMark CM30006, subject to the certificate scope. The current national page lists material R-values R1.5, R2.0, R2.0 HD, R2.5 HD and R4.0 HD; WA-only lines and availability notes must be preserved.

## Selection logic

Recommend this family when wall energy efficiency is primary and a batt fits the cavity. Prefer Soundbreak when separating-wall acoustic comfort is the main brief; prefer Pink Partition for commercial partition systems; use a membrane family separately for water/vapour/air control. Higher material R-value is not automatically better if the batt is compressed or does not fit.

Material R-value is the tested resistance of the batt. Total R-value is for the complete wall. Rw/Rw+Ctr is for a tested acoustic assembly. Never copy one into another column.

## Priority ratings

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Primary wall-cavity function. |
| Acoustic comfort | 3 | Medium | Helpful within systems; not a standalone wall Rw. |
| Sustainability | 4 | High | Manufacturer states up to 80% recycled content; EPD supports eligible ranges. |
| Installation practicality | 4 | High | Firm-fit batt; cavity dimensions remain critical. |
| Compliance readiness | 4 | Medium | CodeMark/non-combustibility evidence exists; check exact SKU/scope. |
| BAL suitability | Gate | High | Non-combustible product does not establish wall-system BAL compliance. |

## Mandatory inputs and failure modes

Capture timber/steel frame, stud centres, clear cavity depth, wall type, target material R-value/Total R-value, climate zone, condensation design, state and fire/BAL requirements. Compression, gaps, services, wetting and incorrect width reduce performance. WA-only codes without the national CodeMark scope require explicit handling.

## Approved bot language

> Pink Batts Wall is a strong starting family for thermal performance in a compatible wall cavity. I can narrow the family now; the exact R-value, thickness, width and regional code need confirmation against your frame and compliance design.

## Sources

- [Fletcher product page and current range](https://insulation.com.au/product/pink-batts-insulation/)
- [Fletcher glasswool environmental declaration](https://insulation.com.au/wp-content/uploads/2025/07/EPD-IES-0023072-001-Fletcher-Insulation-Wall-and-floor-Insulation-products-2025-06-11.pdf)

```json
{"family_id":"FLETCHER_PINK_BATTS_WALL","recommendation_level":"family_only","best_for":["external wall thermal insulation","internal wall thermal insulation"],"current_material_r":["R1.5","R2.0","R2.0 HD","R2.5 HD","R4.0 HD"],"required_inputs":["frame","stud_centres","cavity_depth","target_r","climate_zone","state"],"human_gates":["sku","regional_availability","total_r","condensation","BAL"]}
```
