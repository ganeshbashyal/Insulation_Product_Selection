---
family_id: FLETCHER_VAPAWRAP_WALL
manufacturer: Fletcher Insulation
canonical_name: Sisalation Vapawrap Residential Wall Wrap
category: Vapour-permeable wall membrane
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/sisalation-vapawrap-residential-wall-wrap/
---

# Sisalation Vapawrap Residential Wall Wrap

## Canonical description

Vapawrap Residential Wall Wrap is a vapour-permeable wall membrane used behind suitable external claddings as a water barrier and part of the air/moisture-control strategy. Fletcher describes a Class 4 vapour-permeable product with current variants differentiated in part by allowable UV exposure before cladding (including 30- and 90-day contexts). Confirm the exact variant and TDS.

## Selection logic

Use where the wall condensation design requires outward drying/vapour permeability. Do not substitute an impermeable foil or roof-specific membrane based only on roll size. A membrane does not replace bulk insulation. Its reflective contribution, if any, requires a defined airspace and system calculation.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Moisture/comfort | 5 | High | Water control and vapour permeability are primary. |
| Energy efficiency | 3 | Medium | Air/water control helps the system; no generic R-value. |
| Sustainability | 3 | Low | Durability matters; no family EPD is cited here. |
| Installation practicality | 4 | Medium | Roll format; laps, penetrations and exposure time are critical. |
| Compliance readiness | 4 | Medium | Classification/BAL statements apply only within exact scope. |
| BAL suitability | Gate | High | Use the documented wall construction, not a blanket BAL 0–FZ claim. |

## Mandatory inputs

Capture climate zone, wall/cladding type, cavity, condensation design, required vapour class, weather exposure, UV exposure duration, wind region, fire/BAL requirement, roll width and compatible tape/flashing. Tears and incomplete laps/penetrations must be repaired per current instructions.

## Approved bot language

> Vapawrap Wall is the Fletcher vapour-permeable wall membrane family for suitable drained cladding systems. We will confirm the variant, exposure period, vapour class and BAL/construction detail before quote.

## Source

[Fletcher Vapawrap Residential Wall Wrap](https://insulation.com.au/product/sisalation-vapawrap-residential-wall-wrap/)

```json
{"family_id":"FLETCHER_VAPAWRAP_WALL","recommendation_level":"family_only","documented_vapour_class":4,"required_inputs":["climate_zone","cladding","cavity","condensation_design","uv_exposure_days","wind_region","BAL"],"human_gates":["variant","roll_sku","installation_detail","compliance","BAL"]}
```
