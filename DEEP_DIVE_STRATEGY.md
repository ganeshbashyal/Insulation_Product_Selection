# Deep-Dive Documentation Enhancement Strategy

## Executive Summary

**Goal:** Elevate documentation for all 24+ new manufacturers to Thermotec/Fletcher quality level

**Current State:**
- 2 manufacturers with complete deep-dive: Fletcher (18 families), Thermotec (13 families)
- 24 manufacturers with initial template structure: 52 families, 1,945 products

**Target State:**
- All 26 manufacturers with comprehensive technical documentation
- Each family documented to the Thermotec NuWave quality benchmark
- All performance claims traceable to manufacturer sources
- Clear bot-friendly guidance with mandatory human-review gates

**Effort:** 480+ hours of technical research and documentation (~20 hours per manufacturer average)

---

## Quality Benchmark: Thermotec NuWave Documentation

The Thermotec NuWave Mass Loaded Vinyl documentation exemplifies the required depth:

### 1. Front Matter (25+ YAML fields)
- Family ID, manufacturer, canonical name
- Product category, material, primary function
- Noise type and bot mode
- Recommendation scope and requirements
- Validation status and dates
- Priority scores (sustainability, energy, acoustic) with confidence levels
- Compliance gates (NCC, fire, BAL, weather)
- Official URLs (product, TDS, installation guide)

### 2. Canonical Description (200-300 words)
- Clear purpose statement
- What this product IS (with specific technical claims)
- What this product IS NOT (clear boundaries)
- System context (must be part of complete system, not standalone)

### 3. Manufacturer-Supported Facts (structured list)
- Product type and primary function
- Available grades/variants with specific identifiers
- Performance ratings with test standards
- Material composition as manufacturer describes it
- Applications and manufacturing location
- Certifications and compliance status

### 4. Grade Reconciliation Table
- All SKU variants with performance specs
- Dimensions, coverage, mass/weight
- Cross-reference to source data rows
- Data quality notes and issues to resolve

### 5. Application Boundaries
- **Explicit:** What this family is designed for
- **Explicit:** What this family is NOT designed for
- **Explicit:** Related products in different families
- **Explicit:** How to refer customers to alternatives

### 6. Installation Context (not project-specific)
- Overview of typical installation approach
- What human reviewer must confirm (but NOT specific to one project)
- Conditions that affect performance
- Potential failure modes to watch for

### 7. Customer Priority Profile
- 5-point rating across 3-5 dimensions
- Confidence level for each rating (High/Medium/Low)
- Plain-English interpretation of score
- Explicit exclusions (what this is NOT good for)

### 8. Mandatory Human-Review Gates
- Compliance requirements (NCC, fire, BAL, etc.)
- What the bot CAN'T decide
- What must be flagged for human review
- When to suggest alternative families or decline recommendation

### 9. Aircall Enquiry Flow
- 10+ natural-language conversation questions
- Progressive information gathering (not interrogation)
- How to handle caller naming a product/grade
- When to hand off to human team

