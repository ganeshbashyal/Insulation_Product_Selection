---
family_id: FLETCHER_FI32_SEMI_RIGID
manufacturer: Fletcher Insulation
canonical_name: FI32 Semi Rigid Insulation
category: HVAC and commercial glasswool board/roll
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/fi32-semi-rigid-insulation/
---

# FI32 Semi Rigid Insulation

## Canonical description

FI32 is semi-rigid glasswool supplied as boards or rolls for internal sheet-metal duct lining and other commercial/industrial thermal-acoustic uses such as tanks, process vessels, cabinets, plant rooms and acoustic baffles. Current facing choices include unfaced, Vapastop 883 foil, Sisalation heavy-duty/perforated foil and black matt tissue. Fletcher states up to 80% recycled glass, Australian manufacture and CodeMark CM30006 within scope.

## Range interpretation

The live table spans board and roll formats, several facings, nominal thicknesses 25–100 mm and material R-values approximately R0.71–R3.0 depending on configuration. Match format, thickness, facing and dimensions exactly. Perforated foil and black tissue serve different acoustic/air-stream purposes from sealed vapour-facing foil.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Thermal duct/equipment insulation is primary. |
| Acoustic comfort | 4 | High | Documented duct-lining/acoustic-baffle use. |
| Sustainability | 4 | Medium | Up to 80% recycled glass; verify HVAC EPD scope. |
| Installation practicality | 3 | Medium | Many formats help but fabrication/facing details matter. |
| Compliance readiness | 4 | Medium | Product evidence exists; air-stream/fire/system scope must match. |
| BAL suitability | Gate | High | Not an automatic building-envelope BAL solution. |

## Selection and safeguards

Capture duct/equipment type, internal or external lining, dimensions, air velocity, temperature, condensation/vapour-control need, acoustic target, required R-value, facing, fire/hygiene specification and environment. Do not use material R-value as duct-system Total R or board density as Rw. Damage, exposed edges, wrong facing and poor joints can compromise the design.

## Approved bot language

> FI32 is a semi-rigid thermal-acoustic glasswool family for duct lining and commercial equipment applications. We will match the board/roll, thickness and facing to the air-stream, condensation, acoustic and fire requirements before quoting.

## Source

[Fletcher FI32 current product page and range](https://insulation.com.au/product/fi32-semi-rigid-insulation/)

```json
{"family_id":"FLETCHER_FI32_SEMI_RIGID","recommendation_level":"family_only","formats":["board","roll"],"facings":["unfaced","Vapastop 883","HD perforated foil","HD foil","black matt tissue"],"required_inputs":["application","air_stream","temperature","condensation","acoustic_target","facing"],"human_gates":["sku","fabrication","air_velocity","fire_hygiene","BAL"]}
```
