---
id: thermotec-nuwrap-5
family_id: THERMOTEC_NUWRAP_5
manufacturer: Thermotec Australia
canonical_name: Thermotec NuWrap 5 Acoustic Pipe Lagging
category: Acoustic pipe and duct lagging
validation_status: manufacturer_supported
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/nuwrap-acoustic-lagging
---

# Thermotec NuWrap 5 Acoustic Pipe Lagging

## Bot-ready summary

NuWrap 5 is a flexible composite acoustic lagging for waste pipes, domestic plumbing, ductwork and mechanical services. It combines a high-mass visco-elastic acoustic barrier, 25 mm convoluted acoustic foam and a reinforced fire-resistant aluminium foil facing.

The barrier layer helps restrict airborne noise, while the foam layer provides separation and absorption around the service. Its flexibility allows it to follow bends, fittings and complex pipework in new-build or retrofit installations.

## Typical use

- Waste and water pipes near bedrooms or occupied rooms
- Domestic and commercial plumbing
- Ductwork and mechanical services
- Projects requiring flexible acoustic treatment around bends and fittings

## Selection and installation rules

- Confirm the service type, pipe diameter, fittings, available clearance and required acoustic construction.
- Maintain continuous coverage around the service.
- Treat bends, branches, supports and penetrations as part of the acoustic path.
- Close and seal joins using the manufacturer-specified method.
- Follow the current installation guide where fire or NCC compliance is required.

## Limitations

- Do not describe NuWrap 5 as plain MLV; it is a multi-layer composite.
- Do not populate NRC, thermal R-value or product Rw unless the exact current TDS supplies that metric.
- Do not transfer NuWave Base sheet ratings to NuWrap 5.
- The manufacturer states testing to AS/NZS 1530.3 and BS 476 Parts 6 and 7; cite exact classifications only from the test report or current TDS.

## Approved bot language

> Thermotec NuWrap 5 is a flexible composite acoustic lagging for waste pipes, plumbing, ductwork and mechanical services. It combines a high-mass acoustic barrier with 25 mm convoluted foam and a reinforced foil facing. Correct treatment of joints, bends, supports and penetrations is important because gaps can reduce the performance of the complete installation.

## Source

[Thermotec NuWrap 5 Acoustic Pipe Lagging](https://thermotec.com.au/products/nuwrap-acoustic-lagging)

## Deep-dive decision guidance

### Verified construction and purpose

Thermotec describes NuWrap 5 as a hybrid composite of mass loaded vinyl, 25 mm convoluted acoustic foam and reinforced fire-resistant aluminium foil. Intended applications include waste pipes, ductwork, mechanical services and domestic plumbing. The barrier resists noise breakout, the foam provides separation/absorption within the wrap, and the facing protects the outer surface.

The manufacturer page references testing to AS/NZS 1530.3, BS 476 Parts 6 and 7, plus VOC and acoustic data. These are evidence references to retrieve, not proof that every installed pipe or duct complies.

### Acoustic interpretation

- Pipe-breakout noise is an assembly problem: pipe material, diameter, flow, bends, brackets, penetrations, enclosure and lagging continuity affect the outcome.
- Do not present an MLV surface mass or laboratory result as the room-to-room Rw of the completed construction.
- Structure-borne vibration through brackets may require isolation as well as lagging.

### Family comparison

| Need | Starting family | Boundary |
|---|---|---|
| Conventional high-evidence service wrap | NuWrap 5 | Confirm conditions and installation detail. |
| Small pipes, tight bends or difficult access | NuWrap XtraFlex | Confirm current XtraFlex format. |
| Flat wall, floor or ceiling barrier | NuWave Base MLV | Do not substitute pipe lagging by name alone. |
| Thermal/condensation control on HVAC pipe | E-Flex / 4-Zero | Acoustic lagging is not automatically the thermal design layer. |

### Customer-priority ratings

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Acoustic comfort | 5 | High | Purpose-designed for service-noise breakout. |
| Energy efficiency | 2 | Low | Calculate service insulation separately. |
| Sustainability | 2 | Low | No quantified family environmental declaration is cited. |
| Installation practicality | 4 | Medium | Flexible composite suits bends and complex pipework. |
| Compliance readiness | 3 | Medium | Test references exist; exact reports and application must match. |
| BAL suitability | Gate | High | No automatic BAL outcome. |

### Mandatory enquiry fields and recommendation rule

Capture service, material, outside diameter, operating temperature, exposure, noise symptom, enclosure, fire specification, target and drawing. The demo may recommend the **NuWrap 5 family** for pipe/duct breakout noise. Exact quantity, layer build-up, joint treatment, penetrations and compliance claims require technical review.

### Machine-readable decision record

```json
{"family_id":"THERMOTEC_NUWRAP_5","recommendation_level":"family_only","best_for":["waste pipe noise","duct breakout","mechanical services"],"required_inputs":["service","diameter","temperature","exposure","noise_path","fire_requirement"],"human_gates":["quantity","installation_detail","test_report_scope","compliance","BAL"]}
```
