---
family_id: FLETCHER_TAPES_ACCESSORIES
manufacturer: Fletcher Insulation
canonical_name: Fletcher Tapes and Membrane Accessories
category: Sealing and joining accessories
validation_status: manufacturer_supported_subfamily_selection_required
last_validated: 2026-09-04
recommendation_scope: accessory_only
---

# Fletcher Tapes and Membrane Accessories

## Canonical description

This family contains distinct joining/sealing accessories such as Thermatape, Vapastop 883 Tape and 3M Seaming Tape. A tape must be selected for the exact membrane/facing, substrate, temperature, exposure and required seal. Brand-level grouping is useful for discovery but unsafe for substitution.

## Accessory rule

An accessory supports continuity; it does not give the underlying membrane or insulation a new R-value, Rw, vapour class, fire classification or BAL rating. Use only the tape approved by the relevant product installation guide. Surface preparation, overlap, pressure, temperature and storage affect adhesion.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Installation practicality | 5 | High | Core purpose is sealing/joining continuity. |
| Energy/moisture performance | 3 | Medium | Supports the parent system; no standalone rating. |
| Acoustic comfort | 1 | High | Not an acoustic product. |
| Sustainability | 2 | Low | No common quantified evidence. |
| Compliance readiness | 3 | Medium | Depends entirely on approved parent-system use. |
| BAL suitability | Gate | High | Tape selection alone cannot establish BAL. |

## Mandatory inputs and sources

Capture parent product, joint/repair purpose, substrate, indoor/outdoor exposure, temperature, UV duration, fire/BAL requirement, width and quantity. Do not recommend a tape if the parent-product guide is unknown.

- [Thermatape TDS](https://insulation.com.au/wp-content/uploads/2024/TDS-Thermatape-Revision_1_Issue-Date-14122021-2.pdf)
- [Vapastop 883 Tape](https://insulation.com.au/product/vapastop-883-tape/)
- [3M Seaming Tape](https://insulation.com.au/product/3m-seaming-tape/)

```json
{"family_id":"FLETCHER_TAPES_ACCESSORIES","recommendation_level":"accessory_only","required_inputs":["parent_product","joint_purpose","substrate","temperature","exposure","width"],"human_gates":["compatible_tape","quantity","surface_preparation","compliance","BAL"]}
```
