"""Generate concise, sales- and SEO-oriented product literature for every family.

Runs entirely locally, no LLM calls. Mines the existing deep-dive markdown docs,
families.json, and the SKU catalogue, then produces for each family:
  - output/literature/<manufacturer>/<slug>.md    (customer-facing page)

The copy follows the structure of the Thermotec 4-Zero literature draft
(product description, key features, applications/selection checklist, range
table, technical data, compliance, installation, safety, sustainability,
warranty, spec clause, source register, review actions) while keeping the
repo's safety rules: only facts already present in the knowledge base are used,
and every document keeps the human-review gates and "draft pending TDS
confirmation" status.

Only regenerates files whose inputs changed (content hashing), so it is cheap
to run repeatedly in the background.

Usage:
    python scripts/generate_family_literature.py              # all families
    python scripts/generate_family_literature.py --only Autex # one manufacturer
    python scripts/generate_family_literature.py --dry-run    # report only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "output" / "literature"
SKU_CSV = ROOT / "data" / "processed" / "product_catalogue_skus.csv"
STATE_FILE = OUT_DIR / ".literature_state.json"
GENERATOR_VERSION = "4"  # bump when the template changes so all outputs regenerate

CATEGORY_TAGLINES = {
    "Batt": "bulk insulation batts for thermal and acoustic performance",
    "Board": "rigid insulation boards for continuous thermal performance",
    "Reflective": "reflective foil insulation for radiant heat control",
    "Wrap": "reflective membrane for weather protection and condensation control",
    "Pipe": "pre-formed pipe insulation for thermal efficiency and condensation control",
    "Panel": "acoustic panels for sound absorption and interior finish",
    "Accessory": "installation accessories and fixings",
}
INTENT_TERMS = {
    "thermal": "thermal insulation", "acoustic": "acoustic insulation",
    "wall": "wall insulation", "ceiling": "ceiling insulation",
    "roof": "roof insulation", "floor": "floor insulation",
    "underfloor": "underfloor insulation", "pipe": "pipe insulation",
    "duct": "duct insulation", "shed": "shed insulation",
}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def rating_summary(values: pd.Series) -> str:
    """Collapse noisy per-SKU rating text (e.g. 'Review: R1.2 | R2.5') to a
    compact, de-duplicated summary for a document cell."""
    found: list[str] = []
    for value in values.dropna().astype(str):
        for token in re.findall(r"R\d+(?:\.\d+)?", value):
            if token not in found:
                found.append(token)
    return ", ".join(found[:4]) if found else "Not stated"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return slug[:60]


def parse_front_matter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    data = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip()
    return data


def section(text: str, heading: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def extract_features(text: str) -> list[str]:
    match = re.search(r"features and benefits include:(.*?)(?:This family covers|\n\n|$)", text, re.S | re.I)
    if not match:
        return []
    raw = match.group(1).replace("\n", " ")
    parts = [clean(part).rstrip(".") for part in re.split(r";|\.\s+(?=[A-Z])", raw)]
    return [part for part in parts if len(part) > 8][:8]


def extract_description(text: str) -> str:
    body = section(text, "Canonical description")
    body = re.sub(r"Manufacturer-published features and benefits include:.*?(?=(?:This family covers|\n\n|$))", "", body, flags=re.S | re.I)
    body = re.sub(r"This family covers .*? SKU variant.*?\.", "", body)
    body = re.sub(r"It is not a complete compliant building system.*", "", body, flags=re.S)
    sentences = re.split(r"(?<=[.!?])\s+", clean(body))
    return " ".join(sentences[:3])


def extract_limitations(text: str) -> list[str]:
    body = section(text, "Manufacturer-stated limitations and warnings")
    bullets = re.findall(r"(?m)^- (.+)$", body)
    return [clean(b) for b in bullets if "No manufacturer limitations" not in b][:6]


def extract_grade_rows(text: str) -> list[dict]:
    body = section(text, "Grade and catalogue reconciliation")
    lines = [line for line in body.splitlines() if line.strip().startswith("|")]
    rows = []
    for line in lines:
        cells = [clean(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0] not in ("Rating (as supplied)", "---"):
            rows.append({"rating": cells[0], "rating_type": cells[1], "thickness": cells[2], "dimensions": cells[3], "sku_count": cells[4]})
    return rows


def seo_keywords(name: str, manufacturer: str, category: str, applications: list[str], ratings: set[str]) -> list[str]:
    keywords = [name, f"{manufacturer} {category.lower()}" if category else manufacturer]
    lowered = " ".join([name, *applications]).casefold()
    for term, phrase in INTENT_TERMS.items():
        if term in lowered:
            keywords.append(phrase)
    if "R" in " ".join(ratings):
        keywords.append("R-value insulation")
    keywords += ["insulation Australia", f"{manufacturer} Australia"]
    seen, ordered = set(), []
    for keyword in keywords:
        key = keyword.casefold()
        if key not in seen:
            seen.add(key)
            ordered.append(keyword)
    return ordered[:10]


def title_case_manufacturer(manufacturer_dir: str) -> str:
    return manufacturer_dir.title()


def load_research(manufacturer_dir: str, name: str) -> dict | None:
    """Return the researched spec JSON for a family if the TDS agent produced one."""
    path = ROOT / "knowledge" / manufacturer_dir / "research" / f"{slugify(name)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if data.get("status") == "ok" and data.get("spec") else None


def build_markdown(family: dict, fm: dict, text: str, skus: pd.DataFrame, research: dict | None = None) -> tuple[str, dict]:
    name = family["name"]
    manufacturer = family["manufacturer"]
    category = clean(family.get("category", "")).replace(" insulation", "").replace(" Insulation", "")
    spec = (research or {}).get("spec") or {}
    applications = spec.get("applications") or family.get("applications", [])
    description = clean(spec.get("description", "")) or extract_description(text)
    # helper: tolerate a spec field being None instead of a list/string
    def _list(key):
        value = spec.get(key)
        return value if isinstance(value, list) else []

    def _str(key):
        value = spec.get(key)
        return value if isinstance(value, str) else ""

    features = [clean(f) for f in _list("features") if clean(f)] or extract_features(text)
    technical = [t for t in _list("technical") if isinstance(t, dict) and t.get("property")]
    fire_text = clean(_str("fire"))
    sustainability_text = clean(_str("sustainability"))
    install_steps = [clean(s) for s in _list("install") if clean(s)]
    # richer deep-dive fields (Gemini agent)
    range_rows_data = [r for r in _list("range") if isinstance(r, dict)]
    selection_checklist = [clean(s) for s in _list("selection_checklist") if clean(s)]
    compliance_text = clean(_str("compliance"))
    accessories = [clean(a) for a in _list("accessories") if clean(a)]
    limitations = [clean(l) for l in _list("limitations") if clean(l)] or extract_limitations(text)
    warranty_text = clean(_str("warranty"))
    grade_rows = extract_grade_rows(text)
    material = fm.get("material") or (clean(skus["material_type"].iloc[0]) if not skus.empty else "")
    tds_url = family.get("source_url") or fm.get("official_datasheet_url", "")
    sds_url = fm.get("official_sds_url", "")
    ratings: set[str] = set()
    if not skus.empty:
        for column in ("thermal_r_value", "acoustic_rw", "nrc_aw"):
            for value in skus[column].dropna().astype(str):
                for token in re.findall(r"(?:R|Rw|NRC)\s?\d+(?:\.\d+)?", value):
                    ratings.add(token)
    rating_text = ", ".join(sorted(ratings)[:8]) if ratings else "Not yet extracted per SKU"
    seo_description = clean(description) or f"{name} is a {category.lower()} insulation product family from {manufacturer}. View the catalogue range, applications and specification starting point."
    keywords = seo_keywords(name, manufacturer, category, applications, ratings)
    tagline = CATEGORY_TAGLINES.get(category, f"{category.lower()} insulation product")

    feature_md = "\n".join(f"- {feature}." for feature in features) or "- Refer to the manufacturer datasheet for published features."
    apps_md = "\n".join(f"- {app}" for app in applications) or "- General building applications."
    limits_md = "\n".join(f"- {item}" for item in limitations) or "- No manufacturer limitations extracted yet; treat all claims as unverified until the TDS/SDS is reviewed."
    kw_md = ", ".join(keywords)

    range_rows = ""
    if range_rows_data:
        # support both Gemini's {variant,size_or_rating,pack} and the injected
        # granular size/pack tables ({c0,c1,...} with range_headers)
        headers = spec.get("range_headers")
        if headers and range_rows_data and "c0" in range_rows_data[0]:
            cols = headers
            range_rows = "| " + " | ".join(clean(h) for h in cols) + " |\n"
            range_rows += "|" + " --- |" * len(cols) + "\n"
            for row in range_rows_data:
                range_rows += "| " + " | ".join(clean(row.get(f"c{i}", "")) for i in range(len(cols))) + " |\n"
            range_rows += "\n_Manufacturer size/packaging breakdown._\n"
        else:
            range_rows = "| Variant | Size / rating | Pack |\n| --- | --- | --- |\n"
            for row in range_rows_data[:30]:
                range_rows += f"| {clean(row.get('variant'))} | {clean(row.get('size_or_rating'))} | {clean(row.get('pack'))} |\n"
            if skus.empty:
                range_rows += "\n_Variants from the manufacturer datasheet._\n"
    if skus.empty is False:
        if range_rows:
            range_rows += "\n**Internal catalogue range**\n\n"
        range_rows += "| SKU | Product | Published rating |\n| --- | --- | --- |\n"
        for _, sku in skus.head(25).iterrows():
            rating = rating_summary(pd.Series([sku["thermal_r_value"], sku["acoustic_rw"], sku["nrc_aw"]]))
            range_rows += f"| {clean(sku['our_sku'])} | {clean(sku['product_name'])} | {rating} |\n"
        if len(skus) > 25:
            range_rows += f"\n_{len(skus) - 25} further catalogue variants not listed here._\n"
    elif grade_rows and not range_rows:
        range_rows = "| Rating | Type | Thickness | Dimensions | SKUs |\n| --- | --- | --- | --- | --- |\n"
        for row in grade_rows:
            range_rows += f"| {row['rating']} | {row['rating_type']} | {row['thickness']} | {row['dimensions']} | {row['sku_count']} |\n"
    elif not range_rows:
        range_rows = "_Range not yet extracted; confirm variants against the current manufacturer TDS._\n"

    if technical:
        tech_rows = "| Property | Value | Standard |\n| --- | --- | --- |\n"
        for row in technical[:20]:
            tech_rows += f"| {clean(row.get('property'))} | {clean(row.get('value'))} | {clean(row.get('standard')) or '-'} |\n"
        tech_source = research.get("datasheet_pdf_url", tds_url)
    else:
        tech_rows = (
            "| Property | Value | Source |\n| --- | --- | --- |\n"
            f"| Product type | {category} | Manufacturer catalogue |\n"
            f"| Material | {material or 'Not specified'} | Manufacturer catalogue |\n"
            f"| Applications | {'; '.join(applications) or 'General building applications'} | Manufacturer catalogue |\n"
            f"| Published ratings | {rating_text} | Internal catalogue; confirm against current TDS |\n"
        )
        tech_source = tds_url

    install_md = "\n".join(f"{i}. {step}." for i, step in enumerate(install_steps, 1)) if install_steps else \
        "Use the current manufacturer instructions and the project specification. Handling, fixing and jointing details must be confirmed against the TDS for the selected SKU." + (f" Key limitation: {limitations[0]}" if limitations else "")

    fire_md = fire_text if fire_text else "Not verified per SKU. No fire, NCC or BAL classification is asserted in this draft."
    sustain_md = sustainability_text if sustainability_text else \
        "Sustainability and VOC statements are manufacturer-published claims and are not independently verified in this draft. Confirm any recycled-content or Green Star wording with the manufacturer before publication."
    compliance_md = compliance_text if compliance_text else ""
    warranty_md = warranty_text if warranty_text else "No product-specific warranty term is asserted in this draft. Refer to the manufacturer's general terms and confirm warranty wording before publication."
    accessories_md = "\n".join(f"- {a}." for a in accessories)
    checklist_md = "\n".join(f"{i}. {item}." for i, item in enumerate(selection_checklist, 1)) if selection_checklist else (
        "1. Confirm the application (wall, ceiling, floor, roof, pipe or service) matches the family.\n"
        "2. Confirm the target rating and construction build-up with the project team.\n"
        "3. Confirm available cavity or fixing depth against the product dimensions.\n"
        "4. Check NCC, fire, BAL or acoustic requirements with a qualified reviewer before specifying.\n"
        "5. Record the suburb/postcode so climate-zone requirements can be checked."
    )
    researched = bool(technical)

    meta = {
        "name": name, "manufacturer": manufacturer, "category": category,
        "tagline": tagline, "keywords": keywords, "description": description,
        "features": features, "limitations": limitations, "material": material,
        "tds_url": tds_url, "sds_url": sds_url, "applications": applications,
        "skus": skus, "grade_rows": grade_rows, "technical": technical,
        "fire_text": fire_text, "sustainability_text": sustainability_text,
        "install_steps": install_steps, "researched": researched,
        "datasheet_pdf_url": (research or {}).get("datasheet_pdf_url"),
        "range_rows_data": range_rows_data, "selection_checklist": selection_checklist,
        "compliance_text": compliance_text, "accessories": accessories,
        "warranty_text": warranty_text,
    }

    md = f"""---
