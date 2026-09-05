# Implementation Quick-Start Guide

## Part 1: Understanding the Thermotec NuWave Template

The Thermotec NuWave documentation demonstrates the required depth. Let's break down the key sections you need to replicate for each new manufacturer family:

### Section 1: Front Matter (YAML metadata)
```yaml
---
family_id: MANUFACTURERNAME_CATEGORY_VARIANT  # e.g., AUTEX_BATT_THERMAL
manufacturer: Manufacturer Full Name
canonical_name: Product Family Descriptive Name
category: Product Category (Batt, Board, Wrap, etc.)
primary_function: What it does (thermal, acoustic, vapor control, etc.)
bot_mode: demo_family_recommendation
recommendation_allowed: true
validation_status: manufacturer_supported
last_validated: 2026-09-05  # today's date
official_product_url: https://link-to-product-page
official_datasheet_url: https://link-to-tds-pdf
---
```

### Section 2: Canonical Description (150-300 words)
**Must include:**
- What this product IS (specific, technical)
- What this product IS NOT (exclusions)
- System context (component vs. system)
- Manufacturer origin

**Example template:**
```
Manufacturer {{name}} {{category}} is a {{material}} product designed for {{primary_application}}. 
It is manufactured in {{location}} and {{key_attribute_1}} and {{key_attribute_2}}.

{{Product name}} is [specifically what it does]. It must be combined with {{compatible_systems}} 
and must not be used for {{excluded_applications}}.

{{Product name}} is NOT {{common_misconception_1}}, {{common_misconception_2}}, or a standalone 
{{wrong_classification}}. It must be installed as part of a complete system per {{standard}}.
```

### Section 3: Manufacturer-Supported Facts (bulleted list)
**Must list all of:**
- Product type
- All available grades/variants
- Performance ratings with test methods
- Material composition as manufacturer describes it
- Current applications
- Manufacturing/source information
- Compliance status

### Section 4: Grade & Catalogue Reconciliation (table format)

| Variant/Grade | Performance Rating | Dimensions | Coverage | Weight | Sheet SKU | Notes |
|---|---|---|---|---|---|---|
| Grade 1 | R1.5 / 25mm | 1160×430mm | 0.5 m² | 2.3 kg | SKU-001 | Current base |
| Grade 2 | R2.5 / 50mm | 1160×430mm | 0.5 m² | 3.8 kg | SKU-002 | Wide cavity |
| Grade 3 | R4.0 / 75mm | 1160×430mm | 0.5 m² | 5.2 kg | SKU-003 | Deep cavity only |

**Critical:** Verify these against:
1. Current manufacturer TDS
2. Master SKU catalogue
3. Reseller product listings
4. Cross-check coverage = dimension 1 × dimension 2

### Section 5: Application Boundaries

**Within this family:**
- Application 1 with context
- Application 2 with context
- Application 3 with context

**Not for this family - refer to:**
| Alternative Need | Recommended Family | Why |
|---|---|---|
| Acoustic performance needed | {{FAMILY_ID}} | This family is not acoustic-rated |
| Fire performance needed | {{FAMILY_ID}} | This family has no fire certification |

### Section 6: Customer Priority Profile

| Priority | Score | Confidence | Why |
|---|---:|---|---|
| Energy efficiency | 5 | High | Primary function is thermal insulation |
| Acoustic comfort | 2 | Low | Incidental only; not acoustic product |
| Sustainability | 3 | Medium | {{reason_detail}} |

**Rule:** Each score must be justified by a reference to:
1. Product function or design
2. Manufacturer claims or test results
3. Limitations or exclusions

### Section 7: Human Review Gates

| Requirement | Status | Bot Action |
|---|---|---|
| Compliance (NCC/BAL/Fire) | CONDITIONAL | Record requirement, **do not confirm**, arrange human review |
| Grade/SKU selection | NOT AUTOMATED | User tells bot their need, bot collects info, human chooses SKU |
| R-value sufficiency | PENDING DESIGN | Record target, human verifies against complete wall design |
| Regional availability | VARIABLE | Record location, human checks current stock |

