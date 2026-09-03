# Fletcher Insulation product-family knowledge base

Bot-facing knowledge for the 134 rows whose `Manufacturer Name` is Fletcher in `Sheet1`. The structured source is [families.json](families.json); each family below has a stable ID, discovery terms, priority scores, evidence state, questions and human gates.

All 18 family files received a structured deep-dive review on 2026-09-04. “Complete” means the product role, comparison logic, metric boundaries, customer-priority ratings, mandatory questions and evidence gates are documented. Exact SKU reconciliation remains a separate task. Safe'n'Silent Pro350 and FF HD remain blocked until current primary evidence resolves their identities.

| Family ID | Product family | Evidence status |
| --- | --- | --- |
| `FLETCHER_PINK_BATTS_WALL` | Pink Batts Wall | Manufacturer supported |
| `FLETCHER_PINK_BATTS_CEILING` | Pink Batts Ceiling | Manufacturer supported |
| `FLETCHER_PINK_BATTS_FLOOR` | Pink Batts Floor | Manufacturer supported |
| `FLETCHER_SOUNDBREAK` | Soundbreak | Deep dive complete; manufacturer supported; sheet reconciliation required |
| `FLETCHER_PINK_PARTITION` | Pink Partition | Manufacturer supported |
| `FLETCHER_FI32_SEMI_RIGID` | FI32 Semi-Rigid | Manufacturer supported |
| `FLETCHER_FI24_FLEX_DUCTLINER` | FI24 Flexible Ductliner | Manufacturer supported; legacy FI22 row needs review |
| `FLETCHER_PINK_THERMAL_SLAB` | Pink Thermal Slab | Manufacturer supported |
| `FLETCHER_PARTY_WALL_STONEWOOL` | Fletcher Protect / Fire Stop Party Wall Stonewool | Manufacturer supported; exact system component required |
| `FLETCHER_PERMASTOP` | Permastop Building Blanket | Manufacturer supported |
| `FLETCHER_VAPAWRAP_WALL` | Vapawrap Residential Wall | Manufacturer supported |
| `FLETCHER_VAPAWRAP_METAL_ROOF` | Vapawrap Metal Roof | Manufacturer supported |
| `FLETCHER_SISALATION_WRAP` | Tuff Wrap and Multipurpose | Manufacturer supported; exact variant required |
| `FLETCHER_FOAM_BUBBLE_CELL` | Foam Cell and Bubble Cell | Manufacturer supported; exact variant required |
| `FLETCHER_SUPABATT` | supaBATT | Manufacturer supported |
| `FLETCHER_TAPES_ACCESSORIES` | Tapes and thermal-break accessories | Manufacturer supported; parent system required |
| `FLETCHER_SAFE_N_SILENT_LEGACY` | Safe'n'Silent Pro350 | Identity unverified; recommendation blocked |
| `FLETCHER_FF_HD_LEGACY` | FF HD facing roll | Identity unverified; recommendation blocked |

## Retrieval rule

1. Identify the application and problem before comparing manufacturers.
2. Rank families using application/keyword fit and the customer's priority.
3. Recommend only a manufacturer-supported family.
4. Keep `R`, total system R-value, `Rw`, `Rw+Ctr`, NRC/αw and fire-test results separate.
5. Select the exact SKU, grade, density, facing, width and quantity only after technical review.

Many spreadsheet rows currently point to one of only five TDS URLs, including obvious cross-family links. Those inherited links are not treated as proof of a product-specific value.
