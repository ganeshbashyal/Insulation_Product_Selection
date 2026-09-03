---
family_id: FLETCHER_PINK_BATTS_CEILING
manufacturer: Fletcher Insulation
canonical_name: Pink Batts Ceiling Insulation
category: Glasswool ceiling batt
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/pink-batts-ceiling-insulation/
---

# Pink Batts Ceiling Insulation

## Canonical description and current range

Australian-made FBS-1 glasswool ceiling batts for residential and similar ceiling spaces. Fletcher documents non-combustibility, up to 80% recycled content, consumer lifetime warranty and CodeMark CM30006 within scope. The current national range lists material R2.5 (130 mm), R3.0 (155 mm), R3.5 (175 mm), R4.1 (215 mm), R5.0 (220 mm), R6.0 (250 mm) and R7.0 (285 mm), with separate WA notes/variants.

## Selection logic and metric discipline

Use where ceiling heat flow and energy comfort are primary. Select by the energy report/climate goal, available depth, joist spacing, access and clearances—not by “highest R” alone. Material R-value belongs to the batt; Total R-value belongs to the complete roof/ceiling. Acoustic contribution is secondary and no standalone ceiling Rw should be invented.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Core ceiling application. |
| Acoustic comfort | 3 | Medium | Fibrous absorption can help systems. |
| Sustainability | 4 | High | Up to 80% recycled content and EPD evidence. |
| Installation practicality | 4 | Medium | Standard batt format; roof access and clearances matter. |
| Compliance readiness | 4 | Medium | Product evidence exists; installation and regional scope must match. |
| BAL suitability | Gate | High | Complete roof/ceiling construction determines BAL. |

## Mandatory inputs and safeguards

Capture target material/Total R, joist spacing, available depth, roof type, climate zone, downlights/heat sources, ventilation, existing insulation, access, state and BAL/fire needs. Avoid gaps and compression; maintain mandated clearances and electrical safety. Wet or damaged insulation requires assessment.

## Approved bot language

> Pink Batts Ceiling is the Fletcher family for ceiling thermal performance. The right batt depends on the required R-value, available depth, spacing, services and region; we will confirm the exact code before quote.

## Sources

- [Fletcher product page and current specifications](https://insulation.com.au/product/pink-batts-ceiling-insulation/)
- [Fletcher glasswool EPD](https://insulation.com.au/wp-content/uploads/2025/07/EPD-IES-0023072-001-Fletcher-Insulation-Wall-and-floor-Insulation-products-2025-06-11.pdf)

```json
{"family_id":"FLETCHER_PINK_BATTS_CEILING","recommendation_level":"family_only","current_range":{"R2.5":130,"R3.0":155,"R3.5":175,"R4.1":215,"R5.0":220,"R6.0":250,"R7.0":285},"required_inputs":["target_r","joist_spacing","available_depth","roof_type","climate_zone","state"],"human_gates":["sku","clearances","regional_availability","total_r","BAL"]}
```
