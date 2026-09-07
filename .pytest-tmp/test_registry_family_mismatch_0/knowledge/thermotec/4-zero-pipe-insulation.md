---
id: thermotec-4-zero
family_id: THERMOTEC_4_ZERO
manufacturer: Thermotec Australia
canonical_name: Thermotec 4-Zero Fire Retardant Pipe Insulation
category: Thermal pipe insulation
material: Closed-cell pipe insulation with reinforced aluminium covering
validation_status: manufacturer_supported
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/thermotec-4-zero
---

# Thermotec 4-Zero Fire Retardant Pipe Insulation

## Bot-ready summary

Thermotec 4-Zero is thermal pipe insulation with a factory-applied reinforced aluminium covering. Thermotec positions the covering as providing improved fire performance in accordance with AS 1530.3 and states that the product meets Green Star low-VOC requirements.

The current published range uses 1000 mm lengths with 25 mm insulation wall thickness. Product sizing is stated by internal diameter, so the selected size must match the pipe outside diameter.

## Selection logic

- Match the published internal diameter to the actual pipe outside diameter.
- Confirm service temperature, condensation risk, location and required fire documentation.
- Calculate quantity from straight pipe length, then allow separately for bends, valves, fittings and waste.
- Use the exact bag quantity associated with the selected diameter.

## Current published sizes

Internal diameters: 13, 20, 25, 32, 39, 51, 65, 76, 89 and 102 mm. Each published item has a 25 mm wall thickness and 1000 mm length.

## Limitations

- Do not apply a generic `R1.2` to every 4-Zero size. Thermal resistance depends on thickness, pipe geometry and service conditions.
- Do not call 4-Zero an acoustic MLV product.
- Do not treat the internal diameter as product width.
- Quote exact fire indices or thermal conductivity only from the current TDS/test report.

## Approved bot language

> Thermotec 4-Zero is reinforced, fire-performance-focused thermal pipe insulation supplied in 1 m lengths. Select it by matching the listed internal diameter to the pipe outside diameter and confirm the service-temperature, condensation and fire requirements. A single generic R-value should not be applied across the range.

## Source

[Thermotec 4-Zero Fire Retardant Pipe Insulation](https://thermotec.com.au/products/thermotec-4-zero)

## Deep-dive decision guidance

The current page describes closed-cell thermal pipe insulation with a factory-applied reinforced aluminium cover, tested in an AS 1530.3 context and supported by a Green Star low-VOC statement. Current listed sizes are 13, 20, 25, 32, 39, 51, 65, 76, 89 and 102 mm internal diameter, each with 25 mm wall thickness and 1,000 mm length. Internal diameter is not pipe outside diameter; confirm fit before quoting.

Choose 4-Zero where thermal/condensation control and its documented facing/fire-performance context are important. Choose E-Flex ST for a broader general-service elastomeric range, E-Flex HT for higher-temperature or UV/weather exposure, and Rockwool Pipe for industrial temperatures beyond elastomeric limits.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Primary function is reducing pipe heat flow. |
| Acoustic comfort | 2 | Low | Any noise benefit is secondary and not an Rw claim. |
| Sustainability | 3 | Medium | Low-VOC evidence is relevant but not a whole-life result. |
| Installation practicality | 4 | Medium | Factory facing and standard lengths help; fit and joints matter. |
| Compliance readiness | 4 | Medium | Useful test context exists, but the exact clause/system must match. |
| BAL suitability | Gate | High | No automatic BAL recommendation. |

Capture pipe outside diameter, fluid, normal/maximum temperature, ambient humidity, indoor/outdoor location, insulation thickness, facing continuity, fire clause and quantity. Recommend the family only; thickness, SKU, condensation calculation and compliance remain human gates.

```json
{"family_id":"THERMOTEC_4_ZERO","recommendation_level":"family_only","current_range":{"length_mm":1000,"wall_mm":25,"internal_diameter_mm":[13,20,25,32,39,51,65,76,89,102]},"required_inputs":["pipe_od","fluid","temperature","ambient","exposure","fire_clause"],"human_gates":["fit","sku","thermal_design","condensation","compliance","BAL"]}
```
