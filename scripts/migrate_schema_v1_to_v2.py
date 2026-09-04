"""Idempotently migrate family/evidence JSON from schema 1.0 to 2.0."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY_PATHS = [ROOT / "knowledge" / "thermotec" / "families.json", ROOT / "knowledge" / "fletcher" / "families.json"]
EVIDENCE_PATH = ROOT / "knowledge" / "performance_evidence.json"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def infer_value_type(item: dict) -> str:
    if isinstance(item["value"], (int, float)):
        return "scalar"
    value = str(item["value"]).casefold()
    if " at " in value or (item["metric_type"] == "thermal_r" and " to " in value):
        return "per_thickness"
    if any(marker in value for marker in ["–", " to ", "range", "dependent"]):
        return "range"
    return "text_classification"


def identity_pointer(family: dict) -> dict:
    return {
        "evidence_id": f"{family['family_id']}-IDENTITY",
        "metric_type": "product_identity",
        "value": "Manufacturer page identifies the named product family",
        "value_type": "text_classification",
        "unit": "",
        "scope": "product",
        "variant": "Family identity",
        "test_standard": "Not applicable",
        "test_context": "Identity pointer only; it does not establish performance or compliance.",
        "source_url": family["source_url"],
        "source_type": "manufacturer_page",
        "source_locator": "Manufacturer product-page title and product description",
        "extraction_method": "manufacturer_page_link",
        "extractor_confidence": 1.0,
        "ocr_confidence": None,
        "evidence_status": "pending_human_review",
        "verified_by": None,
        "verified_at": None,
        "notes": "An authorised reviewer must confirm this is the current manufacturer family before verification."
    }


def migrate() -> None:
    all_families = {}
    for path in FAMILY_PATHS:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["schema_version"] = "2.0"
        for family in document["families"]:
            if family.get("source_url") == "":
                family["source_url"] = None
            if family.get("datasheet_url") == "":
                family["datasheet_url"] = None
            all_families[family["family_id"]] = family
        write_json(path, document)

    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["schema_version"] = "2.0"
    for record in evidence["families"]:
        for item in record["evidence_items"]:
            item.setdefault("value_type", infer_value_type(item))
            item.setdefault("source_locator", "Source page; exact section or page locator pending")
            item.setdefault("extraction_method", "legacy_migration")
            item.setdefault("extractor_confidence", 0.75)
            item.setdefault("ocr_confidence", None)
            if item.get("evidence_status") == "verified" and not item.get("verified_by"):
                item["evidence_status"] = "pending_human_review"
            item.setdefault("verified_by", None)
            item.setdefault("verified_at", None)
            item.pop("reviewed_at", None)
        family = all_families[record["family_id"]]
        if family["confidence"] == "manufacturer_supported" and not record["evidence_items"]:
            record["evidence_items"].append(identity_pointer(family))
    write_json(EVIDENCE_PATH, evidence)


if __name__ == "__main__":
    migrate()
    print("Schema v2 migration complete; unattributed verified claims were returned to pending human review.")
