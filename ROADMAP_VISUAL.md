# Documentation Enhancement Roadmap - Visual Summary

## Current vs. Target State

### NOW (2026-09-05)
```
26 MANUFACTURERS
├── Fletcher (134 products) ✅ COMPLETE
│   └── 18 families with deep-dive documentation
│       - Thermotec NuWave quality standard MET
│       - All gates, flows, language complete
│       - Ready for bot and sales use
│
├── Thermotec (280 products) ✅ COMPLETE
│   └── 13 families with deep-dive documentation
│       - Benchmark documentation quality
│       - All required sections complete
│       - Sources verified and documented
│
└── 24 OTHER MANUFACTURERS (1,945 products) ⚠️ INITIAL TEMPLATES ONLY
    ├── Autex (324 products, 3 families)          [NEEDS ELEVATION]
    ├── Bradford (154 products, 4 families)       [NEEDS ELEVATION]
    ├── Kingspan (93 products, 1 family)          [NEEDS ELEVATION]
    ├── Rockwool (71 products, 1 family)          [NEEDS ELEVATION]
    ├── Proctor (61 products, 7 families)         [NEEDS ELEVATION]
    ├── Trade Select (59 products, 2 families)    [NEEDS ELEVATION]
    ├── Ecowool (58 products, 4 families)         [NEEDS ELEVATION]
    ├── Higgins Insulation (56 products, 4 fam.)  [NEEDS ELEVATION]
    ├── Knauf (53 products, 1 family)             [NEEDS ELEVATION]
    └── 15 more manufacturers (467 products)      [NEEDS ELEVATION]

COVERAGE:
✅ Documentation structure: 100% (26/26 manufacturers)
⚠️  Thermotec/Fletcher quality: 6% (2/26 manufacturers)
🚧  Phase 3 ready: 0% (0/24 new manufacturers)
```

### TARGET (2026-12-31)
```
26 MANUFACTURERS - ALL AT THERMOTEC/FLETCHER QUALITY
├── Deep-Dive Complete (26/26) ✅
│   ├── 83 families total
│   ├── 2,359 products
│   ├── All with complete documentation
│   ├── All with mandatory human-review gates
│   ├── All with Aircall enquiry flows
│   └── All with approved customer language
│
├── Evidence Integration (26/26) ✅
│   ├── performance_evidence.json populated
│   ├── Source hierarchy documented
│   ├── Evidence gaps explicitly flagged
│   └── TDS/SDS links verified
│
├── Bot Ready (26/26) ✅
│   ├── JSON machine-readable records complete
│   ├── Aircall flows scripted
│   ├── Language controls in place
│   └── Human gates enforced
│
└── Sales Ready (26/26) ✅
    ├── Approved terminology documented
    ├── Response templates for all scenarios
    ├── Compliance gates clearly defined
    └── Alternative family references clear

COVERAGE:
✅ Documentation structure: 100% (26/26)
✅ Thermotec/Fletcher quality: 100% (26/26)
✅ Phase 3 complete: 100% (26/26)
```

---

## Quality Benchmark: What "Deep-Dive" Means

### Thermotec NuWave (The Standard We Match)

**Document Sections Required:**
```
1. YAML Front Matter         (25+ fields) ............................ 0.5 hours
2. Canonical Description     (200-300 words) ......................... 2.0 hours
3. Manufacturer Facts        (structured table) ...................... 1.0 hour
4. Grade Reconciliation      (all variants with performance) ......... 1.5 hours
5. Application Boundaries    (explicit inclusions/exclusions) ........ 1.0 hour
6. Installation Context      (non-project-specific overview) ......... 1.5 hours
7. Customer Priority Profile (5-point scores with justification) ..... 1.0 hour
8. Human-Review Gates        (compliance, fire, BAL, regional) ....... 1.5 hours
9. Aircall Enquiry Flow      (10+ natural questions) ................. 1.5 hours
10. Approved Customer Language (explanation, grade, compliance) ....... 1.0 hour
11. Language Controls         (prefer/avoid terminology) ............. 0.5 hours
12. Source Reconciliation     (3-tier hierarchy, gaps flagged) ....... 1.0 hour
13. JSON Machine Record       (bot-readable format) .................. 1.0 hour
14. Performance Evidence      (R, Rw, NRC, test standards) ........... 1.5 hours
15. Quality Checklist         (18-point validation) .................. 1.0 hour
                                                    TOTAL: 19-20 hours per family
```

**Key Quality Indicators:**
✅ No "[TBD]" or placeholder text
✅ All claims traceable to primary source
✅ All URLs verified working
✅ No conflation of R vs. Rw vs. NRC
✅ Compliance gates prevent false claims
✅ Bot knows when to hand off to humans
✅ Sales team has exact language to use
✅ Evidence quality level documented
✅ Confidence levels assigned
✅ Next steps for missing evidence identified