### Section 8: Aircall Enquiry Flow

**Natural, progressive questions** (not a rigid checklist):
1. "What are you trying to achieve - thermal insulation, acoustic control, moisture protection, or something else?"
2. "Is this for a new build, renovation, or repair?"
3. "Where is this going - walls, ceiling, floor, or a specialty application?"
4. (If thermal) "Do you know the cavity depth or framing system?"
5. (If compliance) "Are you working from plans or a specification?"
6. "What's most important to you - performance, cost, installation speed, or minimizing thickness?"

**Don't ask:**
- "Which grade do you want?" (let them describe the problem)
- "Will R1.5 or R2.5 be sufficient?" (human job)
- "Is this NCC-compliant?" (human job)

### Section 9: Approved Customer Language

**When explaining the product:**
> {{Brand}} {{Category}} is a {{material}} insulation product designed for {{application}}. The appropriate grade depends on your cavity, climate zone, and any project requirements. I can collect the details and have our team review.

**When asked which grade:**
> I can't choose a grade without knowing your cavity depth and building design. If you tell me those details, our team can recommend the right product.

**When asked about compliance:**
> Compliance depends on the complete wall or system. I will pass your requirements to our team for review and they'll confirm what's appropriate.

---

## Part 2: Step-by-Step Implementation for One Manufacturer

### Example: Autex Batt Family

**Step 1: Gather Information (2-3 hours)**

Research sources:
1. Manufacturer TDS: https://autex.co.nz/products/ (find batt TDS)
2. Product pages: Autex website, reseller sites
3. Master catalogue: Extract all Autex batt SKUs
4. Certifications: Look for R-value tests, fire ratings, EPDs

Document findings:
- All available batt grades and R-values
- Performance ratings (R, NRC, fire class if available)
- Dimensions of standard products
- Available in Australia? New Zealand? Both?
- Key differentiators vs. Fletcher/Thermotec/Bradford

**Step 2: Create YAML Front Matter (0.5 hours)**

```yaml
---
family_id: AUTEX_BATT_THERMAL
manufacturer: Autex Limited
canonical_name: Autex Polyester Batt Insulation
category: Polyester fiber batt
product_family: Thermal insulation batts
brand: Autex
material: 100% recycled polyester fiber
primary_function: Thermal insulation in wall, ceiling and floor cavities
primary_noise_type: Airborne and impact (acoustic secondary benefit)
bot_mode: demo_family_recommendation
recommendation_allowed: true
recommendation_scope: manufacturer_supported_family_only
requires_human_selection: true
validation_status: manufacturer_supported
last_validated: 2026-09-05
official_product_url: https://autex.co.nz/products/autex-batt/
official_datasheet_url: [TO BE ADDED - fetch from Autex]
official_installation_url: [TO BE ADDED - fetch from Autex]
---
```

**Step 3: Write Canonical Description (1-2 hours)**

Template:
```
# Autex Polyester Batt Insulation

Autex Batt is an Australian/New Zealand-made thermal insulation product 
comprising 100% recycled polyester fiber, designed to resist settling and 
provide long-term thermal performance in building cavities.

[Key facts from TDS]:
- Moisture tolerant (compared to glasswool)
- Non-combustible per [test standard]
- R-values from R1.5 to R5.0
- Available in standard batt widths
- Manufacturer warrants performance for [X years]

Autex Batt is designed as a cavity fill and must be combined with 
appropriate framing, linings and vapor control appropriate to your climate. 
It is NOT thermal insulation for exposed applications, floor underlay, 
or acoustic absorption (though it provides minor acoustic benefit).
```

**Step 4: Extract Grade Information (1 hour)**

