---
id: autex-greenstuf-batt
family_id: AUTEX_BATT
manufacturer: Autex
brand: GreenStuf
product_family: GreenStuf Polyester Acoustic and Thermal Batt Insulation
canonical_name: Autex GreenStuf Polyester Batt Insulation
category: Batt
material: 100% polyester fibre (includes post-consumer recycled PET)
primary_noise_type: Airborne noise and reverberation
bot_mode: demo_family_recommendation
recommendation_allowed: true
recommendation_scope: manufacturer_supported_family_only
requires_human_selection: true
validation_status: manufacturer_supported_secondary_claims_pending
last_validated: 2026-09-05
rating_framework_version: 1
priority_sustainability_score: 4
priority_sustainability_confidence: medium
priority_energy_efficiency_score: 4
priority_energy_efficiency_confidence: medium
priority_airborne_acoustic_comfort_score: 4
priority_airborne_acoustic_comfort_confidence: medium
priority_installation_practicality_score: 4
priority_installation_practicality_confidence: medium
gate_ncc_project_compliance: conditional_project_specific_evidence_required
gate_fire_compliance: not_verified_per_sku
gate_bal: not_verified
official_product_url: https://www.autex.com.au/
official_datasheet_url: https://greenstuf.co.nz/resources/data-sheets/
official_installation_url: https://greenstuf.co.nz/resources/technical-documents/
product_count: 92
performance_grades: 5
---

# Autex GreenStuf Polyester Batt Insulation

## Purpose of this file

This is the canonical internal description for the Autex (GreenStuf) Batt family. It aligns the terminology used by the enquiry bot, sales team and future Aircall CSV.

For the demonstration, the bot may recommend the **GreenStuf Batt family** when the customer's problem is thermal comfort, energy efficiency or airborne/reverberant sound control in a wall, ceiling or internal space suited to segmented batt insulation. It must not choose a specific grade, calculate order quantity, or confirm thermal, acoustic, fire, NCC or BAL compliance for a project. Those decisions remain human-reviewed.

## Canonical description

Autex GreenStuf Batt is a segmented, semi-rigid polyester fibre insulation product manufactured from 100% polyester fibre, including a significant proportion of post-consumer recycled PET plastic bottles. It is supplied as pre-cut batts sized to fit standard timber and steel wall, ceiling and floor framing centres, and is used across both thermal (R-value) and acoustic (Rw) applications depending on the specific product line and grade selected.

The family spans multiple distinct product ranges sold under the Autex/GreenStuf brand, including general-purpose thermal and acoustic wall/ceiling batts, and specialised acoustic hardware such as Frontier Fins, Frontier Raft beams/blades, Cove desk dividers and Soffit & Slab Liner (ASL) products. These specialised items are acoustic treatment components rather than concealed cavity batt insulation, and must not be treated as interchangeable with standard thermal/acoustic wall batts even though they are grouped in the same family for catalogue purposes.

GreenStuf Batt is not a fire-rated system on its own, not a complete acoustic wall/ceiling assembly, and not automatically compliant with any specific NCC or BAL requirement. Any project-specific claim about a finished construction's rating must be confirmed against a tested system that matches the proposed build-up.

## Current manufacturer-supported facts

- Product type: segmented/pre-cut polyester fibre batt insulation, plus related acoustic treatment hardware sold under the same family.
- Material: 100% polyester fibre; includes post-consumer recycled PET content.
- Primary functions across the range: thermal insulation (R-value), acoustic absorption/sound reduction (Rw, NRC), and reverberation control.
- Manufactured with low-VOC, formaldehyde-free binder system per manufacturer literature.
- No synthetic mineral fibres; does not require the same PPE precautions as glasswool/stonewool per manufacturer literature (to be confirmed against current SDS before customer-facing use).
- Supplied pre-cut to fit standard framing centres (typically 430mm/580mm/610mm nominal stud/joist spacings, product-dependent).
- The catalogue includes 92 unique SKU variants across 5 published performance grades.

## Grade and catalogue reconciliation

The following reflects the current internal SKU extraction from the master product catalogue. Manufacturer TDS values must be re-confirmed per SKU before quoting, as the internal sheet mixes acoustic (Rw) and thermal (R-value) ratings within the same family.

| Grade label (internal) | Rating type | SKU count | Typical use | Data note |
| --- | --- | ---: | --- | --- |
| R1.5 | Thermal (R-value) | 1 | Greenstuf Baffle Block — acoustic/thermal hybrid ceiling product | Outlier: only thermally-rated SKU in the Batt family; verify category placement |
| Rw 35 | Acoustic (Rw) | 48 | General internal wall/ceiling acoustic batt, standard grade | Largest single grade; majority of Frontier Fins/Raft standard kit variants |
| Rw 40 | Acoustic (Rw) | 4 | Mid-range acoustic upgrade | Current sheet rows require SKU/dimension cross-check |
| Rw 45 | Acoustic (Rw) | 4 | Higher-performance acoustic upgrade | Current sheet rows require SKU/dimension cross-check |
| Rw 50 | Acoustic (Rw) | 35 | Premium acoustic grade | Second-largest grade; includes Cove desk divider and ASL soffit/slab liner variants |

