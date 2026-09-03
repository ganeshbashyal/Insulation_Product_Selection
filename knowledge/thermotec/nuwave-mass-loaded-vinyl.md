---
id: thermotec-nuwave-mlv
family_id: THERMOTEC_NUWAVE_BASE_MLV
manufacturer: Thermotec Australia
brand: NuWave
product_family: Mass Loaded Vinyl Acoustic Barrier
canonical_name: Thermotec NuWave Mass Loaded Vinyl Acoustic Barrier
category: Acoustic barrier
material: Hybrid polymer mass loaded vinyl
primary_noise_type: Airborne noise
validation_status: manufacturer_supported
last_validated: 2026-09-03
official_product_url: https://thermotec.com.au/products/nuwave_mlv_acoustic_barriers_2
official_datasheet_url: https://cdn.shopify.com/s/files/1/0676/6827/9608/files/FINALS_NuWave_Data_Sheet_1703_V3.pdf?v=1787942996
official_installation_url: https://cdn.shopify.com/s/files/1/0676/6827/9608/files/NuWave_INSTALLATION_2025.pdf?v=1787932861
---

# Thermotec NuWave Mass Loaded Vinyl Acoustic Barrier

## Bot-ready summary

Thermotec NuWave is an Australian-made, flexible, high-density mass loaded vinyl acoustic barrier. It is used to reduce airborne sound transmission through walls, floors, ceilings and partitions. It is normally concealed within a building assembly, such as behind plasterboard, rather than used as a decorative exposed finish.

NuWave works as a dense, flexible sound barrier. It is intended to restrict sound passing through a construction element. It should not be described as an acoustic absorber, an NRC product or thermal insulation.

Typical applications include residential and commercial walls, office partitions, ceiling spaces, floor assemblies, music studios, home theatres and other acoustically sensitive rooms.

## Standard NuWave Base grades

| Surface mass | Manufacturer-published Rw | Typical selection position |
| --- | ---: | --- |
| 2 kg/m² | Rw 24 | Lowest-mass option where handling and a modest barrier improvement are priorities |
| 4 kg/m² | Rw 26 | Common general-purpose option, including installation behind plasterboard |
| 6 kg/m² | Rw 29 | Higher-mass option where stronger airborne-noise control is required |
| 8 kg/m² | Rw 30 | Heavy barrier for higher-performance applications |
| 10 kg/m² | Rw 34 | Highest published standard NuWave Base grade in the current range |

The Rw figures above are product ratings published by Thermotec. They must not be presented as the final Rw of a completed wall, floor or ceiling. Installed performance also depends on the complete assembly, including linings, framing, insulation, fixings, junctions, penetrations, flanking paths and workmanship.

## What the bot should ask before recommending a grade

1. Where will it be installed: wall, ceiling, floor or partition?
2. Is the problem mainly airborne noise, impact noise, plumbing noise or room echo?
3. Is the work new construction, a retrofit or a repair?
4. Will the material be installed behind plasterboard or within another tested system?
5. Is there a specified whole-system Rw/STC target?
6. What area must be covered, including laps and cutting waste?
7. Are roll weight, access and manual handling important constraints?
8. Are there fire, moisture, UV-exposure or other project-specific requirements?

If the problem is room echo or reverberation, recommend an absorptive acoustic product instead of presenting NuWave as the complete solution. If the problem is impact noise through a floor, check whether the dedicated Thermotec carpet underlay or another tested floor system is required.

## Selection logic

- Recommend the lightest grade that is supported by the acoustic design or project specification.
- Do not promise that moving from one grade to another will improve the completed room or wall by the numerical difference between their product Rw values.
- Prefer 4 kg/m² as a discussion starting point only when the user has no specified grade; Thermotec describes it as its popular option for installation behind plasterboard.
- Escalate to an acoustic consultant or the manufacturer where a regulatory target, tenancy separation, studio-grade result, healthcare requirement or other critical outcome applies.
- Calculate quantity from covered area and the confirmed current roll dimensions. Include allowance for joints, edges, penetrations and waste.

## Installation overview

Thermotec's published installation guidance describes the following general sequence:

1. Measure the installation area.
2. Cut NuWave to size with a straight blade and T-square.
3. Begin at the ceiling and allow the material to hang evenly toward the floor.
4. Secure it using the fixing method suitable for the substrate, such as screws, nails or staples.
5. Make close, accurate cuts around outlet boxes and other penetrations.
6. Maintain continuity at edges, seams and penetrations; use an appropriate acoustic sealant where specified.
7. Install the plasterboard or other lining over the barrier.

