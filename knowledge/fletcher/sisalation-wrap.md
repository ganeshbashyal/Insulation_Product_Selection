---
family_id: FLETCHER_SISALATION_WRAP
manufacturer: Fletcher Insulation
canonical_name: Sisalation Wrap and Foil Membrane Families
category: Building membranes and reflective foils
validation_status: manufacturer_supported_subfamily_selection_required
last_validated: 2026-09-04
recommendation_scope: subfamily_only
official_guide_url: https://insulation.com.au/wp-content/uploads/2025/Sisalation_Products_2025_LR.pdf
---

# Sisalation Wrap and Foil Membrane Families

## Canonical description

This catalogue family contains several distinct membranes, including products such as Tuff Wrap and Multipurpose. They differ in duty, permeability, water-barrier role, reflective facing, application and exposure. “Sisalation” is a brand/range label, not enough information for product selection.

## Selection workflow

First identify wall, roof, shed or other application. Then determine required vapour classification, water-barrier duty, reflective airspace, strength/duty, UV exposure, wind region and fire/BAL construction. Use the 2025 selection guide and exact TDS to choose the subfamily. Keep Vapawrap Wall and Vapawrap Metal Roof as separate dedicated records.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Moisture/comfort | 4 | Medium | Many members manage water/vapour, but properties differ. |
| Energy efficiency | 3 | Medium | Reflective products require a defined airspace/system. |
| Sustainability | 3 | Low | No single environmental score applies to all subfamilies. |
| Installation practicality | 4 | Medium | Roll products are familiar; product-specific laps/tapes matter. |
| Compliance readiness | 3 | Medium | Strong documentation exists only after subfamily identification. |
| BAL suitability | Gate | High | Apply only exact product and construction evidence. |

## Bot safeguards

Never describe all Sisalation as vapour permeable, impermeable, reflective, fire-rated or BAL suitable. Capture exact sheet row/code, application, cladding/roof, climate, vapour class, exposure, airspace, wind and BAL. Recommend a subfamily only when the selection guide resolves it; otherwise collect the enquiry.

## Sources

- [Sisalation 2025 product selection guide](https://insulation.com.au/wp-content/uploads/2025/Sisalation_Products_2025_LR.pdf)
- [Sisalation Tuff Wrap](https://insulation.com.au/product/sisalation-tuff-wrap/)
- [Sisalation Multipurpose](https://insulation.com.au/product/sisalation-multipurpose/)

```json
{"family_id":"FLETCHER_SISALATION_WRAP","recommendation_level":"subfamily_only","required_inputs":["exact_name_or_code","application","vapour_class","water_barrier","airspace","uv_exposure","wind_region","BAL"],"human_gates":["subfamily","sku","installation","system_r","compliance","BAL"]}
```
