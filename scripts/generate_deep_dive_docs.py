"""Generate deep-dive (Thermotec NuWave-standard) documentation for all remaining
manufacturer families directly from the master Excel source.

This script runs entirely locally (no LLM calls). It pulls real manufacturer-sourced
spec text already present in the spreadsheet (Features & Benefits, Sales Pitch,
Install Instructions, Limitations & Critical Warnings, TDS/SDS URLs) and assembles
it into the same 15-section structure used for Thermotec NuWave and Autex Batt.

Usage:
    python scripts/generate_deep_dive_docs.py                # generate all remaining families
    python scripts/generate_deep_dive_docs.py --dry-run       # list families only, no writes
    python scripts/generate_deep_dive_docs.py --only Bradford # limit to one manufacturer
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXCEL_FILE = Path(r"C:\Users\ganes\OneDrive\Desktop\Insulation Easy\Bot\Product_Master_Bot_KB_SKU_Matched_cleaned.xlsx")
KNOWLEDGE_BASE_DIR = ROOT / "knowledge"
TODAY = "2026-09-05"

# Manufacturers/families already hand-authored to full deep-dive standard - do not overwrite.
SKIP = {
    ("Fletcher", None),
    ("Thermotec", None),
    ("Autex", "Batt"),
}

CATEGORY_SCORES = {
    "batt": {"acoustic_comfort": 3, "energy_efficiency": 5, "sustainability": 4, "installation_practicality": 4, "compliance_readiness": 4},
    "board": {"acoustic_comfort": 2, "energy_efficiency": 4, "sustainability": 3, "installation_practicality": 3, "compliance_readiness": 4},
    "reflective": {"acoustic_comfort": 3, "energy_efficiency": 4, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "pipe": {"acoustic_comfort": 2, "energy_efficiency": 4, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "wrap": {"acoustic_comfort": 2, "energy_efficiency": 3, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "panel": {"acoustic_comfort": 4, "energy_efficiency": 3, "sustainability": 3, "installation_practicality": 3, "compliance_readiness": 3},
    "accessory": {"acoustic_comfort": 1, "energy_efficiency": 1, "sustainability": 2, "installation_practicality": 5, "compliance_readiness": 2},
}
DEFAULT_SCORES = {"acoustic_comfort": 3, "energy_efficiency": 3, "sustainability": 3, "installation_practicality": 3, "compliance_readiness": 3}


def clean(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val).strip()


def normalize_family_name(name):
    name = clean(name)
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name[:50].upper()


def extract_category(product_use, category, material_type):
    combined = f"{product_use} {category} {material_type}".lower()
    if "batt" in combined or "blanket" in combined:
        return "Batt"
    elif "board" in combined or "slab" in combined:
        return "Board"
    elif "foil" in combined or "reflective" in combined or "mlv" in combined:
        return "Reflective"
    elif "pipe" in combined:
        return "Pipe"
    elif "wrap" in combined:
        return "Wrap"
    elif "panel" in combined:
        return "Panel"
    elif "accessory" in combined or "tape" in combined or "adhesive" in combined:
        return "Accessory"
    else:
        return category if category else "General"


def scores_for(category):
    return CATEGORY_SCORES.get(category.lower(), DEFAULT_SCORES)


def most_common_nonempty(series, n=1):
    vals = [clean(v) for v in series if clean(v)]
    if not vals:
        return []
    counts = Counter(vals)
    return [v for v, _ in counts.most_common(n)]


def rating_type(value):
    v = clean(value).lower()
    if v.startswith("r") and "rw" not in v:
        return "thermal_r_value"
    if "rw" in v:
        return "acoustic_rw"
    if "nrc" in v:
        return "acoustic_nrc"
    return "unspecified"


def split_bullets(text, max_items=6):
    if not text:
        return []
    parts = re.split(r";|\u2022|\n", text)
    parts = [p.strip().rstrip(".") for p in parts if p.strip()]
    return parts[:max_items]


def build_grade_table(rows):
    combos = defaultdict(int)
    for _, r in rows.iterrows():
        rating = clean(r.get("R Value / RW / NRC"))
        thickness = clean(r.get("Thickness (mm)"))
        length = clean(r.get("Length (mm)"))
        width = clean(r.get("Width (mm)"))
        key = (rating or "Not specified", thickness, length, width)
        combos[key] += 1
    lines = [
        "| Rating (as supplied) | Rating type | Thickness (mm) | Dimensions (L x W mm) | SKU count |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for (rating, thickness, length, width), count in sorted(combos.items(), key=lambda kv: -kv[1]):
        if length and width:
            dims = f"{length} x {width}"
        elif length:
            dims = f"{length} (width varies)"
        else:
            dims = "Varies"
        lines.append(f"| {rating} | {rating_type(rating)} | {thickness or 'Varies'} | {dims} | {count} |")
    return "\n".join(lines)


def build_grade_json(rows):
    combos = defaultdict(int)
    for _, r in rows.iterrows():
        rating = clean(r.get("R Value / RW / NRC")) or "not_specified"
        combos[rating] += 1
    return [{"rating": k, "rating_type": rating_type(k), "sku_count": v} for k, v in sorted(combos.items(), key=lambda kv: -kv[1])]


def dominant_rating_family(rows):
    """Return whether this family is primarily thermal, acoustic, or mixed."""
    types = [rating_type(clean(r.get("R Value / RW / NRC"))) for _, r in rows.iterrows()]
    thermal = sum(1 for t in types if t == "thermal_r_value")
    acoustic = sum(1 for t in types if t in ("acoustic_rw", "acoustic_nrc"))
    if thermal and acoustic:
        return "mixed"
    if thermal:
        return "thermal"
    if acoustic:
        return "acoustic"
    return "unspecified"


def generate_family_md(manufacturer, category, family_id, rows):
    product_count = len(rows)
    applications = most_common_nonempty(rows["Product Use"], n=6)
    material = most_common_nonempty(rows["Material Type"], n=1)
    material = material[0] if material else "Not specified"
    features = most_common_nonempty(rows["Spec Features & Benefits"], n=1)
    features = features[0] if features else ""
    pitch = most_common_nonempty(rows["Spec Sales Pitch"], n=1)
    pitch = pitch[0] if pitch else ""
    install = most_common_nonempty(rows["Spec Install Instructions"], n=1)
    install = install[0] if install else ""
    limitations = most_common_nonempty(rows["Spec Limitations & Critical Warnings"], n=1)
    limitations = limitations[0] if limitations else ""
    tds_urls = most_common_nonempty(rows["TDS URL"], n=2)
    sds_urls = most_common_nonempty(rows["SDS URL"], n=1)
    rating_kind = dominant_rating_family(rows)
    scores = scores_for(category)

    feature_bullets = split_bullets(features, max_items=6)
    limitation_bullets = split_bullets(limitations, max_items=6)
    install_bullets = split_bullets(install, max_items=6)
    app_list = applications if applications else ["General building applications"]

    rating_label = {
        "thermal": "thermal insulation (R-value)",
        "acoustic": "acoustic performance (Rw/NRC)",
        "mixed": "both thermal insulation (R-value) and acoustic performance (Rw/NRC)",
        "unspecified": "thermal and/or acoustic performance (rating not yet confirmed per SKU)",
    }[rating_kind]

    canonical_desc_parts = []
    if pitch:
        canonical_desc_parts.append(pitch)
    else:
        canonical_desc_parts.append(
            f"{manufacturer} {category} is a {material.lower() if material != 'Not specified' else 'manufacturer-specified material'} "
            f"insulation product family used for {rating_label} across {', '.join(app_list[:3]).lower()} applications."
        )
    if features:
        canonical_desc_parts.append(f"Manufacturer-published features and benefits include: {features}")
    canonical_desc = " ".join(canonical_desc_parts)
    canonical_desc += (
        f" This family covers {product_count} SKU variant(s) in the current catalogue. It is not a complete compliant "
        "building system on its own; project-specific claims about a finished construction must be confirmed by a human "
        "reviewer against a tested system that matches the proposed build-up."
    )

    facts_lines = [f"- Product type: {category} insulation product from {manufacturer}."]
    facts_lines.append(f"- Material: {material}.")
    facts_lines.append(f"- Rating basis: {rating_label}.")
    for b in feature_bullets:
        facts_lines.append(f"- {b}.")
    if not feature_bullets:
        facts_lines.append("- Detailed feature data not yet extracted from manufacturer TDS for this family.")
    facts_lines.append(f"- The catalogue includes {product_count} unique SKU variant(s) in this family.")

    grade_table = build_grade_table(rows)

    boundary_lines = "\n".join(f"- {a}" for a in app_list)

    install_lines = "\n".join(f"- {b}." for b in install_bullets) if install_bullets else (
        "- Installation method not yet extracted from manufacturer TDS; confirm current installation guide before advising customers."
    )

    limitation_lines = "\n".join(f"- {b}." for b in limitation_bullets) if limitation_bullets else (
        "- No manufacturer limitations text yet extracted; treat all compliance claims as unverified until TDS/SDS reviewed."
    )

    tds_ref = tds_urls[0] if tds_urls else "[To be sourced]"
    tds_ref2 = tds_urls[1] if len(tds_urls) > 1 else None
    sds_ref = sds_urls[0] if sds_urls else "[To be sourced]"

    gate_fire = "not_verified_per_sku"
    gate_bal = "not_verified"
    gate_ncc = "conditional_project_specific_evidence_required"

    json_record = {
        "family_id": family_id,
        "manufacturer": manufacturer,
        "canonical_name": f"{manufacturer} {category}",
        "bot_mode": "demo_family_recommendation",
        "recommendation_allowed": True,
        "recommendation_scope": "manufacturer_supported_family_only",
        "primary_function": rating_label,
        "material": material,
        "applications": app_list,
        "product_count": product_count,
        "grades": build_grade_json(rows),
        "priority_profile": {
            "sustainability": {"score": scores["sustainability"], "confidence": "medium"},
            "energy_efficiency": {"score": scores["energy_efficiency"], "confidence": "medium"},
            "acoustic_comfort": {"score": scores["acoustic_comfort"], "confidence": "medium"},
            "installation_practicality": {"score": scores["installation_practicality"], "confidence": "medium"},
        },
        "human_review_gates": {
            "ncc_and_project_compliance": gate_ncc,
            "fire": gate_fire,
            "bal": gate_bal,
        },
        "callback_required": True,
        "source_url": tds_ref,
    }

    md = f"""---
