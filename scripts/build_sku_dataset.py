"""Build the all-manufacturer bot catalogue from the validated Sheet1 export."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot_engine import recommendation_allowed  # noqa: E402
from scripts.validate_fletcher import family_id as fletcher_family_id  # noqa: E402


THERMOTEC_RULES = [
    (r"4\s*-?\s*zero.*foil.*mlv|foil.*mlv.*nuwave", "THERMOTEC_NUWAVE_FOIL_FACED_MLV"),
    (r"fence.*nuwave|uv\s*treated.*nuwave", "THERMOTEC_NUWAVE_FENCE_MLV"),
    (r"underlay.*nuwave|nuwave.*underlay", "THERMOTEC_NUWAVE_UNDERLAY"),
    (r"nuwrap\s*5", "THERMOTEC_NUWRAP_5"), (r"nuwrap.*xtraflex|xtraflex", "THERMOTEC_NUWRAP_XTRAFLEX"),
    (r"nuwave\s*base", "THERMOTEC_NUWAVE_BASE_MLV"), (r"e[- ]?therm", "THERMOTEC_E_THERM"),
    (r"e[- ]?flex\s*ht", "THERMOTEC_E_FLEX_HT"), (r"e[- ]?flex\s*st", "THERMOTEC_E_FLEX_ST"),
    (r"stonewool|rockwool|\bspi\b|rw\s*120kg", "THERMOTEC_ROCKWOOL_PIPE"),
    (r"maxtape", "THERMOTEC_MAXTAPE_FR"), (r"maxflex\s*coil", "THERMOTEC_MAXFLEX_PIPE"),
    (r"4[- ]?zero", "THERMOTEC_4_ZERO"),
]


def thermotec_family_id(row: pd.Series) -> str:
    value = f"{row.get('Our Product Name', '')} {row.get('Product Use', '')}".casefold()
    return next((family_id for pattern, family_id in THERMOTEC_RULES if re.search(pattern, value)), "UNMAPPED")


def get_family_id_for_product(row: pd.Series, manufacturer: str, families: dict) -> str:
    """Generic family mapping based on manufacturer and product category."""
    manufacturer_lower = str(manufacturer).strip().casefold()
    
    # For thermotec and fletcher, use existing specific rules
    if manufacturer_lower == "thermotec":
        return thermotec_family_id(row)
    elif manufacturer_lower == "fletcher":
        return fletcher_family_id(row)
    
    # For all other manufacturers, map based on category
    category = str(row.get('Category', '')).strip() if pd.notna(row.get('Category')) else ''
    mfg_normalized = str(manufacturer).lower().replace(' ', '')
    
    # Find matching family by manufacturer and category
    for family_id, family in families.items():
        if family.get('manufacturer', '').lower().replace(' ', '') == mfg_normalized:
            family_category = family.get('category', '').lower()
            if category.lower() in family_category or family_category in category.lower():
                return family_id
    
    # If no exact match, try to find any family for this manufacturer
    for family_id, family in families.items():
        if family.get('manufacturer', '').lower().replace(' ', '') == mfg_normalized:
            return family_id
    
    return "UNMAPPED"


def load_families() -> dict[str, dict]:
    result = {}
    # Load families from all manufacturers in knowledge directory
    knowledge_dir = ROOT / "knowledge"
    for mfg_dir in knowledge_dir.iterdir():
        if mfg_dir.is_dir():
            families_path = mfg_dir / "families.json"
            if families_path.exists():
                for family in json.loads(families_path.read_text(encoding="utf-8"))["families"]:
                    result[family["family_id"]] = {**family, "manufacturer": family.get("manufacturer", mfg_dir.name.title())}
    return result


def clean(value):
    return "" if pd.isna(value) else value


def build(source: Path, output: Path, source_retrieved_at: str, manifest_output: Path) -> pd.DataFrame:
    rows = pd.read_excel(source, sheet_name="Sheet1")
    # Process all manufacturers
    families = load_families()
    evidence = {
        record["family_id"]: record
        for record in json.loads((ROOT / "knowledge" / "performance_evidence.json").read_text(encoding="utf-8"))["families"]
    }
    rows["family_id"] = rows.apply(lambda row: get_family_id_for_product(row, row.get("Manufacturer Name", ""), families), axis=1)
    if (rows["family_id"] == "UNMAPPED").any():
        names = rows.loc[rows["family_id"] == "UNMAPPED", "Our Product Name"].astype(str).unique()
        raise ValueError(f"Unmapped selected products: {', '.join(names[:10])}")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    result = pd.DataFrame({
        "manufacturer": rows["Manufacturer Name"], "our_sku": rows["Our SKU"], "supplier_sku": rows["SKU"],
        "product_name": rows["Our Product Name"], "active": rows["Active?"], "category": rows["Category"],
        "material_type": rows["Material Type"], "product_use": rows["Product Use"], "mpn": rows["MPN"],
        "family_id": rows["family_id"],
    })
    result.insert(0, "source_sheet_row", rows.index + 2)
    result.insert(0, "sku_record_id", [
        "SKU-" + hashlib.sha256(f"{row['Manufacturer Name']}|{index + 2}|{row['Our SKU']}|{row['SKU']}".encode()).hexdigest()[:16].upper()
        for index, row in rows.iterrows()
    ])
    result["family_name"] = rows["family_id"].map(lambda value: families[value]["name"])
    result["knowledge_file"] = rows.apply(lambda row: f"knowledge/{str(row['Manufacturer Name']).casefold()}/{families[row['family_id']]['knowledge_file']}", axis=1)
    result["thermal_r_value"] = rows["Thermal R Value"]
    result["acoustic_rw"] = rows["Acoustic Rw"]
    result["nrc_aw"] = rows["NRC / αw"]
    result["performance_source"] = rows["Performance Source"]
    result["tds_url"] = rows["TDS URL"]
    result["sds_url"] = rows["SDS URL"]
    result["validation_status"] = rows["Validation Status"]
    result["validation_notes"] = rows["Validation Notes"]
    result["bot_content_status"] = rows["Bot Content Status"]
    result["family_confidence"] = rows["family_id"].map(lambda value: families[value]["confidence"])
    result["family_recommendation_eligible"] = rows["family_id"].map(lambda value: recommendation_allowed(families[value]))
    result["verified_evidence_available"] = rows["family_id"].map(lambda family_id: any(item["evidence_status"] == "verified" for item in evidence[family_id]["evidence_items"]))
    result["sku_selection_eligible"] = result["family_recommendation_eligible"] & result["verified_evidence_available"] & result["validation_status"].astype(str).str.upper().eq("PASS") & result["bot_content_status"].astype(str).str.upper().eq("READY")
    result["source_workbook"] = source.name
    result["source_sha256"] = source_hash
    result["source_retrieved_at"] = source_retrieved_at
    result = result.map(clean)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8")
    manifest = result[["sku_record_id", "source_sheet_row", "manufacturer", "our_sku", "supplier_sku", "family_id"]].copy()
    manifest["evidence_ids"] = result["family_id"].map(lambda family_id: ";".join(item["evidence_id"] for item in evidence[family_id]["evidence_items"]))
    manifest["evidence_statuses"] = result["family_id"].map(lambda family_id: ";".join(sorted({item["evidence_status"] for item in evidence[family_id]["evidence_items"]})))
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(manifest_output, index=False, encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "product_catalogue_skus.csv")
    parser.add_argument("--manifest-output", type=Path, default=ROOT / "data" / "processed" / "sku_evidence_manifest.csv")
    parser.add_argument("--source-retrieved-at", help="ISO-8601 timestamp for when this exact source export was acquired")
    args = parser.parse_args()
    retrieved_at = args.source_retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    result = build(args.source, args.output, retrieved_at, args.manifest_output)
    print(json.dumps({"rows": len(result), "families": result["family_id"].nunique(), "family_eligible": int(result["family_recommendation_eligible"].sum()), "sku_eligible": int(result["sku_selection_eligible"].sum()), "output": str(args.output), "manifest": str(args.manifest_output)}))


if __name__ == "__main__":
    main()
