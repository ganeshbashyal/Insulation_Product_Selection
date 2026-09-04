"""Validate catalogue structure, evidence coverage and recommendation gates."""
from __future__ import annotations

import json
import csv
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot_engine import RECOMMENDATION_ALLOWED_STATES, RECOMMENDATION_BLOCKED_STATES, recommendation_allowed  # noqa: E402


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> list[str]:
    errors: list[str] = []
    family_schema = read_json(ROOT / "schemas" / "families.schema.json")
    evidence_schema = read_json(ROOT / "schemas" / "performance-evidence.schema.json")
    evidence = read_json(ROOT / "knowledge" / "performance_evidence.json")
    schema_states = set(family_schema["$defs"]["family"]["properties"]["confidence"]["enum"])
    if schema_states != RECOMMENDATION_ALLOWED_STATES | RECOMMENDATION_BLOCKED_STATES:
        errors.append("family confidence schema and config/catalogue_states.json disagree")
    catalogues: list[tuple[Path, dict]] = []
    for path in [ROOT / "knowledge" / "thermotec" / "families.json", ROOT / "knowledge" / "fletcher" / "families.json"]:
        document = read_json(path)
        catalogues.append((path, document))
        for issue in Draft202012Validator(family_schema, format_checker=FormatChecker()).iter_errors(document):
            errors.append(f"{path.relative_to(ROOT)}:{'/'.join(map(str, issue.absolute_path))}: {issue.message}")
    for issue in Draft202012Validator(evidence_schema, format_checker=FormatChecker()).iter_errors(evidence):
        errors.append(f"knowledge/performance_evidence.json:{'/'.join(map(str, issue.absolute_path))}: {issue.message}")

    families: dict[str, tuple[Path, dict]] = {}
    for path, document in catalogues:
        for family in document["families"]:
            family_id = family["family_id"]
            if family_id in families:
                errors.append(f"duplicate family_id: {family_id}")
            families[family_id] = (path, family)
            knowledge_file = path.parent / family["knowledge_file"]
            if not knowledge_file.is_file():
                errors.append(f"{family_id}: missing knowledge file {knowledge_file.relative_to(ROOT)}")
            if recommendation_allowed(family) and not family.get("source_url"):
                errors.append(f"{family_id}: recommendable family has no primary source URL")

    evidence_by_id: dict[str, dict] = {}
    evidence_ids: set[str] = set()
    for record in evidence["families"]:
        family_id = record["family_id"]
        if family_id in evidence_by_id:
            errors.append(f"duplicate performance family_id: {family_id}")
        evidence_by_id[family_id] = record
        for item in record["evidence_items"]:
            item_id = item["evidence_id"]
            if item_id in evidence_ids:
                errors.append(f"duplicate evidence_id: {item_id}")
            evidence_ids.add(item_id)
            if item["value_type"] == "scalar" and not isinstance(item["value"], (int, float)):
                errors.append(f"{item_id}: scalar evidence value must be numeric")
            if item["metric_type"] in {"thermal_r", "acoustic_rw", "acoustic_nrc", "acoustic_aw", "temperature_limit", "vapour_permeance"} and item["value_type"] == "scalar" and not item["unit"]:
                errors.append(f"{item_id}: scalar performance metric requires a unit")
            if item["evidence_status"] == "verified":
                if not item["verified_by"] or not item["verified_at"]:
                    errors.append(f"{item_id}: verified evidence requires verified_by and verified_at")
                if "pending" in item["source_locator"].casefold():
                    errors.append(f"{item_id}: verified evidence requires an exact source locator")
                if item["metric_type"] != "product_identity" and not item["test_standard"].strip():
                    errors.append(f"{item_id}: verified performance evidence requires a test standard")
            if item["extraction_method"] == "ocr" and item["ocr_confidence"] is None:
                errors.append(f"{item_id}: OCR evidence requires ocr_confidence")

    missing = sorted(set(families) - set(evidence_by_id))
    extra = sorted(set(evidence_by_id) - set(families))
    if missing:
        errors.append(f"families missing evidence records: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown families in evidence registry: {', '.join(extra)}")
    for family_id, (_, family) in families.items():
        record = evidence_by_id.get(family_id, {})
        if not recommendation_allowed(family) and record.get("automation_status") != "blocked_evidence":
            errors.append(f"{family_id}: unresolved identity/source must use blocked_evidence")
        if record.get("automation_status") == "blocked_evidence" and recommendation_allowed(family):
            # Supported families may still be blocked by performance review, but the reason must be explicit.
            if family.get("confidence") not in RECOMMENDATION_BLOCKED_STATES:
                errors.append(f"{family_id}: blocked evidence conflicts with its supported confidence state")
        if family.get("confidence") == "manufacturer_supported":
            usable_pointer = any(item.get("evidence_status") in {"verified", "pending_human_review"} for item in record.get("evidence_items", []))
            if not usable_pointer:
                errors.append(f"{family_id}: manufacturer_supported requires an evidence pointer")

    sku_path = ROOT / "data" / "processed" / "product_catalogue_skus.csv"
    required_columns = {
        "manufacturer", "our_sku", "supplier_sku", "product_name", "family_id", "knowledge_file",
        "thermal_r_value", "acoustic_rw", "nrc_aw", "performance_source", "tds_url", "sds_url",
        "validation_status", "validation_notes", "bot_content_status", "family_confidence",
        "family_recommendation_eligible", "verified_evidence_available", "sku_selection_eligible", "source_workbook", "source_sha256", "source_retrieved_at",
    }
    if not sku_path.is_file():
        errors.append("missing checked-in SKU dataset: data/processed/product_catalogue_skus.csv")
    else:
        with sku_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not required_columns.issubset(reader.fieldnames or []):
                errors.append(f"SKU dataset missing columns: {', '.join(sorted(required_columns - set(reader.fieldnames or [])))}")
            sku_rows = list(reader)
        if not sku_rows:
            errors.append("SKU dataset contains no products")
        if {row.get("manufacturer") for row in sku_rows} != {"Thermotec", "Fletcher"}:
            errors.append("SKU dataset must contain both Thermotec and Fletcher rows only")
        if any(row.get("family_id") not in families for row in sku_rows):
            errors.append("SKU dataset contains an unmapped or unknown family_id")
        if any(not (ROOT / row.get("knowledge_file", "")).is_file() for row in sku_rows):
            errors.append("SKU dataset contains a missing knowledge_file link")
        hashes = {row.get("source_sha256") for row in sku_rows}
        if len(hashes) != 1 or not next(iter(hashes), "") or len(next(iter(hashes), "")) != 64:
            errors.append("SKU dataset must carry one valid source SHA-256 provenance value")
        retrieval_times = {row.get("source_retrieved_at") for row in sku_rows}
        if len(retrieval_times) != 1:
            errors.append("SKU dataset must carry one source retrieval timestamp")
        else:
            try:
                datetime.fromisoformat(next(iter(retrieval_times)).replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                errors.append("SKU dataset source_retrieved_at must be an ISO-8601 timestamp")
        for index, row in enumerate(sku_rows, start=2):
            family = families.get(row.get("family_id"), ({}, {}))[1]
            expected_family = str(recommendation_allowed(family)).casefold()
            if row.get("family_recommendation_eligible", "").casefold() != expected_family:
                errors.append(f"SKU row {index}: family eligibility conflicts with evidence gate")
            has_verified_evidence = any(item.get("evidence_status") == "verified" for item in evidence_by_id.get(row.get("family_id"), {}).get("evidence_items", []))
            if row.get("verified_evidence_available", "").casefold() != str(has_verified_evidence).casefold():
                errors.append(f"SKU row {index}: verified-evidence flag conflicts with evidence registry")
            expected_sku = recommendation_allowed(family) and has_verified_evidence and row.get("validation_status", "").upper() == "PASS" and row.get("bot_content_status", "").upper() == "READY"
            if row.get("sku_selection_eligible", "").casefold() != str(expected_sku).casefold():
                errors.append(f"SKU row {index}: SKU eligibility conflicts with validation state")

        manifest_path = ROOT / "data" / "processed" / "sku_evidence_manifest.csv"
        if not manifest_path.is_file():
            errors.append("missing SKU evidence manifest")
        else:
            with manifest_path.open(encoding="utf-8", newline="") as handle:
                manifest_rows = list(csv.DictReader(handle))
            if len(manifest_rows) != len(sku_rows):
                errors.append("SKU evidence manifest row count differs from catalogue")
            sku_ids = {row.get("sku_record_id") for row in sku_rows}
            manifest_ids = {row.get("sku_record_id") for row in manifest_rows}
            if len(sku_ids) != len(sku_rows) or sku_ids != manifest_ids:
                errors.append("SKU evidence manifest does not provide a unique link for every SKU row")
            for row in manifest_rows:
                linked = {value for value in row.get("evidence_ids", "").split(";") if value}
                if not linked.issubset(evidence_ids):
                    errors.append(f"{row.get('sku_record_id')}: manifest references unknown evidence ID")
    return errors


def main() -> None:
    errors = validate()
    if errors:
        print("Catalogue validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("Catalogue validation passed: family schemas, knowledge files, evidence coverage and gates are consistent.")


if __name__ == "__main__":
    main()
