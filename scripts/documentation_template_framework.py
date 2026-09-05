"""
Template for generating deep-dive family documentation matching Thermotec/Fletcher quality.
This script creates comprehensive product family markdown files with all required sections.
"""

FAMILY_DOCUMENTATION_TEMPLATE = """---
family_id: {family_id}
manufacturer: {manufacturer}
canonical_name: {canonical_name}
category: {category}
product_family: {product_family}
brand: {brand}
material: {material}
primary_function: {primary_function}
primary_noise_type: {primary_noise_type}
bot_mode: demo_family_recommendation
recommendation_allowed: true
recommendation_scope: manufacturer_supported_family_only
requires_human_selection: true
validation_status: manufacturer_supported
last_validated: {validation_date}
rating_framework_version: 1
priority_sustainability_score: {sustainability_score}
priority_sustainability_confidence: {sustainability_confidence}
priority_energy_efficiency_score: {energy_score}
priority_energy_efficiency_confidence: {energy_confidence}
priority_acoustic_comfort_score: {acoustic_score}
priority_acoustic_comfort_confidence: {acoustic_confidence}
gate_ncc_project_compliance: {ncc_gate}
gate_fire_compliance: {fire_gate}
gate_bal: {bal_gate}
official_product_url: {product_url}
official_datasheet_url: {tds_url}
official_installation_url: {installation_url}
---

# {canonical_name}

## Purpose of this file

This is the canonical internal description for {brand} {category}. It aligns the terminology used by the enquiry bot, sales team and future Aircall CSV.

For the demonstration, the bot may recommend the **{brand} {category}** family when {recommendation_trigger}. It must not choose a grade, calculate an order quantity or confirm acoustic, fire, NCC or BAL compliance. Those decisions remain human-reviewed.

## Canonical description

{detailed_product_description}

## Current manufacturer-supported facts

- Product type: {product_type}
- Primary function: {primary_function_detailed}
- Standard grades/variants: {available_grades}
- Manufacturer-published performance ratings: {performance_ratings}
- Current manufacturer material description: {material_description}
- Confirmed manufacturer applications: {applications}
- Manufacturing location: {manufacturing_location}
- Certification/compliance status: {certifications}

## Grade and catalogue reconciliation

{grade_table}

The figures are current manufacturer-published product ratings. The commercial dimensions and weights below are taken from the current Google Sheet snapshot and must be checked against live availability before quoting.

## Application boundaries

### Within the {brand} {category} family

- {application_1}
- {application_2}
- {application_3}
- {application_4}

### Separate product families

Do not transfer {brand} {category} claims automatically to these records:

| Product/configuration | Family ID | Required treatment |
| --- | --- | --- |
{cross_family_references}

{brand} {category} should not be presented as the complete answer for {exclusions}. Record the requirement for human review rather than suggesting an alternative product.

## Installation context for enquiry handling

{installation_context}

The bot may use this information to understand the customer's project, but must not issue project-specific installation instructions. The human reviewer must confirm:

{installation_confirmations}

## Customer-priority profile

These ratings are internal conversation aids. They determine useful follow-up questions and callback notes; they do not rank or recommend products to customers.

| Customer priority | Internal rating | Confidence | Interpretation |
| --- | ---: | --- | --- |
| Sustainability | {sustainability_score}/5 | {sustainability_confidence} | {sustainability_interpretation} |
| Energy efficiency | {energy_score}/5 | {energy_confidence} | {energy_interpretation} |
| {priority_3} | {score_3}/5 | {confidence_3} | {interpretation_3} |

## Mandatory human-review gates

| Requirement | Status for {brand} {category} | Enquiry-bot action |
| --- | --- | --- |
{human_gates_table}

## Aircall enquiry flow

The voice agent should gather information naturally rather than interrogating the caller with technical questions they may not understand.

{enquiry_flow}

The agent must not ask the caller to choose a {brand} {category} grade. If the caller names a grade, record it as caller-provided information rather than confirming it.

## Approved customer-facing language

### General explanation

> {general_explanation}

### When asked which product/grade to buy

> {grade_selection_language}

### When asked about compliance or requirements

> {compliance_language}

## Language controls

Prefer:

{preferred_language}

Avoid:

{avoid_language}

## Source reconciliation and evidence hierarchy

### Tier 1 — current manufacturer source

{tier_1_sources}

Use these sources for the canonical product identity, current grades, product ratings, primary applications and manufacturing location.

### Tier 2 — current internal catalogue

The Google Sheet provides current commercial records for dimensions, coverage, mass, regional variants, internal SKUs, stock and warehouse information. Commercial data does not validate technical performance.

Current data issues to correct before Aircall CSV export:

{catalogue_issues}

### Tier 3 — authorised owned-site literature

{tier_3_sources}

These pages are useful for application language, customer vocabulary, historical catalogue information and commercial context. Claims appearing only in this older literature remain pending until matched to an accepted current TDS, SDS, test report or environmental document.

## Machine-readable family record

```json
{json_family_record}
```

## Performance Evidence Summary

| Metric | Value | Test Standard | Confidence |
| --- | --- | --- | --- |
{performance_evidence_table}

## Next Steps for Evidence Collection

1. {next_step_1}
2. {next_step_2}
3. {next_step_3}
"""