Major product lines within the family (by SKU pattern observed in the catalogue):

- **Frontier Fins** — standard kit, 12mm and 24mm thickness variants, 150mm and 300mm heights.
- **Frontier Raft** — beams and blades, 100mm and 250mm depth variants.
- **Cove Acoustic Desk Dividers** — freestanding acoustic screening panels.
- **Soffit & Slab Liner (ASL)** — underside acoustic lining for exposed soffit/slab applications.
- **Greenstuf Baffle Block** — the single R1.5 thermally-rated outlier noted above.

### Critical rating interpretation

`Rw` is a weighted sound reduction/absorption index appropriate to the specific test method used (system or material dependent) and is not automatically equivalent to a finished-wall or finished-ceiling Rw rating. `R1.5` is a thermal resistance value and must not be confused with, or substituted for, an Rw acoustic rating. Because this family mixes both rating types across its 92 SKUs, the human reviewer must confirm which rating type applies to the specific SKU before making any performance statement to a customer.

## Application boundaries

### Within the GreenStuf Batt family

- Internal wall and ceiling cavities requiring thermal insulation (R-value applications).
- Internal wall, ceiling and open-plan acoustic treatment requiring sound absorption or reduction (Rw applications).
- Suspended ceiling and soffit acoustic lining (ASL product line).
- Freestanding acoustic screening in open-plan office environments (Cove desk dividers).
- Structural acoustic hardware for fit-out fins and rafts (Frontier Fins/Raft), installed per manufacturer system drawings.

### Separate product families

Do not transfer GreenStuf Batt claims automatically to these records:

| Product/configuration | Family ID | Required treatment |
| --- | --- | --- |
| Autex Panel (rigid acoustic panel products, e.g. Vertiface) | `AUTEX_PANEL` | Separate rigid panel family; requires its own current technical evidence |
| Autex Accessory (fixings, trims, non-standard extrusions) | `AUTEX_ACCESSORY` | Installation hardware, not insulation performance product |
| Greenstuf Baffle Block (R1.5) | `AUTEX_BATT` (same family, distinct rating type) | Thermal rating only; do not apply Rw claims |

GreenStuf Batt should not be presented as a fire-rated system, a complete compliant wall/ceiling assembly, or a guaranteed noise-elimination product. Record the customer's noise type, thermal target and construction context for human review rather than confirming compliance directly.

## Installation context for enquiry handling

Manufacturer literature describes installing batts by friction-fitting between standard framing centres, ensuring full cavity fill without compression, and maintaining continuity around penetrations, services and junctions. Specialised items (Frontier Fins/Raft, Cove dividers, ASL) are installed per manufacturer system drawings and typically require mechanical fixing rather than friction-fit placement.

The bot may use this information to understand the customer's project, but must not issue project-specific installation instructions. The human reviewer must confirm:

- the complete wall, ceiling or soffit build-up and framing centres;
- whether the requirement is thermal, acoustic, or both;
- fixing method for specialised hardware items (Fins, Raft, Cove, ASL);
- junction, penetration and service-cavity treatment;
- moisture and vapour-control requirements for the specific application;
- manual-handling requirements;
- the current Autex/GreenStuf installation guide and project specification.

## Customer-priority profile

These ratings are internal conversation aids. They determine useful follow-up questions and callback notes; they do not rank or recommend products to customers.

| Customer priority | Internal rating | Confidence | Interpretation |
| --- | ---: | --- | --- |
| Sustainability | 4/5 | Medium | Manufacturer literature claims significant post-consumer recycled PET content and GreenTag/EPD certification. Product-specific current certificate has not yet been verified against this specific SKU range. |
| Energy efficiency | 4/5 | Medium | Applicable to the thermal (R-value) portion of the range, but only 1 of 92 SKUs currently carries a published R-value; most SKUs are Rw-rated acoustic products with no verified thermal claim. |
| Airborne acoustic comfort | 4/5 | Medium | Primary documented purpose for 91 of 92 SKUs (Rw 35–50). Actual comfort depends on the complete installed construction and specific product line selected. |
| Installation practicality | 4/5 | Medium | Pre-cut batts fit standard framing centres; specialised hardware (Fins, Raft, Cove, ASL) requires manufacturer system drawings and may need mechanical fixing expertise. |

## Mandatory human-review gates

