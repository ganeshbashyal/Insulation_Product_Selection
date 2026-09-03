"""Map Fletcher Sheet1 rows to evidence-gated family records and write a validation report."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "Product_Master_Bot.xlsx"
CATALOGUE = ROOT / "knowledge" / "fletcher" / "families.json"
REPORT = ROOT / "reports" / "fletcher_validation_report.csv"


def family_id(row: pd.Series) -> str:
    name = str(row.get("Our Product Name", "")).casefold()
    use = str(row.get("Product Use", "")).casefold()
    if "safe'n'silent" in name or "safe n silent" in name:
        return "FLETCHER_SAFE_N_SILENT_LEGACY"
    if name.startswith("ff hd"):
        return "FLETCHER_FF_HD_LEGACY"
    if "supabatt" in name:
        return "FLETCHER_SUPABATT"
    if any(x in name for x in ["partywall", "party wall", "p/wall", "pwall", "protect pw batt", "protect ff roll", "fireseal", "fire strip"]):
        return "FLETCHER_PARTY_WALL_STONEWOOL"
    if any(x in name for x in ["thermatape", "vapastop", "plain foil", "3m seaming"]):
        return "FLETCHER_TAPES_ACCESSORIES"
    if "vapawrap" in name and any(x in name for x in ["mroof", "metal roof"]):
        return "FLETCHER_VAPAWRAP_METAL_ROOF"
    if "vapawrap" in name:
        return "FLETCHER_VAPAWRAP_WALL"
    if "tuff wrap" in name or "multipurpose 439" in name:
        return "FLETCHER_SISALATION_WRAP"
    if "foam cell" in name or "bubble cell" in name:
        return "FLETCHER_FOAM_BUBBLE_CELL"
    if "permastop" in name:
        return "FLETCHER_PERMASTOP"
    if "therm slab" in name:
        return "FLETCHER_PINK_THERMAL_SLAB"
    if "fi32" in name:
        return "FLETCHER_FI32_SEMI_RIGID"
    if "flex dliner" in name or "flex ductliner" in name:
        return "FLETCHER_FI24_FLEX_DUCTLINER"
    if "soundbreak" in name or "pinkssoundb" in name:
        return "FLETCHER_SOUNDBREAK"
    if "pink partition" in name:
        return "FLETCHER_PINK_PARTITION"
    if "floor batt" in name:
        return "FLETCHER_PINK_BATTS_FLOOR"
    if "pink batt" in name or "pinkbatt" in name or "perimeter batt" in name:
        return "FLETCHER_PINK_BATTS_CEILING" if "ceiling" in use else "FLETCHER_PINK_BATTS_WALL"
    return "UNMAPPED"


def main() -> None:
    rows = pd.read_excel(SOURCE, sheet_name="Sheet1")
    rows = rows[rows["Manufacturer Name"].astype(str).str.fullmatch("Fletcher", case=False, na=False)].copy()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))["families"]
    families = {item["family_id"]: item for item in catalogue}
    rows["Mapped Family ID"] = rows.apply(family_id, axis=1)
    rows["Mapped Family"] = rows["Mapped Family ID"].map(lambda x: families.get(x, {}).get("name", ""))
    rows["Family Evidence Status"] = rows["Mapped Family ID"].map(lambda x: families.get(x, {}).get("confidence", "missing"))
    rows["Knowledge File"] = rows["Mapped Family ID"].map(lambda x: f"knowledge/fletcher/{families[x]['knowledge_file']}" if x in families else "")
    rows["Knowledge File Exists"] = rows["Knowledge File"].map(lambda x: bool(x) and (ROOT / x).exists())
    rows["Usable for Family Recommendation"] = rows["Family Evidence Status"].str.startswith("manufacturer_supported") & rows["Knowledge File Exists"]
    rows["Usable for SKU Selection"] = rows["Usable for Family Recommendation"] & rows["Validation Status"].eq("PASS") & rows["Bot Content Status"].eq("READY")
    columns = [
        "Our SKU", "SKU", "Our Product Name", "Active?", "Category", "Product Use", "MPN",
        "Mapped Family ID", "Mapped Family", "Family Evidence Status", "Knowledge File", "Knowledge File Exists",
        "Thermal R Value", "Acoustic Rw", "NRC / αw", "Validation Status", "Validation Notes",
        "Bot Content Status", "External Validation", "Usable for Family Recommendation", "Usable for SKU Selection",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    rows[columns].to_csv(REPORT, index=False, encoding="utf-8-sig")
    print(f"Fletcher rows: {len(rows)}")
    print(f"Mapped rows: {(rows['Mapped Family ID'] != 'UNMAPPED').sum()}")
    print(f"Rows with knowledge files: {rows['Knowledge File Exists'].sum()}")
    print(f"Rows supporting family-level demo recommendation: {rows['Usable for Family Recommendation'].sum()}")
    print(f"Rows ready for exact SKU selection: {rows['Usable for SKU Selection'].sum()}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
