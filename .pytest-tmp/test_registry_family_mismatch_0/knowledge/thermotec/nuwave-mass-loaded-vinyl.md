---
id: thermotec-nuwave-mlv
family_id: THERMOTEC_NUWAVE_BASE_MLV
manufacturer: Thermotec Australia
brand: NuWave
product_family: NuWave Base Mass Loaded Vinyl Acoustic Barrier
canonical_name: Thermotec NuWave Base Mass Loaded Vinyl Acoustic Barrier
category: Acoustic barrier
material: High-density flexible hybrid polymer mass loaded vinyl
primary_noise_type: Airborne noise
bot_mode: demo_family_recommendation
recommendation_allowed: true
recommendation_scope: manufacturer_supported_family_only
requires_human_selection: true
validation_status: manufacturer_supported_secondary_claims_pending
last_validated: 2026-09-03
rating_framework_version: 1
priority_sustainability_score: 2
priority_sustainability_confidence: low
priority_energy_efficiency_score: 1
priority_energy_efficiency_confidence: high
priority_airborne_acoustic_comfort_score: 5
priority_airborne_acoustic_comfort_confidence: high
gate_ncc_project_compliance: conditional_complete_system_evidence_required
gate_fire_compliance: not_verified_for_base_product
gate_bal: not_verified
official_product_url: https://thermotec.com.au/products/nuwave_mlv_acoustic_barriers_2
official_datasheet_url: https://cdn.shopify.com/s/files/1/0676/6827/9608/files/FINALS_NuWave_Data_Sheet_1703_V3.pdf?v=1787942996
official_installation_url: https://cdn.shopify.com/s/files/1/0676/6827/9608/files/NuWave_INSTALLATION_2025.pdf?v=1787932861
---

# Thermotec NuWave Base Mass Loaded Vinyl Acoustic Barrier

## Purpose of this file

This is the canonical internal description for NuWave Base. It aligns the terminology used by the enquiry bot, sales team and future Aircall CSV.

For the demonstration, the bot may recommend the **NuWave Base family** when the customer's problem is airborne sound transmission through a suitable wall, floor, ceiling or partition. It must not choose a grade, calculate an order quantity or confirm acoustic, fire, NCC or BAL compliance. Those decisions remain human-reviewed.

## Canonical description

Thermotec NuWave Base is an Australian-made, flexible, high-density mass loaded vinyl acoustic barrier. It is designed to reduce airborne sound transmission when incorporated into a suitable wall, floor, ceiling or partition construction.

NuWave adds flexible mass to a construction. It is normally concealed behind a lining such as plasterboard and installed as a continuous barrier. Its effectiveness in practice depends on the complete construction, including linings, framing, cavities, absorptive insulation, junctions, penetrations, sealing, flanking paths and workmanship.

NuWave Base is not thermal insulation, an acoustic absorption panel or a complete compliant building system. It must not be described as providing a standalone thermal R-value, NRC result, BAL rating or finished-wall acoustic rating.

## Current manufacturer-supported facts

- Product type: flexible mass loaded vinyl acoustic barrier.
- Primary function: reduction of airborne sound transmission.
- Current standard surface-mass grades: 2, 4, 6, 8 and 10 kg/m².
- Manufacturer-published product ratings: Rw 24 to Rw 34, depending on grade.
- Current manufacturer wording describes the material as a hybrid polymer with fabric-backed construction and an embossed face.
- Confirmed manufacturer applications include walls, floors, ceilings and partitions in residential, commercial and acoustically sensitive spaces.
- The product is manufactured in Australia.
- The manufacturer states that independent acoustic test reports are available.

## Grade and catalogue reconciliation

The Rw figures are current manufacturer-published product ratings. The commercial dimensions and total roll weights below are taken from the current Google Sheet snapshot and must be checked against live availability before quoting.