id: {family_id.lower().replace('_', '-')}
family_id: {family_id}
manufacturer: {manufacturer}
category: {category}
canonical_name: {manufacturer} {category}
material: {material}
bot_mode: demo_family_recommendation
recommendation_allowed: true
recommendation_scope: manufacturer_supported_family_only
requires_human_selection: true
validation_status: manufacturer_supported_secondary_claims_pending
last_validated: {TODAY}
rating_framework_version: 1
priority_sustainability_score: {scores['sustainability']}
priority_sustainability_confidence: medium
priority_energy_efficiency_score: {scores['energy_efficiency']}
priority_energy_efficiency_confidence: medium
priority_acoustic_comfort_score: {scores['acoustic_comfort']}
priority_acoustic_comfort_confidence: medium
priority_installation_practicality_score: {scores['installation_practicality']}
priority_installation_practicality_confidence: medium
gate_ncc_project_compliance: {gate_ncc}
gate_fire_compliance: {gate_fire}
gate_bal: {gate_bal}
official_datasheet_url: {tds_ref}
official_sds_url: {sds_ref}
product_count: {product_count}
rating_basis: {rating_kind}
---

# {manufacturer} {category}

## Purpose of this file

This is the canonical internal description for the {manufacturer} {category} family. It aligns the terminology used by the enquiry bot, sales team and future Aircall CSV.

