import json
from pathlib import Path

import pandas as pd

import scripts.validate_product_sheet as validator


def test_audit_row_uses_local_model_adjudication(monkeypatch):
    row = pd.Series({
        "Manufacturer Name": "Fletcher",
        "Our SKU": "INT-1",
        "SKU": "SUP-1",
        "Our Product Name": "Pink Batts Ceiling Insulation",
        "Category": "Bulk insulation",
        "Material Type": "Glasswool",
        "Product Use": "Ceiling",
        "MPN": "901304",
        "Validation Status": "PASS",
        "Validation Notes": "OK",
        "Bot Content Status": "READY",
        "family_id": "FLETCHER_PINK_BATTS_CEILING",
    })
    families = {
        "FLETCHER_PINK_BATTS_CEILING": {
            "family_id": "FLETCHER_PINK_BATTS_CEILING",
            "manufacturer": "Fletcher",
            "name": "Pink Batts Ceiling Insulation",
            "category": "Bulk insulation",
            "primary_function": "Ceiling thermal insulation",
            "confidence": "manufacturer_supported",
            "knowledge_file": "pink-batts-ceiling.md",
            "applications": ["ceiling"],
            "keywords": ["pink batts ceiling", "ceiling insulation"],
            "questions": ["What R-value?"],
            "human_gates": ["Confirm current regional SKU"],
        }
    }
    monkeypatch.setattr(validator, "get_family_id_for_product", lambda *args, **kwargs: "FLETCHER_PINK_BATTS_CEILING")
    monkeypatch.setattr(validator, "_candidate_families", lambda *args, **kwargs: [{
        "family_id": "FLETCHER_PINK_BATTS_CEILING",
        "score": 99,
        "summary": {
            "family_id": "FLETCHER_PINK_BATTS_CEILING",
            "name": "Pink Batts Ceiling Insulation",
            "manufacturer": "Fletcher",
            "category": "Bulk insulation",
            "primary_function": "Ceiling thermal insulation",
            "confidence": "manufacturer_supported",
            "applications": ["ceiling"],
            "keywords": ["pink batts ceiling"],
            "questions": [],
            "human_gates": [],
            "excerpt": "Pink Batts Ceiling is the Fletcher family for ceiling thermal performance.",
        },
    }])
    monkeypatch.setattr(validator, "_model_chat", lambda *args, **kwargs: json.dumps({
        "status": "supported",
        "best_family_id": "FLETCHER_PINK_BATTS_CEILING",
        "confidence": 96,
        "code_alignment": "strong",
        "literature_alignment": "strong",
        "reasons": ["Manufacturer, product name and code align with the ceiling family."],
        "conflicts": [],
        "follow_up_questions": [],
        "canonical_checks": {
            "manufacturer": True,
            "material": True,
            "product_name": True,
            "product_code": True,
        },
    }))

    result = validator._audit_row(validator.ROOT, row, families, "llama3.2:latest", 1)

    assert result["status"] == "supported"
    assert result["best_family_id"] == "FLETCHER_PINK_BATTS_CEILING"
    assert result["deterministic_family_id"] == "FLETCHER_PINK_BATTS_CEILING"
    assert result["confidence"] == 96
    assert result["canonical_checks"]["product_code"] is True