| NuWave Base grade | Published product Rw | Sheet roll size | Sheet coverage | Calculated/listed roll mass | Data note |
| --- | ---: | --- | ---: | ---: | --- |
| 2 kg/m² | Rw 24 | 1350 × 5000 mm | 6.75 m² | 13.5 kg | Current base-family row |
| 4 kg/m² | Rw 26 | 1350 × 5000 mm | 6.75 m² | 27.0 kg | Current base-family row |
| 6 kg/m² | Rw 29 | 1350 × 3000 mm | 4.05 m² | 24.3 kg | Current base-family row |
| 8 kg/m² | Rw 30 | 1350 × 3000 mm | 4.05 m² | 32.4 kg | Current base-family row |
| 10 kg/m² | Rw 34 | 1350 × 3000 mm | 4.05 m² | 40.5 kg | Sheet SKU is currently `c`; correct before CSV export |

The sheet also contains half-roll and South Australia inventory records for 4, 6 and 8 kg/m². These are commercial or regional records within the same technical family. They do not require separate technical claims, but each must retain its own SKU, dimensions, stock and location data.

### Critical acoustic interpretation

`Rw` is a weighted sound reduction index. It is not thermal `R`, NRC, αw, a percentage reduction or a promise of the number of decibels a customer will experience.

The product Rw must not be represented as the Rw or Rw + Ctr of a completed wall, floor or ceiling. Where a project has an acoustic target, the human reviewer must obtain a tested or assessed complete construction and confirm that it matches the proposed build-up.

## Application boundaries

### Within the NuWave Base family

- Internal walls and partitions.
- Floor and ceiling constructions where the complete system is suitable.
- Office, residential, studio and home-theatre applications involving airborne sound transmission.
- Other concealed barrier applications only after human confirmation of the construction and exposure conditions.

### Separate product families

Do not transfer NuWave Base claims automatically to these records:

| Product/configuration | Family ID | Required treatment |
| --- | --- | --- |
| NuWave Base half rolls | `THERMOTEC_NUWAVE_BASE_MLV` | Same technical family; preserve the different roll dimensions and mass |
| State-specific NuWave Base records | `THERMOTEC_NUWAVE_BASE_MLV` | Same technical family; preserve region and commercial identifiers |
| NuWave 4‑Zero foil-faced MLV | `THERMOTEC_NUWAVE_FOIL_FACED_MLV` | Separate fire-related configuration; requires its own current technical and fire evidence |
| UV-treated NuWave fence barrier | `THERMOTEC_NUWAVE_FENCE_MLV` | Separate exposed-use configuration; requires current UV, durability and installation evidence |
| NuWave carpet underlay | `THERMOTEC_NUWAVE_UNDERLAY` | Separate floor product addressing impact and airborne-noise behaviour |
| NuWave CrossTalk | `THERMOTEC_NUWAVE_CROSSTALK` | Separate ceiling-plenum/CAC product |
| NuWrap 5 | `THERMOTEC_NUWRAP_5` | Composite pipe and duct lagging, not base MLV sheeting |

NuWave Base should not be presented as the complete answer for room echo, reverberation, impact noise or structure-borne vibration. Record the noise type for human review rather than suggesting a different product.

## Installation context for enquiry handling

Thermotec's published overview describes measuring and cutting the sheet, hanging it evenly, mechanically fixing it to the appropriate substrate, cutting closely around penetrations, maintaining continuity and installing the lining over it. Acoustic sealant may be used where specified.

The bot may use this information to understand the customer's project, but must not issue project-specific installation instructions. The human reviewer must confirm:

- the complete wall, floor or ceiling build-up;
- fixing method and substrate;
- joint, perimeter and penetration treatment;
- electrical, plumbing and fire-stopping details;
- moisture, UV and exposure conditions;
- manual-handling requirements;
- the current Thermotec installation guide and project specification.

## Customer-priority profile

These ratings are internal conversation aids. They determine useful follow-up questions and callback notes; they do not rank or recommend products to customers.

