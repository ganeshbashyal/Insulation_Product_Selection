# Thermotec and Fletcher literature review status

Last reviewed: 2026-09-04

## Scope completed

- 13 Thermotec family knowledge files
- 18 Fletcher family knowledge files
- 31 valid embedded machine-readable decision records
- customer-priority logic, comparison boundaries, mandatory enquiry fields and human-review gates in every family file

“Deep dive complete” means the available evidence has been analysed and the bot-safe boundary is documented. It does not turn missing evidence into verified data or make every spreadsheet SKU quote-ready.

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
| Fletcher FI24 / “FI22 FLEX DLINER” row | Spreadsheet alias conflict | Manufacturer confirmation for code 4005560 |
| Fletcher Soundbreak legacy rows | Codes/thicknesses conflict with current TDS | Reconcile old 902191–902202-style codes and legacy dimensions |

## Global bot rules

1. Keep material R-value, Total R-value, Rw, Rw+Ctr, NRC/αw and fire test results separate.
2. Recommend at family level only where current primary manufacturer evidence supports the use case.
3. Never claim NCC, FRL, BAL or installed acoustic performance from a component alone.
4. Exact SKU, quantity, regional availability and system compliance remain human-approved until reconciled.
