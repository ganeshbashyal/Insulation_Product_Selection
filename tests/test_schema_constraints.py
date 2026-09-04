import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def test_family_schema_rejects_unknown_confidence_and_bad_url():
    schema = json.loads((ROOT / "schemas" / "families.schema.json").read_text(encoding="utf-8"))
    document = json.loads((ROOT / "knowledge" / "thermotec" / "families.json").read_text(encoding="utf-8"))
    invalid = copy.deepcopy(document)
    invalid["families"][0]["confidence"] = "probably_supported"
    invalid["families"][0]["source_url"] = "not a link"
    issues = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(invalid))
    assert len(issues) >= 2


def test_evidence_schema_rejects_invalid_confidence_range_and_timestamp():
    schema = json.loads((ROOT / "schemas" / "performance-evidence.schema.json").read_text(encoding="utf-8"))
    document = json.loads((ROOT / "knowledge" / "performance_evidence.json").read_text(encoding="utf-8"))
    invalid = copy.deepcopy(document)
    item = next(record["evidence_items"][0] for record in invalid["families"] if record["evidence_items"])
    item["extractor_confidence"] = 1.5
    item["verified_at"] = "yesterday"
    issues = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(invalid))
    assert len(issues) >= 2
