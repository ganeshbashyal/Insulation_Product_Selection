---
id: thermotec-e-therm
family_id: THERMOTEC_E_THERM
manufacturer: Thermotec Australia
canonical_name: Thermotec E-Therm Reflective Roof and Wall Insulation
category: Reflective insulation
validation_status: manufacturer_supported_system_metrics_pending
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/thermotec-e-therm-roof-wall-insulation
---

# Thermotec E-Therm Reflective Roof and Wall Insulation

## Bot-ready summary

Thermotec E-Therm is double-sided reflective foam insulation for roofs, walls and underfloor applications. Thermotec markets it for houses, metal-roof sheds, warehouses and other construction where reflective thermal insulation and moisture resistance are required.

Published shop variants include nominal 5, 7 and 8 mm products, with a listed roll format of 1350 mm × 22.2 m for the selected 5 mm option.

## Selection logic

- Identify roof, wall or underfloor use.
- Confirm the required total system R-value and the direction/size of adjacent air spaces.
- Confirm vapour, condensation, waterproofing, facing direction and fire requirements.
- Select thickness and roll quantity from the exact current product option.

## Limitations

- Reflective-insulation R-values depend on the complete installed system and air spaces.
- Do not apply a generic `R1.2` to every E-Therm roll.
- Do not describe E-Therm as bulk glasswool, MLV or standalone acoustic barrier.
- Claims about waterproofing, condensation control or replacement of bulk insulation must be checked against the project detail and current TDS.

## Approved bot language

> Thermotec E-Therm is a double-sided reflective foam insulation product used in roof, wall and underfloor systems, including houses, sheds and warehouses. Its thermal result depends on the complete construction and adjacent air spaces, so selection should be based on the required system R-value rather than a generic product R-value.

## Source

[Thermotec E-Therm Reflective Roof and Wall Insulation](https://thermotec.com.au/products/thermotec-e-therm-roof-wall-insulation)

## Deep-dive decision guidance

E-Therm is double-sided reflective foam intended for suitable roof, wall and underfloor systems, particularly metal roofs and sheds. Its role combines a reflective surface with a foam core and water-resistant layer. Reflective performance depends on orientation to an appropriate airspace; never quote a universal system Total R-value from the product name alone.

Use E-Therm where a reflective/foam layer matches the construction and condensation strategy. Use bulk Pink Batts/SupaBATT-type products where cavity material R-value is the primary need. In a hybrid system, both may be useful, but added R-values must follow the applicable calculation method rather than simple marketing arithmetic.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 4 | Medium | Relevant when installed with the documented airspace/construction. |
| Acoustic comfort | 2 | Low | Do not infer rain-noise or Rw performance. |
| Sustainability | 3 | Low | No current quantified EPD is linked. |
| Installation practicality | 4 | Medium | Flexible sheet format; laps, airspace and penetrations matter. |
| Compliance readiness | 2 | Medium | System R-value and condensation design require project evidence. |
| BAL suitability | Gate | High | Reflective facing is not BAL evidence. |

Capture roof/wall/floor location, metal/tile construction, climate zone, airspace geometry, bulk insulation, condensation/vapour strategy, exposure, fire/BAL requirements and target Total R-value. Recommend the family only after confirming the assembly can provide the required airspace.

```json
{"family_id":"THERMOTEC_E_THERM","recommendation_level":"family_only","best_for":["reflective roof system","metal shed","wall or underfloor reflective layer"],"required_inputs":["element","construction","climate_zone","airspace","bulk_insulation","target_total_r","condensation_strategy"],"human_gates":["system_r_calculation","installation_detail","compliance","BAL"]}
```