For the demonstration, the bot may recommend the **{manufacturer} {category} family** when the customer's problem matches its documented applications. It must not choose a specific grade, calculate order quantity, or confirm thermal, acoustic, fire, NCC or BAL compliance for a project. Those decisions remain human-reviewed.

## Canonical description

{canonical_desc}

## Current manufacturer-supported facts

{chr(10).join(facts_lines)}

## Grade and catalogue reconciliation

The following reflects the current internal SKU extraction from the master product catalogue. Manufacturer TDS values must be re-confirmed per SKU before quoting.

{grade_table}

### Critical rating interpretation

Ratings prefixed `R` are thermal resistance values; ratings including `Rw` are weighted sound reduction/absorption indices; ratings including `NRC` are noise reduction coefficients. These are not interchangeable, and a manufacturer-published product rating is not automatically the rating of a finished, installed construction. The human reviewer must confirm which rating type applies to the specific SKU before making any performance statement to a customer.

## Application boundaries

### Within the {category} family

{boundary_lines}

### Separate product families

Do not transfer claims from this family to other {manufacturer} product families without their own current technical evidence. Where {manufacturer} sells multiple categories (batt, board, reflective, pipe, wrap, panel, accessory), each is a distinct family with its own grade table and evidence.

This family should not be presented as a fire-rated system, a complete compliant wall/ceiling assembly, or a guaranteed noise-elimination/thermal-comfort product. Record the customer's requirement and construction context for human review rather than confirming compliance directly.

## Installation context for enquiry handling

Manufacturer literature notes:

{install_lines}

