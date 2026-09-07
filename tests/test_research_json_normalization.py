import scripts.normalize_research_json as normalizer
import scripts.normalize_family_json as family_normalizer


def test_normalize_research_document_adds_canonical_top_level_and_spec_fields():
    normalized = normalizer.normalize_document(
        {
            "family_id": "DEMO_FAMILY",
            "family_name": "Demo Family",
            "status": "ok",
            "spec": {"range": [{"c0": "R2.5"}]},
        }
    )

    assert normalized["schema_version"] == "1.0"
    assert normalized["datasheet_pdf_url"] == ""
    assert normalized["retrieval"] == {}
    assert normalized["spec"]["range"] == [{"c0": "R2.5"}]
    assert normalized["spec"]["range_headers"] == []
    assert normalized["spec"]["technical"] == []
    assert normalized["spec"]["install"] == []
    assert normalized["spec"]["clearances"] == []


def test_normalize_research_document_is_idempotent():
    document = normalizer.normalize_document(
        {"family_id": "DEMO_FAMILY", "family_name": "Demo Family", "spec": {}}
    )
    assert normalizer.normalize_document(document) == document


def test_normalize_family_adds_shared_metadata_fields():
    normalized = family_normalizer.normalize_family(
        {"family_id": "DEMO_FAMILY", "name": "Demo Family"}, "demo_mfg"
    )

    assert normalized["manufacturer"] == "Demo Mfg"
    assert normalized["product_count"] == 0
    assert normalized["source_url_status"] is None
    assert normalized["legacy_source_url"] is None