---

## Implementation Timeline

### Phase 1: Priority 1 Manufacturers (9 manufacturers, 27 families)
**Timeline: 4-6 weeks | Effort: 540 hours | Team: 2-3 people**

```
WEEK 1-2: Information Gathering
├── Obtain TDS for each manufacturer
├── Map all SKU variants
├── Extract performance ratings
├── Compile marketing materials
└── Identify cross-family references

WEEK 3-4: Template Population
├── Generate YAML front matter
├── Write canonical descriptions
├── Create grade tables
├── Define application boundaries
├── Develop priority profiles
└── Document installation context

WEEK 5-6: Validation & Gating
├── Define human-review gates
├── Script Aircall flows
├── Compile approved language
├── Generate JSON records
├── Quality checklist validation
└── Final review & corrections

TARGET MANUFACTURERS:
1. Autex (3 families, 324 products)          - Largest
2. Bradford (4 families, 154 products)       - Major
3. Kingspan (1 family, 93 products)
4. Rockwool (1 family, 71 products)
5. Proctor (7 families, 61 products)         - Most complex
6. Trade Select (2 families, 59 products)
7. Ecowool (4 families, 58 products)
8. Higgins Insulation (4 families, 56 products)
9. Knauf (1 family, 53 products)
```

### Phase 2: Priority 2 Manufacturers (7 manufacturers, 14 families)
**Timeline: 2-3 weeks | Effort: 280 hours | Team: 1-2 people**

Foilboard, Sonata, Polyester Solutions, Acoustica, Aircell, Metecno, Misc

### Phase 3: Priority 3 Manufacturers (8 manufacturers, 11 families)
**Timeline: 1-2 weeks | Effort: 220 hours | Team: 1 person**

Smaller manufacturers, lighter documentation load

**TOTAL PROJECT: 8-12 weeks | 1,040+ hours | 2-3 FTE equivalent**

---

## What Gets Done Each Week (Phase 1 Example)

### Week 1: Bradford Batt Documentation
```
MON-TUE: Information Gathering
  ├── Download Bradford batt TDS
  ├── Extract all grades, R-values, dimensions
  ├── Research material composition
  ├── Identify certifications (fire, non-combustible, CodeMark)
  ├── Compile reseller and owner-site references
  └── Cross-check master SKU catalogue

WED: Template Population
  ├── Write YAML front matter (30 min)
  ├── Canonical description (2 hours)
  ├── Grade reconciliation table (1 hour)
  ├── Application boundaries (1 hour)
  └── Installation context (1 hour)

THU: Gating & Flows
  ├── Customer priority profile (1.5 hours)
  ├── Human-review gates (1.5 hours)
  ├── Aircall enquiry flow (2 hours)
  └── Approved language (1.5 hours)

FRI: Validation
  ├── JSON machine record (1 hour)
  ├── Performance evidence table (1 hour)
  ├── Quality checklist review (1 hour)
  ├── Corrections and refinements (1 hour)
  └── Final sign-off

DELIVERABLE: 1 complete family (Bradford Batt) ready for production use
```

---

## Success Criteria (per Manufacturer)

### Documentation Complete ✅
- [ ] All 18 sections of template populated
- [ ] No placeholder text remaining
- [ ] Word counts met (canonical 200-300 words)
- [ ] All tables properly formatted

### Quality Validated ✅
- [ ] 18-point quality checklist: 100%
- [ ] No conflated metrics (R vs. Rw vs. NRC)
- [ ] All URLs verified working
- [ ] JSON syntax valid
- [ ] Evidence gaps explicitly flagged

### Bot Ready ✅
- [ ] Aircall flow is natural progression
- [ ] No grade/SKU selection by bot
- [ ] All compliance gates defined
- [ ] Fallback to human for unknowns

### Sales Ready ✅
- [ ] Approved language for all scenarios
- [ ] Response templates provided
- [ ] Alternative families cross-referenced
- [ ] No false compliance claims

### Evidence Ready ✅
- [ ] TDS/SDS links working
- [ ] Performance claims sourced
- [ ] Test standards documented
- [ ] Pending evidence listed

---

## Resources Needed

### Technical Resources
- [ ] Access to all manufacturer TDS/SDS documents
- [ ] Product specification databases
- [ ] Installation guides and technical bulletins
- [ ] Test reports and certifications

### Personnel
- [ ] Product specialist per manufacturer (0.5-1 FTE)
- [ ] Technical writer (2-3 FTE)
- [ ] QA/validation reviewer (1 FTE)
- [ ] Project manager (0.5 FTE)

