"""Build the checked-in Thermotec/Fletcher bot catalogue from the validated Sheet1 export."""
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


def load_families() -> dict[str, dict]:
    result = {}
    for manufacturer in ("thermotec", "fletcher"):
        path = ROOT / "knowledge" / manufacturer / "families.json"
        for family in json.loads(path.read_text(encoding="utf-8"))["families"]:
            result[family["family_id"]] = {**family, "manufacturer": manufacturer.title()}
    return result


def clean(value):
    return "" if pd.isna(value) else value


def build(source: Path, output: Path) -> pd.DataFrame:
    rows = pd.read_excel(source, sheet_name="Sheet1")
    rows = rows[rows["Manufacturer Name"].astype(str).str.casefold().isin(["thermotec", "fletcher"])].copy()
    families = load_families()
    rows["family_id"] = rows.apply(lambda row: thermotec_family_id(row) if str(row["Manufacturer Name"]).casefold() == "thermotec" else fletcher_family_id(row), axis=1)
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
    result["sku_selection_eligible"] = result["family_recommendation_eligible"] & result["validation_status"].astype(str).str.upper().eq("PASS") & result["bot_content_status"].astype(str).str.upper().eq("READY")
    result["source_workbook"] = source.name
    result["source_sha256"] = source_hash
    result = result.map(clean)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "product_catalogue_skus.csv")
    args = parser.parse_args()
    result = build(args.source, args.output)
    print(json.dumps({"rows": len(result), "families": result["family_id"].nunique(), "family_eligible": int(result["family_recommendation_eligible"].sum()), "sku_eligible": int(result["sku_selection_eligible"].sum()), "output": str(args.output)}))


if __name__ == "__main__":
    main()
