---
id: thermotec-maxtape-fr
family_id: THERMOTEC_MAXTAPE_FR
manufacturer: Thermotec Australia
canonical_name: Thermotec MaxTape FR Insulating Foam Tape
category: Insulation accessory
material: Adhesive-backed closed-cell EPDM foam
validation_status: manufacturer_supported_classification_pending
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/thermotec-maxflex-insulating-foam-tape
---

# Thermotec MaxTape FR Insulating Foam Tape

## Bot-ready summary

MaxTape FR is an adhesive-backed closed-cell EPDM foam tape used as an insulation and sealing accessory. Thermotec states that it has low thermal conductivity and is intended to help limit heat loss, heat gain and condensation. It can also be used as purlin tape to reduce thermal-movement noise on steel-framed buildings.

Published shop options include 3 mm thickness, 50 or 98 mm width and 9.1 m roll length.

## Selection logic

- Confirm whether the tape is being used for insulation continuity, condensation control, joint sealing or purlin isolation.
- Match width and thickness to the adjoining insulation and substrate.
- Ensure the substrate is compatible with the acrylic pressure-sensitive adhesive and prepared as required.
- Calculate roll quantity from joint length plus laps and waste.

## Limitations

- MaxTape is an accessory, not a standalone insulation system.
- Do not assign it an R-value, Rw or NRC copied from another Thermotec product.
- Thermotec describes the product as fire rated; quote an exact classification only after checking the current test report/TDS.
- Adhesive performance depends on substrate condition, preparation, temperature and installation.

## Approved bot language

> Thermotec MaxTape FR is closed-cell EPDM insulating foam tape with an acrylic pressure-sensitive adhesive. It is used to support insulation continuity, condensation control and purlin isolation. Select the tape width and thickness for the adjoining system; do not treat it as having a standalone R-value or acoustic rating.

## Source

[Thermotec MaxTape FR Insulating Foam Tape](https://thermotec.com.au/products/thermotec-maxflex-insulating-foam-tape)

## Deep-dive decision guidance

MaxTape FR is closed-cell EPDM insulating foam tape with acrylic pressure-sensitive adhesive. It supports insulation continuity, local condensation control, thermal-break detailing and purlin isolation/thermal-movement noise. It is an accessory, not a substitute for correctly sized pipe insulation, a complete vapour barrier or an acoustic barrier.

The product page uses fire-related wording, but the exact report/classification and field of application must be attached before the bot repeats a compliance result. Adhesive suitability also depends on substrate preparation, temperature, exposure and service conditions.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 3 | Medium | Useful for continuity and local thermal bridging. |
| Acoustic comfort | 2 | Medium | Purlin isolation may reduce movement noise; no Rw claim. |
| Sustainability | 2 | Low | No quantified environmental evidence linked. |
| Installation practicality | 5 | High | Self-adhesive accessory format is its main strength. |
| Compliance readiness | 2 | Medium | Exact fire and adhesive evidence must match. |
| BAL suitability | Gate | High | No BAL recommendation. |

Capture adjoining insulation/system, purpose, width/thickness, substrate, service temperature, indoor/outdoor exposure, surface condition and fire clause. The bot may suggest it as an accessory, but a person confirms size, adhesion and regulatory suitability.

```json
{"family_id":"THERMOTEC_MAXTAPE_FR","recommendation_level":"accessory_family_only","best_for":["insulation continuity","local condensation detailing","purlin isolation"],"not_for":["standalone pipe insulation","standalone acoustic barrier"],"required_inputs":["system","purpose","substrate","temperature","exposure"],"human_gates":["size","adhesion","fire_report_scope","BAL"]}
```
