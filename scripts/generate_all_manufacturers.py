"""Generate knowledge base documentation for all manufacturers from the Excel source."""

import json
import re
from pathlib import Path
from collections import defaultdict
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from family_scoring import classify_scores

# Load Excel data
EXCEL_FILE = Path(r"C:\Users\ganes\OneDrive\Desktop\Insulation Easy\Bot\Product_Master_Bot_KB_SKU_Matched_cleaned.xlsx")
KNOWLEDGE_BASE_DIR = ROOT / "knowledge"

# Scoring templates live in scripts/family_scoring.py (imported above). Scores are
# classification-aware (manufacturer-stated use), not based on physical form alone.

def get_scores_for_category(category_name, name="", applications=(), keywords=()):
    """Get scores for a family, driven by its classification signals."""
    return classify_scores(category_name, name=name, applications=applications, keywords=keywords)

def normalize_family_name(name):
    """Convert product name to family ID format."""
    if not name:
        return "UNKNOWN"
    # Remove special characters, replace spaces with underscores, uppercase
    name = str(name).strip()
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name[:50].upper()

def extract_category(product_use, category, material_type):
    """Extract product category from multiple columns."""
    if not product_use and not category:
        return "General"
    
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
    elif "panel" in combined or "panel" in combined:
        return "Panel"
    elif "accessory" in combined or "tape" in combined or "adhesive" in combined:
        return "Accessory"
    else:
        return category if category else "General"

def load_manufacturer_data():
    """Load and organize all manufacturer data from Excel."""
    df = pd.read_excel(EXCEL_FILE, sheet_name='CLEANED')
    
    manufacturers_data = defaultdict(lambda: defaultdict(list))
    
    for idx, row in df.iterrows():
        mfg = row.get('manufacturer_matching')
        if pd.isna(mfg) or mfg == 'Manufacturer Name':
            continue
            
        mfg_name = str(mfg).strip()
        
        # Extract product info
        product_name = row.get('core_identity', '')
        product_use = row.get('unnamed:_6', '')  # Based on earlier analysis
        category = row.get('unnamed:_4', '')
        material_type = row.get('unnamed:_5', '')
        
        product_category = extract_category(product_use, category, material_type)
        
        # Store the row with normalized category
        manufacturers_data[mfg_name][product_category].append({
            'name': product_name,
            'product_use': product_use,
            'category': category,
            'material_type': material_type,
            'row': row
        })
    
    return manufacturers_data

def create_family_json_for_manufacturer(manufacturer_name, products_by_category):
    """Create families.json for a manufacturer."""
    manufacturer_name = str(manufacturer_name).strip()
    families = []
    
    for idx, (category, products) in enumerate(sorted(products_by_category.items()), 1):
        # Create one family per category (groups similar products)
        family_id = f"{normalize_family_name(manufacturer_name)}_{normalize_family_name(category)}"
        
        # Get representative product name
        sample_product = products[0]['name'] if products else category
        sample_product = str(sample_product).strip() if sample_product else ""
        
        app_list = list(set([str(p['product_use']).strip() for p in products if p['product_use'] and pd.notna(p['product_use'])]))
        keyword_list = [category.lower(), manufacturer_name.lower(), sample_product.lower() if sample_product else category.lower()]
        family = {
            "family_id": family_id,
            "manufacturer": manufacturer_name,
            "name": f"{manufacturer_name} {category}",
            "category": category,
            "primary_function": f"{category} insulation product from {manufacturer_name}.",
            "applications": app_list,
            "keywords": keyword_list,
            "scores": get_scores_for_category(category, name=f"{manufacturer_name} {category}", applications=app_list, keywords=keyword_list),
            "score_notes": f"Initial categorization of {manufacturer_name} {category} products. Scores based on product category.",
            "confidence": "manufacturer_supported",
            "knowledge_file": f"{normalize_family_name(category).lower()}.md",
            "detailed_knowledge_status": "initial_2026-09-05",
            "source_url": f"https://www.{manufacturer_name.lower().replace(' ', '')}.com.au/",
            "questions": [
                "What is the primary application for this product?",
                "What performance requirements apply?",
                "What space or area constraints exist?"
            ],
            "human_gates": [
                "Verify manufacturer identity from primary source",
                "Confirm product specifications and performance claims",
                "Validate compliance with relevant standards"
            ],
            "product_count": len(products)
        }
        
        families.append(family)
    
    return {
        "schema_version": "2.0",
        "scope": f"{manufacturer_name} product families",
        "rating_scale": "1 = low relevance, 3 = useful, 5 = primary strength; ratings guide discovery and are not compliance or performance certificates",
        "families": families
    }