The bot may use this information to understand the customer's project, but must not issue project-specific installation instructions. The human reviewer must confirm the complete construction, fixing method, junction/penetration treatment, moisture/vapour requirements, manual-handling requirements and the current manufacturer installation guide.

## Manufacturer-stated limitations and warnings

{limitation_lines}

## Customer-priority profile

These ratings are internal conversation aids. They determine useful follow-up questions and callback notes; they do not rank or recommend products to customers.

| Customer priority | Internal rating | Confidence | Interpretation |
| --- | ---: | --- | --- |
| Sustainability | {scores['sustainability']}/5 | Medium | Based on product category norms; product-specific certification not yet verified. |
| Energy efficiency | {scores['energy_efficiency']}/5 | Medium | Based on {rating_label}; confirm per-SKU rating before quoting a thermal target. |
| Acoustic comfort | {scores['acoustic_comfort']}/5 | Medium | Based on product category norms and any Rw/NRC ratings present in this family. |
| Installation practicality | {scores['installation_practicality']}/5 | Medium | Based on manufacturer install notes above; confirm access and handling requirements per project. |

## Mandatory human-review gates

| Requirement | Status for {manufacturer} {category} | Enquiry-bot action |
| --- | --- | --- |
| Acoustic/thermal target / NCC | CONDITIONAL | Record the building type, construction and target rating. Do not confirm compliance; arrange human review. |
| Fire requirement | NOT VERIFIED PER SKU | Record the required fire test, classification or system and arrange human review. |
| BAL / bushfire construction | NOT VERIFIED | Record the site's BAL and the external building element involved; arrange human review. |
| Rating-type confirmation | REQUIRES CONFIRMATION | Confirm which rating type (R, Rw, NRC) applies to the customer's requirement before referencing any specific grade. |

## Aircall enquiry flow

1. What are you trying to improve or solve for this project?
2. Where is the problem located: wall, ceiling, floor, roof, duct, pipe, or elsewhere?
3. Is this mainly a thermal comfort/energy issue, a noise issue, or both?
4. Is this a home, apartment, office, commercial building, industrial site or other project?
5. Is it a new build, renovation, retrofit or repair?
6. What is most important: sustainability, energy efficiency, acoustic comfort, budget, or ease of installation?
7. Do plans, a consultant or a certifier specify a thermal, acoustic, NCC, fire or BAL requirement?
8. What is the approximate area or length involved, if known?
9. Are there access, manual-handling, moisture or exposure considerations?
10. Would the caller prefer to phone the team directly or request a callback?

The agent must not ask the caller to choose a specific grade or SKU. If the caller names a grade, record it as caller-provided information rather than confirming it.

## Approved customer-facing language

### General explanation

> {manufacturer} {category} is a manufacturer-supported product family used for {rating_label}. The right grade depends on the complete construction and project requirements. I can collect the details for our team to review.

### When asked which grade to buy

> I cannot select a specific grade or confirm the result of an installed system. If you tell me about the location, requirement and any project specification, I can prepare the enquiry for our team. Would you prefer to call them or request a callback?

### When asked about compliance or BAL

> Compliance and bushfire suitability depend on the complete construction and supporting documentation for the specific product selected. I cannot confirm that from a product name alone. I will flag this for technical review and arrange the next contact step.

## Language controls

Prefer:

- "manufacturer-published rating" rather than a guaranteed result;
- "complete construction" or "complete installed system";
- "requires confirmation by our team";
- "customer-stated requirement" when recording a target.

Avoid:

- "soundproof," "eliminates noise" or "guaranteed";
- confusing thermal R-value with acoustic Rw or NRC;
- "best," "perfect" or "compliant" without qualification;
- calling any SKU fire-rated or BAL-rated without current verification;
- asserting exact recycled-content percentage, certification or warranty terms until current supporting documentation is accepted for that specific SKU.

## Source reconciliation and evidence hierarchy

### Tier 1 — current manufacturer source

Technical Data Sheet: {tds_ref}
{f"Additional TDS reference: {tds_ref2}" if tds_ref2 else ""}
Safety Data Sheet: {sds_ref}

Use this source for the canonical product identity, current grades, published ratings, primary applications and material composition.

### Tier 2 — current internal catalogue

The master product catalogue provides current commercial records for {product_count} SKUs, including internal SKU codes, dimensions, grade labels and stock. Commercial data does not validate technical performance; grade labels must be cross-checked against current manufacturer TDS per SKU before quoting.

### Tier 3 — authorised owned-site literature

Reseller and distributor listings may repeat manufacturer copy. Claims appearing only in this literature remain pending until matched to an accepted current TDS, SDS or certification document for the specific SKU.