| Customer priority | Internal rating | Confidence | Interpretation |
| --- | ---: | --- | --- |
| Sustainability | 2/5 | Low | Australian manufacture and claimed durability are positive indicators. Owned legacy literature also mentions low VOC and no ozone-depleting substances, but current product-specific environmental evidence has not yet been verified. Do not claim an EPD, recycled-content percentage, Green Star certification, recyclability or whole-of-life benefit. |
| Energy efficiency | 1/5 | High | NuWave Base is an acoustic barrier and has no verified thermal R-value. It must not be used to answer an energy-efficiency or thermal-insulation requirement. |
| Airborne acoustic comfort | 5/5 | High | Reducing airborne sound transmission is its primary documented purpose. Actual comfort depends on the complete installed construction and the noise source. |

## Mandatory human-review gates

| Requirement | Status for NuWave Base | Enquiry-bot action |
| --- | --- | --- |
| Acoustic target / NCC | CONDITIONAL | Record the building type, construction and any Rw or Rw + Ctr target. Do not confirm compliance; arrange human review. |
| Fire requirement | NOT VERIFIED FOR BASE PRODUCT | Do not apply foil-faced 4‑Zero fire claims to NuWave Base. Record the required fire test, classification or system and arrange human review. |
| BAL / bushfire construction | NOT VERIFIED | Record the site's BAL and the external building element involved. Do not describe NuWave Base as BAL-compliant; arrange human review. |
| UV or weather exposure | NOT VERIFIED FOR BASE PRODUCT | Treat exposed fence material as a separate family. Record exposure conditions and arrange human review. |
| Thermal or energy target | NOT AN INTENDED FUNCTION | Record the requirement and arrange human review without suggesting an alternative product. |

## Aircall enquiry flow

The voice agent should gather information naturally rather than interrogating the caller with technical questions they may not understand.

1. What are you trying to improve, and what noise can you hear?
2. Where is the problem: wall, ceiling, floor, room, vehicle, machinery enclosure or somewhere else?
3. Is it mainly voices/music/traffic passing through a construction, footsteps or furniture movement, plumbing/mechanical noise, or echo within the room?
4. Is this a home, apartment, office, commercial building, industrial site or other project?
5. Is it a new build, renovation, retrofit or repair?
6. What is most important: acoustic comfort, sustainability, energy efficiency, budget, minimal thickness, ease of installation or another priority?
7. Do plans, a consultant or a certifier specify an acoustic, NCC, fire or BAL requirement?
8. What is the approximate area, if known?
9. Are there access, manual-handling, moisture, outdoor or UV-exposure considerations?
10. Would the caller prefer to phone the team directly or request a callback?

The agent must not ask the caller to choose a NuWave grade. If the caller names a grade, record it as caller-provided information rather than confirming it.

## Approved customer-facing language

### General explanation

> Mass loaded vinyl is a dense, flexible barrier used within a construction to help reduce airborne sound transmission. Thermotec NuWave Base is available in several surface-mass grades, but the appropriate product and grade depend on the complete construction and project requirements. I can collect the details for our team to review.

### When asked which grade to buy

> I cannot select a grade or confirm the result of an installed system. If you tell me about the noise, location, construction and any project requirements, I can prepare the enquiry for our team. Would you prefer to call them or request a callback?

### When asked about compliance or BAL

> Compliance and bushfire suitability depend on the complete construction and supporting documentation. I cannot confirm that from a product name alone. I will flag this for technical review and arrange the next contact step.

## Language controls

Prefer:

- “designed to reduce airborne sound transmission”;
- “manufacturer-published product Rw”;
- “complete construction” or “complete installed system”;
- “requires confirmation by our team”;
- “customer-stated requirement” when recording a target.

Avoid:

- “soundproof” or “eliminates noise”;
- “reduces noise by X dB” unless quoting a clearly identified applicable test result with context;
- “best,” “perfect,” “guaranteed” or “compliant”;
- calling product Rw a finished-wall rating;
- treating Rw as thermal R or NRC;
- calling NuWave Base fire-rated, BAL-rated, thermal insulation or an impact-noise underlay;
- asserting exact PVC/barium chemistry, non-toxicity, 100°C service temperature, thickness, low-VOC status or environmental compliance until current supporting documentation is accepted.

