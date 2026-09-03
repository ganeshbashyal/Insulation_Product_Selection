---
family_id: FLETCHER_PERMASTOP
manufacturer: Fletcher Insulation
canonical_name: Permastop Building Blanket
category: Faced glasswool roof blanket
validation_status: manufacturer_supported
last_validated: 2026-09-04
recommendation_scope: family_only
official_product_url: https://insulation.com.au/product/permastop-building-blanket/
---

# Permastop Building Blanket

## Canonical description

Permastop is a faced glasswool building blanket for suitable metal-roof and commercial/residential constructions. Fletcher positions it for thermal performance, condensation management and reduction of rain/noise effects, with low-, medium- and heavy-duty foil-facing options in the current range. Facing grade, blanket thickness, mesh/support and roof system must match the job.

## Selection logic

Use Permastop when a flexible roof blanket beneath metal cladding is required. Use Pink Batts Ceiling for ceiling-level cavity insulation, Pink Thermal Slab for semi-rigid soffit/concrete applications, or Vapawrap Metal Roof when a vapour-permeable membrane—not bulk glasswool—is required. A blanket R-value is not the roof Total R-value; rain-noise improvement is system-specific.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 5 | High | Core bulk roof-insulation function. |
| Acoustic comfort | 4 | Medium | Relevant to metal-roof rain/noise control as a system. |
| Sustainability | 4 | Medium | Glasswool recycled-content/EPD evidence; confirm exact scope. |
| Installation practicality | 3 | Medium | Large blanket format; compression, sag and supports matter. |
| Compliance readiness | 4 | Medium | Product/BAL statements exist only for defined applications. |
| BAL suitability | Gate | High | Apply only the exact documented roof-system conditions. |

## Mandatory inputs and safeguards

Capture roof profile, support/purlin spacing, blanket thickness/R-value, facing duty, facing direction, mesh/support, compression at spacers, condensation design, climate, rain-noise target, building classification and BAL/fire requirement. Never claim “BAL compliant” without the applicable construction detail.

## Approved bot language

> Permastop is the Fletcher faced glasswool blanket family for suitable metal-roof systems, combining thermal and condensation functions with potential rain-noise benefit. The exact blanket, facing and roof detail must be confirmed.

## Source

[Fletcher Permastop Building Blanket](https://insulation.com.au/product/permastop-building-blanket/)

```json
{"family_id":"FLETCHER_PERMASTOP","recommendation_level":"family_only","best_for":["metal roof blanket","thermal and condensation control","rain noise system contribution"],"required_inputs":["roof_profile","purlin_spacing","target_r","facing_duty","support","condensation_design","BAL"],"human_gates":["sku","compression","system_total_r","rain_noise_claim","BAL"]}
```