title: "{name} - {category} Insulation | {manufacturer}"
description: "{seo_description[:150]}"
keywords: "{kw_md}"
status: "Draft - pending manufacturer TDS/SDS confirmation"
family_id: {family['family_id']}
---

# {name}

**{manufacturer} {category}** — {tagline}.

{description or f"{name} is a {category.lower()} product family from {manufacturer}. Confirm the current published specification against the manufacturer datasheet before quoting."}

## Key features

{feature_md}

## Applications and selection

{apps_md}

**Selection checklist**

{checklist_md}
{f"\n## Manufacturer range\n\n{range_rows}" if range_rows_data and not skus.empty else ""}

## Current catalogue range

{range_rows}
## Technical data

{tech_rows}
{f"Extracted from manufacturer datasheet: {tech_source}" if researched else ""}

## Fire, testing and compliance context

{fire_md}
{f"\n{compliance_md}\n" if compliance_md else ""}
- NCC / project compliance: conditional — project-specific evidence required.
- BAL: not verified.
- Datasheet: {tds_url or "to be sourced"} (link audited 2026-09-05; exact product TDS may still be pending).
- SDS: {sds_url or "to be sourced"}.
{f"\n## Recommended accessories\n\n{accessories_md}\n" if accessories_md else ""}
{f"\n## Limitations and warnings\n\n" + chr(10).join(f'- {l}.' for l in limitations) + chr(10) if limitations else ""}
## Installation overview

