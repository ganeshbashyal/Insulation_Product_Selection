---
id: thermotec-e-flex-st
family_id: THERMOTEC_E_FLEX_ST
manufacturer: Thermotec Australia
brand: E-Flex
product_family: E-Flex ST Pipe Insulation
canonical_name: Thermotec E-Flex ST Hot Water, HVAC and Refrigeration Pipe Insulation
category: Pipe insulation
material: Elastomeric closed-cell foam
validation_status: manufacturer_supported
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/thermotec-e-flex-st-hot-water-hvac-refrigeration-pipe-insulation
---

# Thermotec E-Flex ST Pipe Insulation

## Bot-ready summary

Thermotec E-Flex ST is flexible elastomeric closed-cell foam pipe insulation for HVAC, refrigeration, general plumbing and hot-water services. The manufacturer states that it can be used continuously at temperatures up to 110°C.

The published range covers internal diameters from 9 mm to 114 mm and wall thicknesses from 9 mm to 38 mm. Standard tubes are 2 m long; continuous coils and self-seal versions are available in selected sizes.

E-Flex ST and E-Flex HT are different product families. ST is the general HVAC, refrigeration and plumbing range. HT is the EPDM range intended for higher temperatures and stronger outdoor UV/weather exposure.

## Selection rules

- Select the internal diameter to fit the pipe outside diameter.
- Select wall thickness from the thermal, condensation-control and regulatory design requirements.
- Confirm whether the required format is a 2 m tube, continuous coil, sheet or self-seal product.
- Confirm operating temperature and whether the installation is outdoors or exposed to UV or physical damage.
- Use E-Flex HT rather than assuming ST is suitable when the service temperature or exposure exceeds the ST documentation.

## Limitations and warnings

- Do not assign one generic thermal R-value to the full range. Thermal resistance varies with pipe diameter, insulation thickness and service conditions.
- Do not copy E-Flex HT temperature or UV claims to E-Flex ST.
- Do not use an `Rw` acoustic rating for this family unless a product-specific acoustic source supports it.
- Fire-test language must retain the cited test or classification context; do not translate a component result into a whole-building compliance claim.
- Confirm the current technical data sheet and project specification before final selection.

## Approved bot language

> Thermotec E-Flex ST is flexible closed-cell elastomeric pipe insulation for HVAC, refrigeration, general plumbing and hot-water services. It is available in multiple internal diameters and wall thicknesses, with tubes, selected coils and self-seal formats. Select it by pipe size, required insulation thickness, operating temperature and exposure conditions; do not apply one generic R-value across the complete range.

## Official source

[Thermotec E-Flex ST product page](https://thermotec.com.au/products/thermotec-e-flex-st-hot-water-hvac-refrigeration-pipe-insulation)

## Deep-dive decision guidance

E-Flex ST is closed-cell elastomeric foam for HVAC, refrigeration, hot-water and general plumbing. The current page states continuous use to 110 °C, internal diameters from 9 to 114 mm, wall thicknesses from 9 to 38 mm, 2 m tubes, and selected continuous-coil/self-seal options. It references AS/NZS 1530.3/BCA and NFPA 274 FRV testing; quote the exact result only from the applicable report.

This family is the general-service choice. Move to E-Flex HT when actual temperature, solar duty, UV or weather exposure requires the EPDM higher-temperature family. Move to Rockwool Pipe for high industrial temperatures. Use 4-Zero when its factory aluminium facing and documented test context are specified.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Primary thermal-service function. |
| Acoustic comfort | 2 | Low | Do not invent an acoustic rating. |
| Sustainability | 3 | Low | No family EPD is linked in this record. |
| Installation practicality | 5 | High | Broad sizes, tube/coil and selected self-seal formats. |
| Compliance readiness | 3 | Medium | Test references require application-specific verification. |
| BAL suitability | Gate | High | No family-level BAL claim. |

Capture pipe OD, service/fluid, operating and peak temperature, ambient design, indoor/outdoor exposure, required thickness, vapour-seal continuity and format preference. Never assign one generic R-value to this family: resistance varies with thickness, pipe geometry and temperature.

```json
{"family_id":"THERMOTEC_E_FLEX_ST","recommendation_level":"family_only","documented_limit_c_continuous":110,"range":{"id_mm":"9-114","wall_mm":"9-38","tube_length_m":2},"required_inputs":["pipe_od","fluid","temperature","ambient","exposure","thickness"],"human_gates":["sku","thermal_design","condensation","fire_report_scope","BAL"]}
```
