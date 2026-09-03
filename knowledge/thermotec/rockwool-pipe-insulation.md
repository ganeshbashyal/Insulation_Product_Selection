---
id: thermotec-rockwool-pipe
family_id: THERMOTEC_ROCKWOOL_PIPE
manufacturer: Thermotec Australia
canonical_name: Thermotec Rockwool Pipe Insulation
category: High-temperature pipe insulation
material: Foil-faced pre-formed rockwool
validation_status: manufacturer_supported
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/thermotec-rockwool-pipe-insulation
---

# Thermotec Rockwool Pipe Insulation

## Bot-ready summary

Thermotec Rockwool Pipe Insulation is heavy-duty, foil-faced, pre-formed mineral-wool pipe lagging for industrial and commercial services, including steam and other continuously high-temperature lines.

Thermotec publishes a nominal density range of 115–140 kg/m³ and a maximum continuous service temperature of 650°C.

## Selection logic

- Match the sectional insulation internal diameter to the pipe outside diameter.
- Select wall thickness using the thermal design, service temperature and personnel/surface-temperature requirements.
- Confirm facing, joint treatment, supports, weather protection and corrosion-under-insulation controls.
- Use this family for high-temperature mineral-wool pipe insulation, not as an acoustic Rw product.

## Limitations

- A product label such as `RW 120 kg` describes density, not an Rw acoustic rating.
- Do not populate `Acoustic Rw = 120`.
- Do not infer a product R-value from density.
- Confirm the exact service-temperature limit and facing requirements in the current TDS for the specified configuration.

## Approved bot language

> Thermotec Rockwool Pipe Insulation is foil-faced pre-formed mineral-wool lagging for industrial and commercial high-temperature services. The published 115–140 kg/m³ figure is density, not an acoustic Rw rating. Select the internal diameter and wall thickness for the pipe size, service temperature and thermal design.

## Source

[Thermotec Rockwool Pipe Insulation](https://thermotec.com.au/products/thermotec-rockwool-pipe-insulation)

## Deep-dive decision guidance

Thermotec describes preformed foil-faced rockwool/mineral-wool pipe sections for commercial and industrial service, with nominal density 115–140 kg/m³ and service temperature up to 650 °C. Density describes mass per volume; it is neither material R-value nor Rw. Thermal performance depends on thickness, mean temperature and pipe geometry.

Choose this family for high-temperature/process/steam duties that exceed elastomeric limits. E-Flex ST/HT and 4-Zero are generally more practical for lower-temperature closed-cell condensation-control duties. The foil facing is not automatically weatherproof cladding; confirm jacketing for the actual environment.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Strong high-temperature thermal fit. |
| Acoustic comfort | 3 | Low | Fibrous mass may assist systems, but no product Rw is inferred. |
| Sustainability | 3 | Low | No project-specific EPD is linked here. |
| Installation practicality | 2 | Medium | Sections, joints and jacketing need skilled detailing. |
| Compliance readiness | 3 | Medium | Temperature/material evidence exists; system evidence still needed. |
| BAL suitability | Gate | High | Non-combustibility/BAL claims require exact evidence and assembly. |

Capture pipe OD, service, operating/maximum temperature, insulation thickness, location, moisture/chemical exposure, jacketing, personnel-protection requirement and specification. Family recommendation only; engineering selects thickness, facing and SKU.

```json
{"family_id":"THERMOTEC_ROCKWOOL_PIPE","recommendation_level":"family_only","density_kg_m3":"115-140","documented_max_temperature_c":650,"required_inputs":["pipe_od","service","temperature","thickness","environment","jacketing"],"human_gates":["sku","thermal_design","material_compatibility","fire_evidence","BAL"]}
```
