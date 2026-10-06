import json
from pathlib import Path

import pytest

import scripts.review_full_suite_local as review


def _write_packet(run_dir: Path, families: list[dict]) -> tuple[str, str]:
    batch_id = "batch-001"
    packet = {"batch_id": batch_id, "families": families}
    packet["packet_sha256"] = review._sha256(review._canonical(packet).encode("utf-8"))
    batch_path = run_dir / "batches" / "batch-001.json"
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(json.dumps(packet), encoding="utf-8")
    coverage = {
        "families": [
            {
                "family_id": family["family_id"],
                "coverage_status": "eligible_pending_owner_submission",
                "source_status": "local_and_supplied_urls",
                "source_urls": family.get("source_references", []),
                "batch_id": batch_id,
            }
            for family in families
        ],
        "batches": [{
            "batch_id": batch_id,
            "packet_file": "batches\\batch-001.json",
            "packet_sha256": packet["packet_sha256"],
        }],
    }
    (run_dir / "coverage_manifest.json").write_text(json.dumps(coverage), encoding="utf-8")
    return batch_id, packet["packet_sha256"]


def _family(family_id: str, with_pages: bool = True) -> dict:
    return {
        "family_id": family_id,
        "family_name": family_id.replace("_", " ").title(),
        "manufacturer": "Test Maker",
        "structured_claims": [{"field": "spec.r_value", "text": "R2.0"}],
        "product_items": [],
        "unique_family_context": "Test family context.",
        "source_references": [{"url": "https://example.invalid/tds.pdf"}],
        "local_source": {
            "path": "data/tds/test.pdf",
            "sha256": "a" * 64,
            "pages": [{"page": 1, "excerpt": "Product rating R2.0 and glasswool.", "truncated": False}],
        } if with_pages else None,
    }


def _model_response(family_id: str) -> str:
    return json.dumps({
        "families": [{
            "family_id": family_id,
            "overall_result": "no_issue_found",
            "findings": [],
            "limitations": ["Only the supplied local page excerpt was inspected."],
        }]
    })


class _FakeOllama:
    def __init__(self):
        self.calls = []
        self.chat_calls = []

    def request(self, endpoint, payload=None):
        self.calls.append((endpoint, payload))
        if endpoint == "/api/tags":
            return {"models": [{"name": "llama3.1:8b"}]}
        if endpoint == "/api/ps":
            return {"models": []}
        self.chat_calls.append((endpoint, payload))
        prompt = payload["messages"][-1]["content"]
        family_id = json.loads(prompt.split("\n\n", 1)[1])["family_id"]
        return {"message": {"content": _model_response(family_id)}}


def test_review_input_only_contains_local_text_and_marks_truncated_context():
    family = _family("LOCAL_FAMILY")
    family["unique_family_context"] = "x" * (review.MAX_CONTEXT_CHARS + 1)
    payload, truncated = review._review_input(family, "b" * 64)

    assert truncated is True
    assert payload["unique_family_context"] == "x" * review.MAX_CONTEXT_CHARS
    assert payload["listed_url_count_not_opened"] == 1
    assert payload["local_source"]["pages"][0]["excerpt"].startswith("Product rating")


def test_validates_exact_page_quotes_and_rejects_unverifiable_citations():
    family = _family("LOCAL_FAMILY")
    payload, _ = review._review_input(family, "b" * 64)
    good = json.dumps({
        "families": [{
            "family_id": "LOCAL_FAMILY",
            "overall_result": "discrepancies_found",
            "findings": [{
                "claim_field": "material",
                "finding_type": "identity_variant",
                "page": 1,
                "source_quote": "glasswool",
                "explanation": "The source identifies glasswool.",
                "severity": "high",
                "confidence": "high",
                "owner_check": "Confirm the source applies to this family.",
            }],
            "limitations": [],
        }]
    })
    assert review.validate_response(good, payload)["family_id"] == "LOCAL_FAMILY"

    bad = json.loads(good)
    bad["families"][0]["findings"][0]["source_quote"] = "mineral wool"
    with pytest.raises(ValueError, match="not present"):
        review.validate_response(json.dumps(bad), payload)


def test_run_review_skips_unretrieved_url_only_family_and_resumes(tmp_path):
    local = _family("LOCAL_FAMILY")
    url_only = _family("URL_ONLY_FAMILY", with_pages=False)
    _write_packet(tmp_path, [local, url_only])
    client = _FakeOllama()

    summary = review.run_review(tmp_path, limit=1, client=client)

    assert len(client.chat_calls) == 1
    assert summary["total_families"] == 2
    assert summary["locally_reviewed"] == 1
    assert summary["skipped_without_local_page_text"] == 1
    assert summary["not_yet_reviewed_local_families"] == 0
    output = tmp_path / "local_review_llama3.1_8b" / "families"
    local_receipt = json.loads((output / "LOCAL_FAMILY.json").read_text(encoding="utf-8"))
    skipped_receipt = json.loads((output / "URL_ONLY_FAMILY.json").read_text(encoding="utf-8"))
    assert local_receipt["status"] == "reviewed"
    assert skipped_receipt["status"] == "skipped_no_local_source"
    assert skipped_receipt["source_urls_not_opened"] == 1

    again = review.run_review(tmp_path, limit=1, client=client)
    assert len(client.chat_calls) == 1
    assert again["locally_reviewed"] == 1


def test_packet_hash_mismatch_fails_before_model_call(tmp_path):
    _write_packet(tmp_path, [_family("LOCAL_FAMILY")])
    path = tmp_path / "batches" / "batch-001.json"
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["families"][0]["family_name"] = "Tampered"
    path.write_text(json.dumps(packet), encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        review._load_packets(tmp_path)