From TDS and master catalogue:
```
| Autex Grade | R-Value | Thickness | Width | Length | Coverage | Mass |
|---|---|---|---|---|---|---|
| R1.5 | R1.5 | 50mm | 580mm | 1200mm | 0.7 m² | 1.1 kg |
| R2.5 | R2.5 | 75mm | 580mm | 1200mm | 0.7 m² | 1.8 kg |
| R4.0 | R4.0 | 120mm | 580mm | 1200mm | 0.7 m² | 2.9 kg |
| R5.0 | R5.0 | 150mm | 580mm | 1200mm | 0.7 m² | 3.6 kg |

Source: Autex TDS 2026-Q3; Google Sheet snapshot [date]
Note: Width varies by market (580mm AU, 600mm NZ); verify current availability
```

**Step 5: Define Application Boundaries (1 hour)**

Within family:
- Residential wall cavities (timber and steel frame)
- Ceiling cavities
- Floor cavities (not underlay)
- Non-fire-rated buildings or residential applications

Separate families:
- Polyester underlay → [DIFFERENT_FAMILY] (floor impact noise)
- Acoustic board → [DIFFERENT_FAMILY] (surface treatment, not cavity fill)
- Fire-rated systems → [Refer to compliance specialist]

**Step 6: Customer Priority Profile (1 hour)**

Research and assign:
| Priority | Score | Confidence | Interpretation |
|---|---:|---|---|
| Energy efficiency | 5 | High | Primary function is thermal R-value performance per TDS |
| Acoustic comfort | 2 | Low | Incidental acoustic benefit, not primary design; not acoustic product |
| Sustainability | 4 | High | 100% recycled polyester is significant sustainability advantage; no fire retardants |
| Installation practicality | 4 | High | Batt format fits standard cavities; slight compression tolerance vs. glasswool |
| Compliance readiness | 3 | Medium | R-value and non-combustibility verified; exact NCC compliance depends on system |

**Step 7: Define Human Review Gates (1 hour)**

| Gate | Status | Action |
|---|---|---|
| R-value sufficiency | CONDITIONAL | Collect building design info (cavity depth, frame type, climate), human confirms R-value selection |
| Cavity fit | REQUIRED | Human verifies cavity dimensions, batt width compatibility |
| Vapor control | CONDITIONAL | Climate-dependent; human confirms condensation strategy |
| NCC compliance | PENDING SYSTEM | Human confirms within complete wall system |
| Regional availability | VARIABLE | Autex batt AU/NZ split; human checks current stock for project location |

**Step 8: Aircall Enquiry Flow (1 hour)**

Natural progression:
1. "What area are you insulating - a new build renovation, or repair?"
2. "Is that walls, ceilings, floors, or a combination?"
3. "Do you know your cavity depth - how much space we're working with?"
4. "Is there any particular R-value or building code requirement?"
5. "Are you in Australia or New Zealand?" (affects availability/specification)
6. "What's most important - the R-value level, budget, or ease of installation?"
7. "Would you prefer to call us directly or request a callback?"

**Step 9: Approved Language (30 min)**

When explaining:
> Autex Batt is a thermal insulation product made from recycled polyester. The right R-value depends on your cavity depth and climate zone. I can collect those details for our team to confirm.

When asked "which grade":
> I can't recommend a specific grade without knowing your cavity size and building design. Tell me those details and our team will confirm the right product.

**Step 10: Source Hierarchy (30 min)**

Tier 1 (primary):
- [Autex TDS link]
- [Autex product page link]

Tier 2 (internal):
- Google Sheet Autex batt rows [rows X-Y]
- SKU mapping: SKU-001 → Autex R1.5 580×1200

Tier 3 (secondary):
- [Reseller site links]
- Autex sustainability datasheet (if available)

**Step 11: JSON Record (30 min)**

```json
{
  "family_id": "AUTEX_BATT_THERMAL",
  "recommendation_level": "family_only",
  "best_for": [
    "residential wall thermal insulation",
    "ceiling cavity thermal performance",
    "thermal upgrade in renovations"
  ],
  "current_material_r": ["R1.5", "R2.5", "R4.0", "R5.0"],
  "required_inputs": [
    "cavity_depth_mm",
    "frame_type",
    "climate_zone",
    "target_r_value"
  ],
  "human_gates": [
    "sku_selection",
    "cavity_fit_verification",
    "regional_availability",
    "total_r_value_confirmation",
    "vapor_control_design"
  ],
  "exclusions": [
    "exposed_applications",
    "floor_underlay_impact_noise",
    "acoustic_absorption_primary",
    "fire_rated_systems"
  ]
}
```