def create_product_family_md(family_id, manufacturer_name, category, product_count):
    """Create a product family markdown file."""
    content = f"""---
family_id: {family_id}
manufacturer: {manufacturer_name}
category: {category}
status: Initial documentation
date_created: 2026-09-05
---

# {manufacturer_name} {category}

{manufacturer_name} {category} product family documentation.

## Product Family

This family contains {product_count} product variants from {manufacturer_name} in the {category} category.

### Applications

- Thermal insulation
- Acoustic control
- Building envelope
- General building applications

### Key Product Attributes

- **Manufacturer**: {manufacturer_name}
- **Category**: {category}
- **Status**: Initial documentation

## Performance Claims

Performance data and thermal specifications are maintained in the centralized evidence registry.

## Limitations and Important Notices

- All product selection must be verified against current manufacturer technical data sheets
- Installation requirements must be confirmed for the specific application
- Compliance with NCC, BAL, and fire ratings must be validated independently

## Next Steps

1. Extract performance data from manufacturer TDS
2. Verify material composition and specifications
3. Validate acoustic and thermal ratings
4. Confirm availability and sourcing

## References

- Manufacturer website: {manufacturer_name}
- Technical Data Sheet: [To be sourced]
- Safety Data Sheet: [To be sourced]

---

*This documentation was initially generated on 2026-09-05 and requires detailed technical review and validation against primary manufacturer sources.*
"""
    return content

def main():
    """Generate knowledge base documentation for all manufacturers."""
    print("Loading manufacturer data from Excel...")
    manufacturers_data = load_manufacturer_data()
    
    print(f"Found {len(manufacturers_data)} manufacturers")
    
    # Create folders and files for each manufacturer
    for manufacturer_name in sorted(manufacturers_data.keys()):
        if manufacturer_name in ['Fletcher', 'Thermotec']:
            print(f"Skipping {manufacturer_name} (already documented)")
            continue
        
        products_by_category = manufacturers_data[manufacturer_name]
        mfg_dir = KNOWLEDGE_BASE_DIR / manufacturer_name.lower()
        mfg_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Processing {manufacturer_name} ({sum(len(p) for p in products_by_category.values())} products)...")
        
        # Create families.json
        families_data = create_family_json_for_manufacturer(manufacturer_name, products_by_category)
        families_json_path = mfg_dir / "families.json"
        with open(families_json_path, 'w', encoding='utf-8') as f:
            json.dump(families_data, f, indent=2, ensure_ascii=False)
        print(f"  [OK] Created {families_json_path.name}")
        
        # Create README.md
        readme_content = f"""# {manufacturer_name} product-family knowledge base

Bot-facing knowledge for {manufacturer_name} products. Each file represents a technical family, not an individual stock SKU.

## Family index

| Family ID | Product family | Evidence status |
| --- | --- | --- |
"""
        
        for family in families_data['families']:
            readme_content += f"| `{family['family_id']}` | {family['name']} | Initial documentation |\n"
        
        readme_content += f"""

## Retrieval rule

1. Identify the application and problem before comparing manufacturers.
2. Rank families using application/keyword fit and the customer's priority.
3. Recommend only a manufacturer-supported family.
4. Keep thermal R-values, acoustic Rw, and fire-test results separate.
5. Select the exact SKU, grade, and quantity only after technical review.
"""
        
        readme_path = mfg_dir / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        print(f"  [OK] Created {readme_path.name}")
        
        # Create product family markdown files
        for family in families_data['families']:
            category = family['category']
            family_id = family['family_id']
            product_count = family['product_count']
            
            md_content = create_product_family_md(family_id, manufacturer_name, category, product_count)
            md_path = mfg_dir / family['knowledge_file']
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"  [OK] Created {family['knowledge_file']}")
    
    print("\n[DONE] Documentation generation complete!")
    print(f"Created documentation for {len([m for m in manufacturers_data.keys() if m not in ['Fletcher', 'Thermotec']])} manufacturers")

if __name__ == "__main__":
    main()
