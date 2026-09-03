---
id: thermotec-nuwave-foil-faced-mlv
family_id: THERMOTEC_NUWAVE_FOIL_FACED_MLV
manufacturer: Thermotec Australia
product_family: NuWave 4-Zero Foil-faced MLV
category: Foil-faced acoustic barrier
validation_status: secondary_owned_source_only
last_validated: 2026-09-03
---

# NuWave 4-Zero Foil-faced MLV

## Bot-ready summary

Owned-site product pages describe a foil-faced NuWave mass loaded vinyl configuration. It is a separate acoustic-barrier family and is not Thermotec 4-Zero pipe insulation. The current Thermotec manufacturer page, available grades and exact fire-test documents still need confirmation.

The bot may use this record to recognise the product name and capture an enquiry. It must not select a grade, promise a fire outcome or quote the product until a person checks the current data sheet and the project's complete construction.

## Required questions

- Why is the foil-faced configuration required?
- What surface mass, sheet format and construction are specified?
- Is there a nominated fire report, NCC clause or consultant detail?
- Is the product being used in a wall, ceiling, service enclosure or another system?

## Human review gates

- Confirm the current manufacturer technical data and supply status.
- Check the exact fire test, specimen and permitted application.
- Do not turn a component test into a whole-system compliance claim.
- Do not map these rows to the 4-Zero pipe-insulation knowledge file.

## Secondary owned source

[Insulation Easy Australia product page](https://insulationeasy.com.au/product/nuwave-4zero-foil-faced-mlv-soundproofing/)

## Deep-dive evidence dossier

This owned secondary page describes a foil-faced NuWave MLV configuration. Keep it distinct from **Thermotec 4-Zero pipe insulation**, a factory-faced thermal pipe product. Similar wording does not establish equivalence.

No current Thermotec page/data sheet and exact fire report are linked. The bot can collect an enquiry but cannot select a grade, repeat a fire classification or recommend it for a regulated application. Foil may be wanted for protection or facing continuity; it does not itself prove R-value, non-combustibility, BAL suitability or assembly compliance.

| Priority | Score / 5 | Confidence | Reason |
|---|---:|---|---|
| Acoustic comfort | 4 | Low | MLV concept is relevant; exact variant unresolved. |
| Energy efficiency | 1 | High | Foil alone is not a valid R-value claim. |
| Sustainability | 2 | Low | No current quantified evidence. |
| Installation practicality | 2 | Low | Facing, laps and tapes need manufacturer detail. |
| Compliance readiness | 1 | High | Fire evidence and identity are pending. |
| BAL suitability | Gate | High | No BAL statement supported. |

Ask why foil is required, application, construction, mass/grade, fire clause and exposure. Offer NuWave Base only if a standard internal barrier meets the brief; never silently substitute it.

```json
{"family_id":"THERMOTEC_NUWAVE_FOIL_FACED_MLV","recommendation_level":"blocked_pending_manufacturer_verification","do_not_confuse_with":"THERMOTEC_4_ZERO","required_inputs":["application","reason_for_facing","grade","construction","fire_clause"],"human_gates":["identity","datasheet","fire_report","installation","compliance","BAL"]}
```