def test_family_report_groups_rows_and_flags_quick_glance():
    records = {
        "FAMILY_ONE": {
            "family_id": "FAMILY_ONE",
            "manufacturer": "Fletcher",
            "name": "Family One",
            "status": "supported",
            "confidence": 94,
            "code_alignment": "strong",
            "literature_alignment": "strong",
            "reasons": ["Row A"],
            "conflicts": [],
            "follow_up_questions": [],
            "row_count": 2,
            "best_family_id": "FAMILY_ONE",
            "source_family_id": "FAMILY_ONE",
            "rows": [
                {"sku_record_id": "A", "our_sku": "A", "supplier_sku": "SUP-A", "mpn": "MPN-A", "product_name": "Product A", "category": "Bulk", "material_type": "Glass wool", "product_use": "Ceiling"},
                {"sku_record_id": "B", "our_sku": "B", "supplier_sku": "SUP-B", "mpn": "MPN-B", "product_name": "Product B", "category": "Bulk", "material_type": "Glass wool", "product_use": "Ceiling"},
            ],
        },
    }
    families = {
        "FAMILY_ONE": {
            "family_id": "FAMILY_ONE",
            "manufacturer": "Fletcher",
            "name": "Family One",
            "category": "Bulk insulation",
            "knowledge_file": "family-one.md",
        }
    }
    markdown = validator._family_report(records, families)
    assert "Quick-glance eligible SKU rows:** 2" in markdown
    assert "Fletcher / FAMILY_ONE / Family One" in markdown
    assert "Product A" in markdown and "Product B" in markdown
    assert "Family assessment:** supported (94/100 confidence)" in markdown
    assert "family-level assessment; not individual row verification" in markdown
    assert "SUP-A" in markdown and "MPN-B" in markdown
    assert "Code alignment:** strong" in markdown


def test_family_report_shows_failed_family_and_source_rows_without_inventing_row_verdicts():
    records = {
        "FAMILY_FAILED": {
            "family_id": "FAMILY_FAILED",
            "manufacturer": "Fletcher",
            "status": "model_reply_unparseable",
            "confidence": None,
            "rows": [
                {
                    "sku_record_id": "SKU-1",
                    "our_sku": "SKU-1",
                    "supplier_sku": "SUP-1",
                    "mpn": "MPN-1",
                    "product_name": "Product one",
                }
            ],
        }
    }
    markdown = validator._family_report(records, {})
    assert "Family assessment:** model_reply_unparseable (0/100 confidence)" in markdown
    assert "Quick-glance eligible SKU rows:** 0" in markdown
    assert "SKU-1" in markdown and "SUP-1" in markdown and "MPN-1" in markdown
    assert "Family assessment: **model_failed**" not in markdown


def test_write_reports_persists_markdown_and_state(tmp_path, monkeypatch):
    records = {
        "FAMILY_ONE": {
            "family_id": "FAMILY_ONE",
            "manufacturer": "Fletcher",
            "name": "Family One",
            "status": "supported",
            "confidence": 94,
            "code_alignment": "strong",
            "literature_alignment": "strong",
            "reasons": ["Row A"],
            "conflicts": [],
            "follow_up_questions": [],
            "row_count": 1,
            "rows": [
                {"sku_record_id": "A", "our_sku": "A", "product_name": "Product A"}
            ],
            "validation_status": "PASS",
            "validation_notes": "OK",
            "bot_content_status": "READY",
            "canonical_checks": {"manufacturer": True},
        }
    }
    families = {
        "FAMILY_ONE": {
            "family_id": "FAMILY_ONE",
            "manufacturer": "Fletcher",
            "name": "Family One",
            "category": "Bulk insulation",
            "knowledge_file": "family-one.md",
        }
    }
    state = {"source_path": "example.xlsx"}
    monkeypatch.setattr(validator, "OUTPUT_JSON", tmp_path / "product_sheet_validation.json")
    monkeypatch.setattr(validator, "OUTPUT_CSV", tmp_path / "product_sheet_validation.csv")
    monkeypatch.setattr(validator, "OUTPUT_MD", tmp_path / "product_sheet_family_review.md")
    monkeypatch.setattr(validator, "STATE_JSON", tmp_path / "state.json")

    validator._write_reports(records, families, state)

    assert (tmp_path / "product_sheet_validation.json").is_file()
    assert (tmp_path / "product_sheet_validation.csv").is_file()
    assert (tmp_path / "product_sheet_family_review.md").is_file()
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["completed_rows"] == 1
    assert saved["output"]["markdown"].endswith("product_sheet_family_review.md")
