---
family_id: FLETCHER_FOAM_BUBBLE_CELL
manufacturer: Fletcher Insulation
canonical_name: Foam Cell and Bubble Cell Reflective Insulation
category: Reflective foam and bubble insulation
validation_status: manufacturer_supported_subfamily_selection_required
last_validated: 2026-09-04
recommendation_scope: subfamily_only
official_product_url: https://insulation.com.au/product/foam-cell-mutlipurpose/
---

# Foam Cell and Bubble Cell Reflective Insulation

## Canonical description

This dataset family groups related but distinct Fletcher reflective products: Foam Cell Multipurpose, Foam Cell Multipurpose LT and Bubble Cell. Foam Cell uses a closed-cell foam core; Bubble Cell uses an air-cell/bubble construction. Facing, duty, thickness and intended assembly differ, so they are not interchangeable.

## Performance interpretation

Reflective insulation only delivers the claimed thermal contribution in the documented orientation and airspace. Product thickness or reflective appearance is not a universal R-value. Water/vapour behaviour, condensation strategy, compression, contact with metal and electrical safety also need project review.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | 4 | Medium | Useful in documented reflective assemblies. |
| Moisture/comfort | 4 | Medium | Closed-cell/foil layers can contribute; exact product properties matter. |
| Acoustic comfort | 2 | Low | Do not infer Rw or rain-noise performance. |
| Sustainability | 2 | Low | No common family EPD/score should be assumed. |
| Installation practicality | 4 | Medium | Lightweight rolls; airspace, laps and compression are critical. |
| BAL suitability | Gate | High | Foil facing does not prove BAL compliance. |

## Mandatory inputs

Capture exact subfamily/code, roof/wall/floor application, construction, airspace, target Total R-value, climate/condensation design, contact/compression, exposure, fire/BAL and roll size. The demo may choose the grouped family, but exact subfamily/SKU and system R-value remain human-gated.

## Sources

- [Foam Cell Multipurpose](https://insulation.com.au/product/foam-cell-mutlipurpose/)
- [Foam Cell Multipurpose LT](https://insulation.com.au/product/foam-cell-multipurpose-lt/)
- [Bubble Cell](https://insulation.com.au/product/bubble-cell/)

```json
{"family_id":"FLETCHER_FOAM_BUBBLE_CELL","recommendation_level":"subfamily_only","subfamilies":["Foam Cell Multipurpose","Foam Cell Multipurpose LT","Bubble Cell"],"required_inputs":["exact_product","application","airspace","construction","target_total_r","condensation","BAL"],"human_gates":["subfamily","sku","system_r","installation","compliance","BAL"]}
```