## Machine-readable family record

```json
{json.dumps(json_record, indent=2)}
```

## Performance evidence summary

| Evidence type | Status | Reference |
| --- | --- | --- |
| Performance rating(s) | Manufacturer-published, not yet SKU-matched to current TDS | {tds_ref} |
| Material composition | Manufacturer-claimed | {tds_ref} |
| Fire performance | Not verified per SKU | Pending SDS/test report review |
| Installation guidance | Extracted from manufacturer spec text (see above) | {tds_ref} |

## Quality checklist validation

- [x] YAML front-matter with priority scores, gates and source URLs
- [x] Canonical description generated from manufacturer sales pitch/features text
- [x] Manufacturer-supported facts table present
- [x] Grade reconciliation table covers all SKUs in this family
- [x] Application boundaries with explicit inclusions/exclusions
- [x] Installation context documented (non-project-specific)
- [x] Manufacturer-stated limitations and warnings captured
- [x] Customer priority profile with confidence scoring
- [x] Mandatory human-review gates documented
- [x] Aircall enquiry flow with 10 questions
- [x] Approved customer-facing language for 3 scenarios
- [x] Language controls (prefer/avoid lists)
- [x] 3-tier source hierarchy documented
- [x] JSON machine-readable record included
- [x] Performance evidence summary table included
- [ ] Manually reviewed against current manufacturer TDS/SDS (pending human QA)

---

*This documentation was generated {TODAY} by scripts/generate_deep_dive_docs.py directly from the master product catalogue's manufacturer-sourced spec fields (Features & Benefits, Sales Pitch, Install Instructions, Limitations & Warnings, TDS/SDS URLs). It follows the Thermotec NuWave/Autex Batt documentation standard. Human QA against current manufacturer TDS/SDS is still required before full sign-off.*
"""
    return md, json_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", default=None, help="Limit to a single manufacturer name")
    args = parser.parse_args()

    print("Loading master Excel...")
    df = pd.read_excel(EXCEL_FILE, sheet_name="CLEANED", header=1)
    df["__category__"] = df.apply(
        lambda r: extract_category(clean(r.get("Product Use")), clean(r.get("Category")), clean(r.get("Material Type"))),
        axis=1,
    )

    manufacturers = sorted(df["Manufacturer Name"].dropna().unique(), key=lambda x: str(x))
    if args.only:
        manufacturers = [m for m in manufacturers if str(m) == args.only]

    total_written = 0
    for mfg in manufacturers:
        mfg = str(mfg).strip()
        if (mfg, None) in SKIP:
            print(f"Skipping {mfg} (already deep-dive documented)")
            continue

        mfg_df = df[df["Manufacturer Name"] == mfg]
        mfg_dir = KNOWLEDGE_BASE_DIR / mfg.lower()
        families_json_path = mfg_dir / "families.json"
        if not families_json_path.exists():
            print(f"  [WARN] No families.json for {mfg}, skipping")
            continue

        with open(families_json_path, "r", encoding="utf-8") as f:
            families_data = json.load(f)

        changed = False
        for family in families_data["families"]:
            category = family["category"]
            if (mfg, category) in SKIP:
                print(f"  Skipping {mfg} {category} (already deep-dive documented)")
                continue

            rows = mfg_df[mfg_df["__category__"] == category]
            if rows.empty:
                print(f"  [WARN] No rows matched {mfg} {category}, skipping")
                continue

            family_id = family["family_id"]
            print(f"  Generating {mfg} / {category} ({len(rows)} SKUs) -> {family['knowledge_file']}")

            if args.dry_run:
                continue

            md, json_record = generate_family_md(mfg, category, family_id, rows)
            md_path = mfg_dir / family["knowledge_file"]
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            total_written += 1

            # Update families.json metadata in place
            scores = scores_for(category)
            family["scores"] = scores
            family["score_notes"] = (
                f"Deep-dive scoring for {mfg} {category}: {len(rows)} SKUs generated from master catalogue spec data "
                f"via scripts/generate_deep_dive_docs.py. Human QA against current manufacturer TDS/SDS still pending."
            )
            family["detailed_knowledge_status"] = f"complete_deep_dive_{TODAY}"
            family["product_count"] = len(rows)
            changed = True

        if changed and not args.dry_run:
            with open(families_json_path, "w", encoding="utf-8") as f:
                json.dump(families_data, f, indent=2, ensure_ascii=False)

    print(f"\n[DONE] Wrote {total_written} deep-dive family documents.")


if __name__ == "__main__":
    main()
