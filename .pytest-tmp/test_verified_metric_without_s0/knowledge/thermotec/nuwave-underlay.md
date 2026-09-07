---
id: thermotec-nuwave-underlay
family_id: THERMOTEC_NUWAVE_UNDERLAY
manufacturer: Thermotec Australia
canonical_name: Thermotec Premium Carpet Underlay
category: Acoustic floor underlay
validation_status: manufacturer_supported_metrics_pending
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/carpet-underlay
---

# Thermotec Premium Carpet Underlay

## Bot-ready summary

Thermotec Premium Carpet Underlay is a floor-acoustic product in the NuWave noise-barrier range. It combines a flexible high-density limp-mass polymer barrier with a low-density closed-cell polyethylene foam layer. The barrier restricts airborne sound while the foam layer helps address floor impact energy.

Use it beneath a compatible carpet/floor system where the design needs control of sound travelling down through a floor and up through the ceiling below. It is a different construction from plain NuWave Base MLV and must have a separate family record.

## Selection questions

- What floor covering and substrate will be used?
- Is the target impact noise, airborne noise or both?
- Is there a required tested floor-system result?
- Is the project new construction or retrofit?
- Are floor height, transitions, moisture or loading constraints relevant?

## Limitations

- Do not copy NuWave Base product Rw values into this underlay family.
- Do not promise a completed floor impact or airborne rating without the tested assembly.
- Confirm grade, thickness, roll size, floor-covering compatibility and installation method in the current data sheet.
- The spreadsheet's 4/6/8 kg underlay labels require reconciliation against the current Thermotec underlay range.

## Approved bot language

> Thermotec Premium Carpet Underlay combines a limp-mass sound barrier with closed-cell polyethylene foam to help reduce airborne and impact noise through floor systems. Final performance depends on the complete floor and ceiling construction, so the required assembly rating and compatible floor covering should be confirmed before selecting the product.

## Source

[Thermotec Premium Carpet Underlay](https://thermotec.com.au/products/carpet-underlay)

## Deep-dive decision guidance

### What the product is

This is a composite floor-acoustic underlay, not a plain foam cushion and not plain NuWave Base MLV. Thermotec describes a flexible high-density limp-mass polymer barrier bonded to low-density closed-cell polyethylene foam. The mass layer is intended to impede airborne sound; the resilient foam layer helps decouple floor-generated impact energy.

### What the bot may infer

- Strong family fit when the customer describes footsteps, chairs or floor-borne disturbance and the proposed floor finish is compatible.
- Potential combined benefit where both impact and airborne transfer through a floor are concerns.
- The product is a component of a floor/ceiling assembly; substrate, finish, ceiling, fixings, perimeter details and flanking paths affect the result.

The bot must not translate a product weight such as 4, 6 or 8 kg into an Rw, Ln,w or dB improvement. Those are different quantities. It must not call this thermal insulation without a current documented thermal result.

### Family comparisons

| Situation | Better starting family | Reason |
|---|---|---|
| Footfall through a floor | NuWave Underlay | Resilient underlay is aligned to impact transmission. |
| Airborne sound through a wall/ceiling | NuWave Base MLV | Plain barrier integrates more directly in those constructions. |
| Noise breakout from waste pipe | NuWrap 5 or XtraFlex | Service lagging is shaped and faced for pipes/ducts. |
| Room echo | Acoustic absorber, not this family | Echo control needs exposed absorption. |

### Customer-priority ratings

| Priority | Score / 5 | Confidence | Bot rationale |
|---|---:|---|---|
| Acoustic comfort | 5 | High | Directly aligned to floor impact and airborne-noise control. |
| Energy efficiency | 1 | High | Not the documented primary function. |
| Sustainability | 2 | Low | No current EPD or quantified disclosure is linked. |
| Installation practicality | 4 | Medium | Thin/flexible format is useful; compatibility and detailing still matter. |
| Compliance readiness | 2 | Medium | A tested assembly or consultant detail is normally needed. |
| BAL suitability | Gate | High | No family-level BAL recommendation is supported. |

### Mandatory enquiry fields

Capture floor finish, substrate, joist/slab construction, ceiling below, new-build versus retrofit, impact versus airborne concern, target rating or body-corporate rule, available build-up height, moisture exposure and project location.

### Recommendation rule

The demo may recommend the **NuWave Underlay family** when the use case is a compatible floor system and acoustic comfort is primary. Send grade, thickness, exact SKU and any performance/compliance promise to a person until the current data sheet and tested assembly are attached.

### Machine-readable decision record

```json
{"family_id":"THERMOTEC_NUWAVE_UNDERLAY","recommendation_level":"family_only","best_for":["floor impact noise","combined floor airborne and impact control"],"not_for":["room echo","standalone wall barrier","pipe lagging"],"required_inputs":["floor_finish","substrate","complete_assembly","noise_type","target_rating"],"human_gates":["grade","sku","tested_system","compliance","BAL"]}
```
