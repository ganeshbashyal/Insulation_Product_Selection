---
id: thermotec-maxflex-pipe
family_id: THERMOTEC_MAXFLEX_PIPE
manufacturer: Thermotec Australia
product_family: Maxflex Coil Pipe Insulation
category: Pipe insulation
validation_status: identity_unverified
last_validated: 2026-09-03
---

# Maxflex Coil Pipe Insulation — identity unverified

## Bot-ready status

Sheet1 contains two Thermotec-labelled coil records, but a current authoritative Thermotec source for a distinct “Maxflex Coil” pipe-insulation family has not been located. The name may be legacy or may refer to another family, but that cannot be assumed.

## Catalogue evidence only

| Manufacturer part number | Sheet description | Sheet dimensions |
| --- | --- | --- |
| `990130013042` | Maxflex Coil Pipe Insulation | 13 mm wall × 13 mm ID, 32 m coil |
| `990130019042` | Maxflex Coil Pipe Insulation | 13 mm wall × 19 mm ID, 25 m coil |

These values identify the records; they are not enough to establish material, thermal conductivity, temperature range, fire classification, R-value or regulatory suitability.

## Mandatory gate

- Do not recommend, quote or use either record for compliance advice.
- Ask purchasing or Thermotec to confirm the current product family and technical data sheet.
- Do not automatically merge the records into E-Flex ST even though that range has selected coil formats.

## Deep-dive evidence dossier

The spreadsheet names “Maxflex Coil” records, but a current Thermotec pipe-insulation family page and data sheet matching that identity have not been established. The live Thermotec page using “Maxflex” in its URL describes **MaxTape FR insulating foam tape**, not a Maxflex pipe-coil family. Name similarity is insufficient to merge products.

Until purchasing/manufacturer evidence supplies the exact product title, material, dimensions, temperature range, thermal conductivity, fire data and current availability, keep these rows excluded from automatic selection and quotation. E-Flex ST may have coil formats, but substituting it would change product identity and requires explicit human confirmation.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Energy efficiency | Unknown | High | Intended function is plausible; performance is unverified. |
| Acoustic comfort | Unknown | High | No acoustic evidence. |
| Sustainability | Unknown | High | No evidence. |
| Installation practicality | Unknown | High | Format identity is unresolved. |
| Compliance readiness | 1 | High | No current primary technical source. |
| BAL suitability | Gate | High | No evidence. |

Collect source catalogue/date, supplier, product label photograph, code, coil dimensions, pipe size, thickness, service temperature and intended job. Route to purchasing/technical support without recommending a substitute.

```json
{"family_id":"THERMOTEC_MAXFLEX_PIPE","recommendation_level":"blocked_identity_unverified","spreadsheet_identity":"Maxflex Coil","do_not_merge_automatically_with":"THERMOTEC_E_FLEX_ST","required_evidence":["manufacturer_page","datasheet","product_code","dimensions","temperature_limit","fire_data","availability"],"human_gates":["identity","substitution","quotation","compliance","BAL"]}
```