QUALITY_CHECKLIST = """
# Deep-Dive Documentation Quality Checklist

## Structure Requirements
- [ ] Front matter with all required YAML fields
- [ ] Canonical description (1-2 paragraphs)
- [ ] Manufacturer-supported facts table
- [ ] Grade/catalogue reconciliation table
- [ ] Application boundaries clearly defined
- [ ] Cross-family references documented
- [ ] Installation context section
- [ ] Customer-priority profile (5-point ratings)
- [ ] Mandatory human-review gates table
- [ ] Aircall enquiry flow (natural language conversation)
- [ ] Approved customer-facing language blocks
- [ ] Language control guidelines (prefer/avoid)
- [ ] Source reconciliation (3-tier hierarchy)
- [ ] Machine-readable JSON record
- [ ] Performance evidence summary table

## Content Requirements
- [ ] Product type clearly identified
- [ ] Primary function vs. secondary uses distinguished
- [ ] All available grades/variants listed with performance
- [ ] Limitations and exclusions explicitly stated
- [ ] Installation requirements without project-specific instructions
- [ ] Scoring rationale for each priority dimension
- [ ] No claims beyond supported scope (thermal R ≠ acoustic Rw)
- [ ] Material composition accurately described
- [ ] Compliance/certification status clearly bounded
- [ ] Regional variants handled appropriately

## Evidence Requirements
- [ ] Current manufacturer TDS linked and reviewed
- [ ] SDS (Safety Data Sheet) available
- [ ] Product certifications verified
- [ ] Performance ratings from primary source
- [ ] Installation guide from manufacturer
- [ ] All claims traceable to documented source
- [ ] Pending evidence identified explicitly
- [ ] Evidence quality hierarchy documented

## Audience Readiness
- [ ] Bot can use this to understand customer needs
- [ ] Sales team has clear approved language
- [ ] Human reviewers know what to verify
- [ ] Internal team aligned on scope and gates
- [ ] Aircall CSV generation possible from JSON
- [ ] No conflation of material R, total R, Rw, NRC
- [ ] No false claims about compliance/suitability
- [ ] No project-specific recommendations by bot

## Completeness Indicators
- [ ] No "TBD" or "[TO BE FILLED]" placeholders
- [ ] All cross-references validated
- [ ] All URLs tested and working
- [ ] JSON syntax correct and valid
- [ ] No assumptions about evidence not yet obtained
- [ ] Clear scope: what this family IS and IS NOT
"""

print("""
DOCUMENTATION ESCALATION FRAMEWORK

Current State: 24 manufacturers with initial template structure
Target State: All 24 manufacturers with deep-dive Thermotec/Fletcher-quality documentation

=== IMPLEMENTATION STRATEGY ===

PHASE 1: Information Collection (per manufacturer)
  1. Obtain current manufacturer TDS and SDS
  2. Identify all product grades/variants from source data
  3. Extract performance ratings (R, Rw, NRC, certifications)
  4. Map application boundaries from marketing/technical docs
  5. Document installation requirements
  6. Identify cross-family references
  7. Compile owner-site literature references

PHASE 2: Content Generation (per family)
  1. Populate front matter with all required YAML fields
  2. Write canonical description (1-2 technical paragraphs)
  3. Create manufacturer-supported facts table
  4. Build grade/variant reconciliation with performance
  5. Define application boundaries precisely
  6. Document cross-family relationships
  7. Write installation context (no project specifics)
  8. Assign priority scores with confidence levels
  9. Define mandatory human-review gates
  10. Script natural Aircall enquiry flow
  11. Write approved customer-facing language
  12. List preferred vs. avoided terminology
  13. Document source hierarchy (3 tiers)
  14. Generate JSON machine-readable record
  15. Create performance evidence table

PHASE 3: Validation & Gating
  1. Run quality checklist against each file
  2. Verify no claims beyond scope
  3. Check evidence hierarchy is documented
  4. Validate all URLs are working
  5. Confirm JSON syntax is correct
  6. Review human gates are appropriate
  7. Approve language for sales use

=== PRIORITIZATION ===

Priority 1 (Start immediately - 9 manufacturers, 27 families):
  - Autex (3 families, 324 products) - Largest
  - Bradford (4 families, 154 products)
  - Kingspan (1 family, 93 products)
  - Rockwool (1 family, 71 products)
  - Proctor (7 families, 61 products)
  - Trade Select (2 families, 59 products)
  - Ecowool (4 families, 58 products)
  - Higgins Insulation (4 families, 56 products)
  - Knauf (1 family, 53 products)

Priority 2 (Secondary focus - 7 manufacturers, 14 families):
  - Foilboard, Sonata, Polyester Solutions, Acoustica, Aircell, Metecno, Misc

Priority 3 (Complete for coverage - 8 manufacturers, 11 families):
  - Smaller manufacturers: DCTech, Stinger, Paroc, Ametalin, James Hardie, Hushtec, Polyair, Martini

=== AUTOMATION APPROACH ===

For each manufacturer:
  1. Extract metadata from families.json
  2. Query product data from master SKU catalogue
  3. Use template to generate documentation structure
  4. Auto-populate TDS/SDS URLs (with manual verification)
  5. Insert grade/performance tables from source data
  6. Generate JSON machine-readable record
  7. Flag items requiring TDS/evidence extraction
  8. Prepare for manual content completion

Result: ~80% automation, 20% manual technical deep-dive per manufacturer
""")
