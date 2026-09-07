# All manufacturers literature review status

Last reviewed: 2026-09-04 (Thermotec/Fletcher); 2026-09-05 (All 26 manufacturers)

## Scope completed

### Phase 1 (Detailed review - 2026-09-04)
- 13 Thermotec family knowledge files
- 18 Fletcher family knowledge files
- 31 valid embedded machine-readable decision records
- Customer-priority logic, comparison boundaries, mandatory enquiry fields and human-review gates in every family file

### Phase 2 (Initial documentation - 2026-09-05)
- 24 additional manufacturers with initial knowledge base structure
- 1,682+ products across all manufacturers organized by category
- Generated families.json for each manufacturer with standardized scoring and metadata
- Readme and product family templates for all manufacturers

## Manufacturer coverage

| Manufacturer | Product Count | Status | Documentation Level |
|---|---|---|---|
| Autex | 324 | New | Initial categorization |
| Thermotec | 280 | Existing | Deep dive complete |
| Bradford | 154 | New | Initial categorization |
| Fletcher | 134 | Existing | Deep dive complete |
| Kingspan | 93 | New | Initial categorization |
| Rockwool | 71 | New | Initial categorization |
| Proctor | 61 | New | Initial categorization |
| Trade Select | 59 | New | Initial categorization |
| Ecowool | 58 | New | Initial categorization |
| Higgins Insulation | 56 | New | Initial categorization |
| Knauf | 53 | New | Initial categorization |
| Foilboard | 49 | New | Initial categorization |
| Sonata Acoustic Panels | 48 | New | Initial categorization |
| Polyester Solutions | 32 | New | Initial categorization |
| Acoustica | 29 | New | Initial categorization |
| Aircell | 23 | New | Initial categorization |
| Metecno | 22 | New | Initial categorization |
| Misc | 22 | New | Initial categorization |
| DCTech | 14 | New | Initial categorization |
| Stinger | 13 | New | Initial categorization |
| Paroc | 12 | New | Initial categorization |
| Ametalin | 8 | New | Initial categorization |
| James Hardie | 5 | New | Initial categorization |
| Hushtec | 5 | New | Initial categorization |
| Polyair | 5 | New | Initial categorization |
| Martini | 4 | New | Initial categorization |
| **TOTAL** | **2,359** | - | - |

"Initial categorization" means the structure is in place but requires technical deep-dive review for full accuracy.
"Deep dive complete" means the available evidence has been analysed and the bot-safe boundary is documented. It does not turn missing evidence into verified data or make every spreadsheet SKU quote-ready.

## Recommendation levels

| Level | Meaning |
|---|---|
| Family only | Demo may name the manufacturer-supported family; grade/SKU/system result remains human-reviewed. |
| Subfamily only | Exact variant must be identified from the current guide/TDS before selection. |
| Accessory only | May be suggested only with the compatible parent system. |
| Blocked | Bot collects the enquiry and requests human verification; no recommendation or substitution. |

## Evidence exceptions requiring follow-up

| Family | Current state | Required next evidence |
|---|---|---|
| Thermotec NuWave Fence MLV | Owned secondary source; listed out of stock | Current Thermotec TDS, availability, UV/weathering and installation evidence |
| Thermotec NuWave foil-faced MLV | Owned secondary source only | Current Thermotec identity, TDS and exact fire report |
| Thermotec Maxflex Coil | Identity unresolved | Full name/code, current TDS, dimensions and service limits |
| Fletcher Safe'n'Silent Pro350 | Legacy identity unresolved | Current/archived Australian primary catalogue and technical data |
| Fletcher FF HD | Abbreviated legacy identity unresolved | Full description/code, material, facing and current equivalent |
| Fletcher FI24 / "FI22 FLEX DLINER" row | Spreadsheet alias conflict | Manufacturer confirmation for code 4005560 |
| Fletcher Soundbreak legacy rows | Codes/thicknesses conflict with current TDS | Reconcile old 902191–902202-style codes and legacy dimensions |
| All new manufacturers | Initial templates | Extract and validate TDS for each family category |

## Global bot rules

1. Keep material R-value, Total R-value, Rw, Rw+Ctr, NRC/αw and fire test results separate.
2. Recommend at family level only where current primary manufacturer evidence supports the use case.
3. Never claim NCC, FRL, BAL or installed acoustic performance from a component alone.
4. Exact SKU, quantity, regional availability and system compliance remain human-approved until reconciled.

## Next steps for Phase 3 (Detailed technical validation)

1. **Performance evidence extraction**: Extract thermal R, acoustic Rw, NRC/αw from manufacturer TDS for each family
2. **Category validation**: Confirm product category assignments match manufacturer intent
3. **Application mapping**: Validate applications listed for each family category
4. **Evidence scoring**: Update confidence levels based on available manufacturer documentation
5. **Family refinement**: Split overly broad categories or consolidate similar families
