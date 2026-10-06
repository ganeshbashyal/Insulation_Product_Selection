import pandas as pd

from scripts.generate_family_literature import build_markdown


def test_family_literature_lists_every_catalogue_row():
    count = 38
    skus = pd.DataFrame([{
        "sku_record_id": f"SKU-{index:03}",
        "our_sku": f"INT-{index:03}",
        "supplier_sku": f"SUP-{index:03}",
        "product_name": f"Product {index}",
        "thermal_r_value": "R2.0",
        "acoustic_rw": "",
        "nrc_aw": "",
        "material_type": "Glasswool",
        "validation_status": "REVIEW",
    } for index in range(count)])

    markdown, _ = build_markdown(
        {"family_id": "FAMILY_A", "name": "Family A", "manufacturer": "Maker",
         "category": "Batt", "applications": ["Walls"]},
        {},
        "## Canonical description\nFamily description.",
        skus,
    )

    assert all(f"SKU-{index:03}" in markdown for index in range(count))
    assert "All 38 catalogue source rows are listed" in markdown
    assert "38 further catalogue variants not listed" not in markdown


def test_manufacturer_range_does_not_duplicate_sku_table():
    skus = pd.DataFrame([{
        "sku_record_id": "SKU-ONE",
        "our_sku": "INT-1",
        "supplier_sku": "SUP-1",
        "product_name": "Product one",
        "thermal_r_value": "R2.0",
        "acoustic_rw": "",
        "nrc_aw": "",
        "material_type": "Glasswool",
        "validation_status": "REVIEW",
    }])
    markdown, _ = build_markdown(
        {"family_id": "FAMILY_A", "name": "Family A", "manufacturer": "Maker",
         "category": "Batt", "applications": ["Walls"]},
        {},
        "## Canonical description\nFamily description.",
        skus,
        research={"spec": {"range": [{
            "variant": "Standard",
            "size_or_rating": "R2.0",
            "pack": "One pack",
        }]}},
    )

    assert markdown.count("| SKU-ONE |") == 1
    assert markdown.count("**Internal catalogue range**") == 0
    assert "Standard | R2.0 | One pack" in markdown


def test_staff_release_skus_show_state_variances_without_price_amounts():
    markdown, _ = build_markdown(
        {"family_id": "FAMILY_A", "name": "Family A", "manufacturer": "Maker",
         "category": "Batt", "applications": ["Walls"]},
        {},
        "## Canonical description\nFamily description.",
        pd.DataFrame(),
        staff_skus=[{
            "our_sku": "SKU-ONE",
            "sales_product_name": "Product one",
            "family_mapping_status": "local_model_candidate_unreviewed",
            "melbourne_baseline": True,
            "state_presence": ["Melbourne", "Brisbane"],
            "state_differences": {
                "Melbourne": [],
                "Sydney": ["not_listed"],
                "Brisbane": ["MOQ", "sell_price_varies"],
            },
            "price_statuses": {"Melbourne": "numeric", "Brisbane": "poa"},
        }],
        staff_source={"source_workbook": "staff.xlsm", "source_sha256": "a" * 64},
    )

    assert "SKU-ONE" in markdown
    assert "Melbourne baseline" in markdown
    assert "Sydney: not listed" in markdown
    assert "sell price differs; amount omitted" in markdown
    assert "Melbourne: numeric, Brisbane: poa" in markdown
    assert "Local model candidate; review" in markdown
    assert "$" not in markdown