### Tools
- [ ] Template files (provided: IMPLEMENTATION_GUIDE.md)
- [ ] Quality checklist (provided: documentation_template_framework.py)
- [ ] JSON validator
- [ ] Markdown linter
- [ ] URL checker

---

## Deliverables Summary

### Per Manufacturer (26 folders)
```
knowledge/{manufacturer}/
├── families.json (enhanced, all fields complete)
├── README.md (updated family index)
├── {family_1}.md (complete deep-dive, 25+ sections)
├── {family_2}.md (complete deep-dive)
├── ... (one per family)
├── _sources.json (evidence tracking, gaps)
└── _quality_report.md (checklist results)
```

### Cross-Cutting Updates
```
├── performance_evidence.json (all families)
├── EVIDENCE_MATRIX.md (family → evidence mapping)
├── LANGUAGE_GUIDE.md (approved terminology)
├── QUALITY_REPORT.md (aggregate validation results)
└── PHASE_3_COMPLETE.md (sign-off documentation)
```

---

## ROI & Business Impact

### Immediate (Bot Use)
- Bot has clear boundaries for all 52 families
- Prevents false compliance claims
- Knows when to hand off to humans
- Can script enquiry flows for Aircall

### Short Term (Sales)
- Sales team has approved language
- Consistent messaging across 26 manufacturers
- Clear alternative product references
- Response templates for common questions

### Medium Term (Expansion)
- New manufacturers can follow same template
- Evidence collection process standardized
- Quality bar established for all products
- Bot logic extensible to new families

### Long Term (Competitive)
- Only documentation standard covering 26 manufacturers + 2,359 products
- Defensible against regulatory challenge
- Evidence-based recommendations
- Clear compliance boundaries documented

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| TDS unavailable for some | Missing perf. data | Use Tier 2/3, flag pending |
| Timeline slippage | Delayed completion | Phase 3 can be lighter if needed |
| Language translation issues | Unclear guidance | Manual review by native speakers |
| Scope creep | Project overrun | Prioritize, Phase 3 optional initially |
| Team bandwidth | Incomplete work | Automate template, focus manual effort |

---

## Quick Reference: Thermotec NuWave vs. Initial Autex Batt

### NOW (Initial Template)
```markdown
---
family_id: AUTEX_BATT
manufacturer: Autex
name: Autex Batt
category: Batt
---

# Autex Batt

Autex Batt is a thermal insulation product.

[Empty sections, no technical detail]
```
**Lines: ~20 | Sections: 3 | Detail Level: Minimal**

### AFTER (Deep-Dive)
```markdown
---
family_id: AUTEX_BATT_THERMAL
manufacturer: Autex Limited
canonical_name: Autex Polyester Batt Thermal Insulation
category: Polyester fiber batt
material: 100% recycled polyester fiber
[25 YAML fields total]
---

# Autex Polyester Batt Insulation

## Purpose of this file
[Canonical description - 250 words with application context]

## Canonical description
[Detailed explanation of product, materials, applications]

## Manufacturer-supported facts
[Table with product types, grades, ratings, certifications]

## Grade and catalogue reconciliation
[Complete table of all SKU variants, R-values, dimensions]

## Application boundaries
[Explicit inclusions, exclusions, cross-family references]

## Installation context
[Overview, what human must verify, failure modes]

## Customer-priority profile
[5-point scores with confidence levels and justification]

## Mandatory human-review gates
[Compliance, fire, BAL, regional gates]

## Aircall enquiry flow
[10+ natural questions for voice agent]

## Approved customer-facing language
[Templates for all scenarios]

## Language controls
[Prefer/Avoid terminology lists]

## Source reconciliation
[3-tier hierarchy with evidence gaps]

## Machine-readable family record
[Complete JSON for bot logic]

## Performance Evidence Summary
[R, NRC, fire, test standards, confidence]
```
**Lines: 500+ | Sections: 15+ | Detail Level: Production-Ready**

---

## Next Steps

1. ✅ **Review this roadmap** - Alignment on scope and timeline
2. ✅ **Assign Phase 1 ownership** - One lead per manufacturer
3. ⏳ **Start with Autex** - Largest, most revenue potential
4. ⏳ **Establish review cadence** - Weekly validation
5. ⏳ **Coordinate TDS collection** - May require manufacturer outreach
6. ⏳ **Integrate with bot logic** - JSON records ready for Aircall
7. ⏳ **Plan sales training** - Approved language rollout

**Recommendation:** Begin Phase 1 immediately to achieve 100% documentation quality within 8-12 weeks.