**Step 12: Final Quality Check (30 min)**

Checklist:
- [ ] All YAML fields filled
- [ ] No "TBD" placeholders
- [ ] TDS/SDS URLs verified working
- [ ] Grade table cross-checked against source
- [ ] No conflation of R vs. Rw
- [ ] Application boundaries explicit
- [ ] Human gates clearly defined
- [ ] Aircall flow is natural conversational progression
- [ ] Customer language is in plain English
- [ ] Source hierarchy documented
- [ ] JSON syntax valid

---

## Part 3: Batch Implementation for Priority 1

**Week 1-2 Target:** Autex + Bradford (7 families total)

For each family:
1. Gather info: 2-3 hours
2. Write documentation: 6-8 hours
3. Quality review: 1-2 hours
**Per family: ~12-15 hours**

**Total for 7 families: 84-105 hours (~2-3 person-weeks)**

### Daily Workflow Example

**Day 1 (Autex Batt):**
- Morning: Research TDS, compile grade table (2h)
- Afternoon: Write canonical description, define boundaries (2h)
- Evening: Create YAML front matter, Aircall flow (2h)

**Day 2 (Autex Batt - continued):**
- Morning: Priority profile, human gates (1.5h)
- Afternoon: Approved language, source hierarchy, JSON (2h)
- Evening: Quality review, corrections (1.5h)

**Day 3 (Autex Panel):**
- Repeat pattern for next family

---

## Part 4: Tools & Templates

### Folder Structure
```
knowledge/
├── autex/
│   ├── families.json (updated from initial)
│   ├── README.md (updated from initial)
│   ├── batt.md (complete deep-dive)
│   ├── panel.md (complete deep-dive)
│   ├── accessory.md (complete deep-dive)
│   └── _sources.json (new: evidence tracking)
```

### File Checklist (per family markdown)
- [ ] 25+ YAML front-matter fields
- [ ] Canonical description (200-300 words)
- [ ] Manufacturer-supported facts table
- [ ] Grade reconciliation table
- [ ] Application boundaries section
- [ ] Cross-family references
- [ ] Installation context
- [ ] Customer priority profile (5-point scores)
- [ ] Mandatory human-review gates
- [ ] Aircall enquiry flow (10+ questions)
- [ ] Approved customer language blocks
- [ ] Language controls (prefer/avoid)
- [ ] Source reconciliation (3 tiers)
- [ ] JSON machine-readable record
- [ ] Performance evidence table

### Validation Commands
```powershell
# Check for "TBD" placeholders
Get-ChildItem -Path knowledge -Recurse -Filter "*.md" | 
  Select-String -Pattern "\[TBD\]|\[TODO\]|TO BE" | 
  Select-Object Path, LineNumber, Line

# Validate JSON syntax
Get-ChildItem -Path knowledge -Recurse -Filter "*.md" | 
  Select-String -Pattern "```json" -Context 0,20 | 
  ForEach-Object { $_.Line | python -m json.tool }

# Count documentation completeness
Get-ChildItem -Path knowledge/*/families.json | 
  ForEach-Object { [pscustomobject]@{
    Manufacturer = $_.Directory.Name
    Families = (Get-Content $_ | ConvertFrom-Json).families.Count
  }} | Format-Table
```

---

## Success Definition

When complete, EACH manufacturer family will have:
✅ Complete technical documentation (no gaps)
✅ Clear bot-friendly guidance
✅ Mandatory human-review gates
✅ Approved customer language
✅ Traceable evidence hierarchy
✅ Compliance with Thermotec/Fletcher quality standard
✅ Ready for Aircall integration
✅ Ready for sales team use

**Result:** All 52 new manufacturer families elevated to deep-dive documentation quality matching Thermotec/Fletcher standard.