{install_md}

## Safety and handling

Confirm the current SDS before handling or cutting. No product-specific hazard classification is asserted here.

## Sustainability and indoor environment

{sustain_md}

## Warranty, returns and support

{warranty_md}

## Specification starting point

> Insulation shall be {name} ({category.lower()}) by {manufacturer}, selected to suit the confirmed application and required rating. Exact product, thickness and compliance to be confirmed by the project reviewer against the current manufacturer TDS before ordering.

## Source register

- SRC-01 Manufacturer datasheet: {tds_url or "to be sourced"}.
- SRC-02 Safety data sheet: {sds_url or "to be sourced"}.
- SRC-03 Internal SKU catalogue ({len(skus) if not skus.empty else len(grade_rows)} variant(s)).

## Review actions before publication

- Confirm the exact product TDS deep link and re-validate all technical values against it.
- Confirm SDS currency and handling guidance.
- Approve environmental and warranty wording with the manufacturer.
- Human review of NCC, fire, BAL and acoustic claims remains mandatory.

_Draft generated 2026-09-05 from the internal knowledge base. Technical values and claims remain subject to manufacturer review before publication._
"""
    return md, meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="limit to one manufacturer directory name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    skus = pd.read_csv(SKU_CSV).fillna("")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}

    written = skipped = 0
    for path in sorted(ROOT.glob("knowledge/*/families.json")):
        manufacturer_dir = path.parent.name
        if args.only and manufacturer_dir.casefold() != args.only.casefold():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out_dir = OUT_DIR / manufacturer_dir.replace(" ", "_")
        used_slugs: set[str] = set()
        for family in data["families"]:
            family.setdefault("manufacturer", title_case_manufacturer(manufacturer_dir))
            md_path = path.parent / family.get("knowledge_file", "")
            if not md_path.exists():
                continue
            text = md_path.read_text(encoding="utf-8")
            family_skus = skus[skus["family_id"] == family["family_id"]]
            research = load_research(manufacturer_dir, family["name"])
            fingerprint = hashlib.sha256((GENERATOR_VERSION + text + json.dumps(family, sort_keys=True) + str(len(family_skus)) + json.dumps(research or {}, sort_keys=True)).encode()).hexdigest()
            slug = slugify(family["name"])
            base_slug = slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug}_{suffix}"
                suffix += 1
            used_slugs.add(slug)
            state_key = f"{manufacturer_dir}/{slug}"
            if state.get(state_key) == fingerprint and (out_dir / f"{slug}.md").exists():
                skipped += 1
                continue
            if args.dry_run:
                print(f"would generate {state_key}")
                written += 1
                continue
            fm = parse_front_matter(text)
            md, meta = build_markdown(family, fm, text, family_skus, research=research)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{slug}.md").write_text(md, encoding="utf-8")
            state[state_key] = fingerprint
            written += 1

    print(f"\ngenerated: {written}, unchanged: {skipped}")
    if not args.dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