| Requirement | Status for GreenStuf Batt | Enquiry-bot action |
| --- | --- | --- |
| Acoustic target / NCC | CONDITIONAL | Record the building type, construction and any Rw target. Do not confirm compliance; arrange human review. |
| Thermal target / NCC | CONDITIONAL | Record the required R-value and climate zone. Note that only the R1.5 Baffle Block SKU carries a published thermal rating in this family; arrange human review before recommending for thermal-only requirements. |
| Fire requirement | NOT VERIFIED PER SKU | Do not assume fire rating applies across all 92 SKUs. Record the required fire test, classification or system and arrange human review. |
| BAL / bushfire construction | NOT VERIFIED | Record the site's BAL and the external building element involved. Do not describe GreenStuf Batt as BAL-compliant; arrange human review. |
| Rating-type mismatch | REQUIRES CONFIRMATION | Confirm whether the customer's stated requirement is thermal (R) or acoustic (Rw) before referencing any specific grade, given the mixed rating types in this family. |

## Aircall enquiry flow

The voice agent should gather information naturally rather than interrogating the caller with technical questions they may not understand.

1. What are you trying to improve — warmth/energy efficiency, noise control, or both?
2. Where is the problem: internal wall, ceiling, open-plan office, soffit/slab underside, or somewhere else?
3. Is the noise issue mainly sound passing between rooms, echo/reverberation within a room, or something else?
4. Is this a home, apartment, office fit-out, commercial building or other project?
5. Is it a new build, renovation, retrofit or repair?
6. What is most important: sustainability, energy efficiency, acoustic comfort, budget, or ease of installation?
7. Do plans, a consultant or a certifier specify a thermal R-value, acoustic Rw, NCC or BAL requirement?
8. What is the approximate area, if known, and standard framing centres if known?
9. Are you looking for standard cavity batt insulation, or specialised hardware such as acoustic fins, desk dividers, or soffit lining?
10. Would the caller prefer to phone the team directly or request a callback?

The agent must not ask the caller to choose a specific grade or SKU. If the caller names a grade, record it as caller-provided information rather than confirming it.

## Approved customer-facing language

### General explanation

> Autex GreenStuf Batt is a polyester fibre insulation range made largely from recycled plastic bottles. It's used for both thermal comfort and acoustic control depending on the specific product and grade, and it also includes some specialised acoustic hardware for fit-outs. I can collect the details for our team to review and recommend the right product.

### When asked which grade to buy

> I cannot select a specific grade or confirm the result of an installed system. If you tell me whether you need warmth, noise control, or both, along with the location and any project requirements, I can prepare the enquiry for our team. Would you prefer to call them or request a callback?

### When asked about compliance or BAL

> Compliance and bushfire suitability depend on the complete construction and supporting documentation for the specific product selected. I cannot confirm that from a product name alone. I will flag this for technical review and arrange the next contact step.

## Language controls

Prefer:

- "designed to reduce airborne sound transmission" or "designed to improve thermal comfort" (as applicable to the specific SKU);
- "manufacturer-published product Rw" or "manufacturer-published R-value";
- "complete construction" or "complete installed system";
- "requires confirmation by our team";
- "customer-stated requirement" when recording a target.

Avoid:

- "soundproof" or "eliminates noise";
- treating a single SKU's rating as representative of the whole 92-SKU family;
- confusing thermal R-value and acoustic Rw ratings;
- "best," "perfect," "guaranteed" or "compliant";
- calling any GreenStuf Batt SKU fire-rated or BAL-rated without current verification;
- asserting exact recycled-content percentage, EPD status, or formaldehyde-free claims until current supporting documentation is accepted for that specific SKU.

## Source reconciliation and evidence hierarchy

### Tier 1 — current manufacturer source