## Source reconciliation and evidence hierarchy

### Tier 1 — current manufacturer source

[Thermotec NuWave Mass Loaded Vinyl Acoustic Barrier](https://thermotec.com.au/products/nuwave_mlv_acoustic_barriers_2)

Use this source for the canonical product identity, current grades, product Rw values, primary applications and Australian manufacture.

### Tier 2 — current internal catalogue

The Google Sheet provides current commercial records for roll dimensions, calculated coverage, total roll mass, regional variants, internal SKUs, stock and warehouse information. Commercial data does not validate technical performance.

Current data issues to correct before Aircall CSV export:

- NuWave Base technical rows still show `NEEDS SOURCE` and `UNVERIFIED` despite the current Thermotec product page.
- The 10 kg row has `c` in the SKU field.
- NuWave Base, foil-faced 4‑Zero MLV, UV fence material and carpet underlay are currently grouped too broadly in some spec fields.
- The two foil-faced MLV rows link to the Thermotec 4‑Zero pipe-insulation page, which is the wrong product family.

### Tier 3 — authorised owned-site literature

- [Soundproofing Products Australia — NuWave Base](https://www.soundproofingproducts.com.au/nuwave-base-mlv-acoustic-soundproofing/)
- [Insulation Easy — NuWave Base](https://insulationeasy.com.au/product/nuwave-mass-loaded-vinyl-8kg-m2/)
- [Mass Loaded Vinyl Australia — NuWave Base](https://massloadedvinyl.com.au/product/mass-loaded-vinyl-mlv-acoustic-barrier/)
- [Insulation Victoria — Mass Loaded Vinyl](https://www.insulationvictoria.com.au/product/mass-loaded-vinyl-australian-made/)
- [Soundproofing Adelaide — 4 kg NuWave Base](https://soundproofingadelaide.au/product/4kg-mass-loaded-vinyl-best-quality-australian-made/)

These pages are useful for application language, customer vocabulary, historical catalogue information and commercial context. They contain substantial repeated legacy copy and should not be treated as five independent confirmations of the same claim.

Claims appearing only in this older literature remain pending until matched to an accepted current TDS, SDS, test report or environmental document. These include exact PVC/barium composition, nominal thicknesses, 100°C operating temperature, “Green Building Council compliant,” low-VOC, no-ODP and broad fire-performance language.

## Machine-readable family record

```json
{
  "family_id": "THERMOTEC_NUWAVE_BASE_MLV",
  "manufacturer": "Thermotec Australia",
  "canonical_name": "Thermotec NuWave Base Mass Loaded Vinyl Acoustic Barrier",
  "bot_mode": "demo_family_recommendation",
  "recommendation_allowed": true,
  "recommendation_scope": "manufacturer_supported_family_only",
  "primary_function": "Reduce airborne sound transmission as part of a complete construction",
  "applications": ["wall", "floor", "ceiling", "partition"],
  "grades": [
    {"surface_mass_kg_m2": 2, "product_rw": 24},
    {"surface_mass_kg_m2": 4, "product_rw": 26},
    {"surface_mass_kg_m2": 6, "product_rw": 29},
    {"surface_mass_kg_m2": 8, "product_rw": 30},
    {"surface_mass_kg_m2": 10, "product_rw": 34}
  ],
  "thermal_r_value": null,
  "nrc": null,
  "priority_profile": {
    "sustainability": {"score": 2, "confidence": "low"},
    "energy_efficiency": {"score": 1, "confidence": "high"},
    "airborne_acoustic_comfort": {"score": 5, "confidence": "high"}
  },
  "human_review_gates": {
    "ncc_and_project_compliance": "conditional_complete_system_evidence_required",
    "fire": "not_verified_for_base_product",
    "bal": "not_verified",
    "uv_weather_exposure": "not_verified_for_base_product"
  },
  "callback_required": true,
  "source_url": "https://thermotec.com.au/products/nuwave_mlv_acoustic_barriers_2"
}
```