The bot should describe this only as an overview. It should direct the installer to the current Thermotec installation guide and the project system specification for fixing patterns, overlaps, junctions, electrical details and other construction requirements.

## Important limitations and warnings

- NuWave primarily addresses airborne sound transmission. It is not automatically the correct solution for impact noise, reverberation or structure-borne vibration.
- Rw is not NRC. Do not populate an NRC field from the NuWave Rw value.
- NuWave does not have a meaningful thermal R-value in the supplied product information. Use `Not stated` for thermal R-value.
- A product Rw must not be represented as the Rw/STC of a completed wall, floor or ceiling.
- Acoustic performance can be undermined by gaps, unsealed edges, penetrations and flanking paths.
- Confirm fire, moisture, UV, exposure and lining requirements for the actual project.
- Confirm safe manual handling before recommending heavier grades or large rolls.
- Do not apply this base-product write-up automatically to NuWave Carpet Underlay, NuWave CrossTalk, NuWrap pipe lagging, foil-faced variants or UV-treated fence products. Those are separate products or configurations and need their own records.

## Product-family boundaries for the raw data

Use separate family identifiers so the bot does not mix unlike products:

| Product/configuration | Recommended family ID | Treatment |
| --- | --- | --- |
| NuWave Base 2/4/6/8/10 kg/m² | `THERMOTEC_NUWAVE_BASE_MLV` | Covered by this article |
| NuWave Base half rolls | `THERMOTEC_NUWAVE_BASE_MLV` | Same material; retain separate SKU and roll dimensions |
| State-specific inventory records | `THERMOTEC_NUWAVE_BASE_MLV` | Same technical family; region is an inventory attribute |
| 4-Zero foil-faced MLV NuWave | `THERMOTEC_NUWAVE_FOIL_FACED_MLV` | Separate configuration; do not inherit all base claims without its technical source |
| UV-treated NuWave fence insulation | `THERMOTEC_NUWAVE_FENCE_MLV` | Separate external-use configuration; confirm UV and installation data |
| Underlay NuWave | `THERMOTEC_NUWAVE_UNDERLAY` | Separate floor/impact-noise product record |
| NuWave CrossTalk | `THERMOTEC_NUWAVE_CROSSTALK` | Separate ceiling-plenum/CAC system |
| NuWrap 5 | `THERMOTEC_NUWRAP_5` | Composite acoustic pipe lagging, not base MLV sheeting |

## Recommended structured fields

```json
{
  "manufacturer": "Thermotec Australia",
  "brand": "NuWave",
  "family_id": "THERMOTEC_NUWAVE_BASE_MLV",
  "product_type": "Mass loaded vinyl acoustic barrier",
  "material": "Hybrid polymer mass loaded vinyl",
  "primary_function": "Reduce airborne sound transmission",
  "applications": ["wall", "floor", "ceiling", "partition"],
  "surface_mass_kg_m2": 4,
  "product_rw": 26,
  "thermal_r_value": null,
  "nrc": null,
  "system_rating_warning": "Product Rw is not the rating of the completed building assembly.",
  "installation_location": "Concealed within the specified construction assembly",
  "source_status": "manufacturer_supported",
  "source_url": "https://thermotec.com.au/products/nuwave_mlv_acoustic_barriers_2"
}
```

Create one record per surface-mass grade and SKU. Keep the technical family record separate from commercial fields such as price, stock, warehouse, state and supplier SKU.

## Approved short bot response

> Thermotec NuWave is a flexible mass loaded vinyl barrier used to reduce airborne noise through walls, floors, ceilings and partitions. Standard grades range from 2 to 10 kg/m², with manufacturer-published product ratings from Rw 24 to Rw 34. The correct grade depends on the construction and required whole-system performance. NuWave is normally installed continuously behind a lining such as plasterboard, with seams, edges and penetrations carefully sealed. The product Rw must not be treated as the rating of the completed wall or floor.

## Source notes

- Primary product source: [Thermotec NuWave Mass Loaded Vinyl Acoustic Barrier](https://thermotec.com.au/products/nuwave_mlv_acoustic_barriers_2)
- Installation context: [Thermotec, Achieving next level home acoustics with MLV](https://thermotec.com.au/news/MLV%20Mass%20Loaded%20Vinyl)
- The Google Sheet currently contains NuWave-related records in `Sheet1!573:591`. Some entries are distinct configurations and should be split according to the family-boundary table above.
