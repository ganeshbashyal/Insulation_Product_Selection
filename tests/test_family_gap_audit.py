import json

import pytest

from scripts.audit_family_gaps import gap_reasons, validate_review


def test_supplied_failed_link_is_not_missing_link():
    row = {"source_documents": 0, "download_failures": 1,
           "held_link_rows": 0, "extraction_gaps": 0}
    reasons = gap_reasons(row, [{"url": "https://example.test/tds.pdf"}])
    assert reasons == ["no_archived_family_source", "supplied_download_failed"]


def test_validate_advisory_sources_are_grounded():
    evidence = [{"family_id": "A", "cache_candidates": [{"sha256": "abc"}]}]
    review = {"families": [{"family_id": "A", "finding": "Failed supplied link.",
                           "next_action": "Review cached match.", "possible_cached_sources": ["abc"]}]}
    assert validate_review(json.dumps(review), evidence) == review["families"]
    review["families"][0]["possible_cached_sources"] = ["invented"]
    with pytest.raises(ValueError, match="source not in"):
        validate_review(json.dumps(review), evidence)


def test_validate_rejects_duplicate_families():
    evidence = [{"family_id": "A", "cache_candidates": []},
                {"family_id": "B", "cache_candidates": []}]
    item = {"family_id": "A", "finding": "Gap", "next_action": "Check",
            "possible_cached_sources": []}
    with pytest.raises(ValueError, match="duplicate"):
        validate_review(json.dumps({"families": [item, item]}), evidence)