### 10. Approved Customer-Facing Language
- General explanation (natural English, no jargon)
- Grade/product selection response
- Compliance and requirement response
- Preferred terminology list (do use these words)
- Avoid terminology list (don't use these phrases)

### 11. Source Reconciliation
- **Tier 1:** Current manufacturer official source (TDS, product page)
- **Tier 2:** Internal catalogue data (Google Sheet) with quality notes
- **Tier 3:** Owned-site reseller literature (useful but secondary)
- Evidence gaps and pending claims explicitly listed

### 12. Machine-Readable JSON Record
- Parseable structure for bot logic
- Grade details with performance
- Application list
- Required inputs and failure modes
- Human review gates in machine format

### 13. Performance Evidence Summary Table
- All metrics (R, Rw, NRC, fire rating, etc.) with test standard
- Confidence level for each measurement
- Comparison to alternatives
- System vs. component distinctions

---

## Implementation Roadmap

### Phase 1: Priority 1 Manufacturers (9 manufacturers, 27 families)

**Timeline:** 4-6 weeks
**Focus:** Major manufacturers with largest product counts

#### Week 1-2: Information Gathering
- [ ] Obtain current TDS for each Autex family (3 families)
- [ ] Obtain current TDS for each Bradford family (4 families)
- [ ] Map all SKU variants in master catalogue
- [ ] Extract performance ratings from TDS
- [ ] Compile manufacturer marketing materials
- [ ] Identify cross-family references

#### Week 3-4: Template Population
- [ ] Generate front matter YAML for all 27 families
- [ ] Write canonical descriptions
- [ ] Create grade reconciliation tables
- [ ] Define application boundaries
- [ ] Document installation context
- [ ] Develop customer priority profiles

#### Week 5-6: Validation & Gating
- [ ] Define mandatory human-review gates
- [ ] Script Aircall enquiry flows
- [ ] Compile approved language
- [ ] Document source hierarchy
- [ ] Generate JSON records
- [ ] Quality review against checklist

### Phase 2: Priority 2 Manufacturers (7 manufacturers, 14 families)

**Timeline:** 2-3 weeks
**Focus:** Mid-sized manufacturers

### Phase 3: Priority 3 Manufacturers (8 manufacturers, 11 families)

**Timeline:** 1-2 weeks  
**Focus:** Smaller manufacturers (may have less available documentation)

---

## Detailed Template Structure

See `documentation_template_framework.py` for:
1. Complete template with all required sections
2. Quality checklist (18-point verification)
3. Evidence collection checklist
4. Audience readiness criteria

---

## Data Integration Points

### From Master SKU Catalogue
```
family_id → product_name → material_type → category → performance specs
```

### From families.json (auto-generated currently)
```
family_id, manufacturer, name, category, applications, keywords
```

### From TDS/Source Documents
```
grades, performance ratings, certifications, material composition, applications
```

### Into performance_evidence.json
```
family_id → evidence_items[] → {
  metric (R, Rw, NRC, fire_rating),
  value, unit, variant, scope, test_standard, confidence_level, source
}
```

---

## Validation Workflow

### 1. Content Completeness Check
- All YAML front matter fields populated ✓
- No "[TBD]" or "placeholder" text ✓
- All URLs verified working ✓
- JSON syntax valid ✓

### 2. Scope Verification
- Product type clearly stated ✓
- Primary vs. secondary functions separated ✓
- Limitations and exclusions explicit ✓
- No system R claimed as component ✓
- No thermal R claimed for acoustic product ✓
- No compliance claimed beyond scope ✓

### 3. Evidence Quality
- All claims traceable to primary source ✓
- Pending evidence explicitly flagged ✓
- Confidence levels assigned ✓
- Test standards documented ✓
- Alternative interpretations noted ✓

### 4. Bot Readiness
- Aircall flow natural and conversational ✓
- Approved language provided for every scenario ✓
- Human gates clearly defined ✓
- No project-specific recommendations ✓
- Grade/SKU selection left to humans ✓

### 5. Team Readiness
- Sales team can use approved language ✓
- Human reviewers know compliance gates ✓
- Clear escalation paths defined ✓
- Alternative families documented ✓

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Documentation coverage | 100% of 52 new families | Count of complete files |
| Quality score | 85%+ on checklist | Automated validation |
| Evidence maturity | Tier 1 source for 80%+ | Source hierarchy audit |
| Bot readiness | All families with enquiry flow | Aircall script completeness |
| Team adoption | 90%+ usage of approved language | Sales/callback analysis |

---

## Resource Requirements

### Technical Resources
- [ ] Access to all manufacturer TDS/SDS documents
- [ ] Product specifications databases
- [ ] Performance test reports and certifications
- [ ] Installation guides and technical bulletins

### Personnel
- [ ] Product specialists per manufacturer (0.5-1 FTE per major mfg)
- [ ] Technical writer (2-3 FTE for template population)
- [ ] QA/validation reviewer (1 FTE)
- [ ] Bot/JSON specialist (0.5 FTE)

### Timeline
- Priority 1: 4-6 weeks
- Priority 2: 2-3 weeks
- Priority 3: 1-2 weeks
- **Total: 8-12 weeks for complete expansion**

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| TDS unavailable for some mfg | Missing performance data | Use reseller sites as Tier 2/3, flag as pending |
| Outdated/conflicting claims | Bot recommends incorrectly | Validation date required, cross-check 3+ sources |
| Language translation issues | Bot provides unclear guidance | Manual language review by native speakers |
| Scope creep on smaller mfg | Timeline extension | Prioritize by product count, Phase 3 can be lighter |
| Team bandwidth | Incomplete documentation | Automate template population, focus manual work on gaps |

---

## Deliverables

### Per Manufacturer Folder
1. `families.json` (enhanced from initial) with all fields complete
2. `README.md` (updated with full family index)
3. Per-family markdown file with complete documentation
4. `_sources.json` (new file tracking evidence sources and gaps)

### Cross-cutting Deliverables
1. `performance_evidence.json` (updated with all families)
2. `EVIDENCE_MATRIX.md` (matrix of family → evidence items)
3. `LANGUAGE_GUIDE.md` (approved terminology per manufacturer)
4. `QUALITY_REPORT.md` (validation checklist results)

---

## Next Steps

1. **Prioritize manufacturers** for Phase 1 based on:
   - Product count (higher = more revenue potential)
   - TDS availability (publicly accessible = faster)
   - Complexity (simpler products = faster documentation)

2. **Assign ownership** - select lead technical person per manufacturer

3. **Create working document** tracking progress on template population

4. **Establish review cadence** - weekly validation of completed families

5. **Coordinate with TDS collection** - may need to request from manufacturers

6. **Plan integration** with bot logic, Aircall, and sales tools

---

## Example: Autex Deep-Dive Structure

### Autex Batt Family Documentation Requirements

Current state: `autex/batt.md` with template

Required enhancements:
1. Obtain Autex batt TDS and specifications
2. Map all Autex batt SKUs to products in source data
3. Extract performance ratings (R-values, NRC, fire ratings)
4. Identify Autex batt sub-families (if any)
5. Define competition vs. Fletcher/Thermotec/Bradford
6. Write canonical description distinguishing Autex from others
7. Create grade reconciliation table with all variants
8. Define application boundaries
9. Document installation context
10. Assign priority scores
11. Create Aircall enquiry flow specific to thermal+acoustic
12. Generate approved customer language
13. Validate against quality checklist

**Estimated effort:** 16-20 hours per family
**Autex total:** 3 families × 18 hours = 54 hours