[Autex Australia](https://www.autex.com.au/) and [GreenStuf Technical Documents](https://greenstuf.co.nz/resources/technical-documents/)

Use this source for the canonical product identity, current grades, published R-values/Rw values, primary applications and material composition.

### Tier 2 — current internal catalogue

The master product catalogue provides current commercial records for 92 SKUs, including internal SKU codes, dimensions, grade labels and stock. Commercial data does not validate technical performance; the 5 grade labels (R1.5, Rw 35/40/45/50) are taken from this sheet and must be cross-checked against current manufacturer TDS per SKU before quoting.

Current data issues to correct before Aircall CSV export:

- Confirm whether Greenstuf Baffle Block (R1.5) should remain classified under Batt or be reclassified as a distinct product type given its thermal-only rating.
- Rw 40 and Rw 45 grades (4 SKUs each) require dimension and SKU cross-check against current manufacturer literature.
- Frontier Fins/Raft/Cove/ASL specialised hardware items require separate installation and system-drawing references distinct from standard cavity batt SKUs.

### Tier 3 — authorised owned-site literature

- [GreenStuf Data Sheets](https://greenstuf.co.nz/resources/data-sheets/)
- [Global GreenTag — GreenStuf Acoustic Insulation](https://www.globalgreentag.com/products/greenstuf-acoustic-insulation/)
- [MBS Architectural — Autex Greenstuf Polyester Insulation](https://assets-global.website-files.com/62e7ebd286b041af8c52e785/6400d1caf7c99083d6399fa7_MBS%20Architectural%20-%20Insulation%20-%20Autex%20Greenstuf%20Polyester%20Insulation.pdf)

These pages are useful for application language, customer vocabulary and commercial context. Claims appearing only in this literature (exact recycled-content percentage, 50-year warranty, specific certification numbers) remain pending until matched to an accepted current TDS, SDS or certification document for the specific Australian-market SKU range.

## Machine-readable family record

```json
{
  "family_id": "AUTEX_BATT",
  "manufacturer": "Autex",
  "canonical_name": "Autex GreenStuf Polyester Batt Insulation",
  "bot_mode": "demo_family_recommendation",
  "recommendation_allowed": true,
  "recommendation_scope": "manufacturer_supported_family_only",
  "primary_function": "Thermal insulation and/or acoustic sound absorption/reduction depending on SKU",
  "material": "100% polyester fibre (post-consumer recycled PET content)",
  "applications": ["internal_wall", "ceiling", "soffit_slab_underside", "open_plan_office"],
  "product_count": 92,
  "grades": [
    {"grade_label": "R1.5", "rating_type": "thermal_r_value", "sku_count": 1},
    {"grade_label": "Rw 35", "rating_type": "acoustic_rw", "sku_count": 48},
    {"grade_label": "Rw 40", "rating_type": "acoustic_rw", "sku_count": 4},
    {"grade_label": "Rw 45", "rating_type": "acoustic_rw", "sku_count": 4},
    {"grade_label": "Rw 50", "rating_type": "acoustic_rw", "sku_count": 35}
  ],
  "product_lines": ["Frontier Fins", "Frontier Raft", "Cove Acoustic Desk Dividers", "Soffit & Slab Liner (ASL)", "Greenstuf Baffle Block"],
  "priority_profile": {
    "sustainability": {"score": 4, "confidence": "medium"},
    "energy_efficiency": {"score": 4, "confidence": "medium"},
    "airborne_acoustic_comfort": {"score": 4, "confidence": "medium"},
    "installation_practicality": {"score": 4, "confidence": "medium"}
  },
  "human_review_gates": {
    "ncc_and_project_compliance": "conditional_project_specific_evidence_required",
    "fire": "not_verified_per_sku",
    "bal": "not_verified",
    "rating_type_mismatch": "requires_confirmation"
  },
  "callback_required": true,
  "source_url": "https://www.autex.com.au/"
}
```

## Performance evidence summary

| Evidence type | Status | Reference |
| --- | --- | --- |
| Thermal R-value (R1.5 SKU) | Manufacturer-published, not yet SKU-matched to current TDS | GreenStuf Data Sheets |
| Acoustic Rw (Rw 35/40/45/50) | Manufacturer-published, not yet SKU-matched to current TDS | GreenStuf Data Sheets |
| Material composition (100% polyester, recycled PET) | Manufacturer-claimed, general product line | Autex/GreenStuf website |
| Fire performance | Not verified per SKU | Pending SDS/test report review |
| Environmental certification (GreenTag/EPD) | Manufacturer-claimed, not yet product-specific verified | Global GreenTag listing |

## Quality checklist validation

- [x] 25+ YAML front-matter fields present
- [x] 200-300 word canonical description
- [x] Manufacturer-supported facts table present
- [x] Grade reconciliation table covers all 5 published grades and 92 SKUs
- [x] Application boundaries with explicit inclusions/exclusions
- [x] Installation context documented (non-project-specific)
- [x] Customer priority profile with confidence scoring
- [x] Mandatory human-review gates documented
- [x] Aircall enquiry flow with 10 questions
- [x] Approved customer-facing language for 3 scenarios
- [x] Language controls (prefer/avoid lists)
- [x] 3-tier source hierarchy documented
- [x] JSON machine-readable record included
- [x] Performance evidence summary table included
- [x] Rating-type mismatch (thermal vs acoustic) explicitly flagged given mixed grades
- [x] Outlier SKU (R1.5 Baffle Block) explicitly documented
- [x] Specialised hardware lines (Fins/Raft/Cove/ASL) distinguished from standard cavity batts
- [x] Last validated date recorded in front matter

---

*This documentation was created 2026-09-05 as the first Phase 1 deep-dive family (Autex Batt), following the Thermotec NuWave documentation standard. It replaces the initial template generated 2026-09-05 and requires ongoing validation against primary manufacturer sources as current TDS/SDS documents are obtained per SKU.*
