import hashlib
import json
from pathlib import Path

import pytest

import scripts.prepare_chatgpt_validation_pilot as pilot


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_inputs(root: Path, monkeypatch):
    ids = tuple(f"FAMILY_{index}" for index in range(5))
    families = []
    cached_docs = {}
    mapping = []
    accuracy = []
    for index, family_id in enumerate(ids):
        pdf_relative = f"data/tds/maker/source_{index}.pdf"
        pdf_hash = _write(root / pdf_relative, f"PDF fixture {index}")
        guide_relative = f"knowledge/maker/guide_{index}.md"
        guide_hash = _write(root / guide_relative, f"# Guide {index}\nSize $100.00")
        literature_relative = f"output/literature/maker/family_{index}.md"
        literature_hash = _write(root / literature_relative, f"# Literature {index}\nSource email: test@example.invalid")
        research_relative = f"knowledge/maker/research/family_{index}.json"
        research_hash = _write(root / research_relative, json.dumps({
            "family_id": family_id,
            "datasheet_pdf_url": f"https://maker.invalid/tds/{index}.pdf",
            "datasheet_source": "supplied_manually",
            "spec": {
                "range": [{
                    "variant": f"R{index + 1}.0",
                    "product_code": f"CODE-{index}",
                    "size_or_rating": "90 mm",
                    "price": "$12.00",
                }],
            },
        }))
        families.append({
            "family_id": family_id,
            "family_name": f"Family {index}",
            "manufacturer": "Maker",
            "status": "partial_exact_matches_flagged",
            "facts_checked": 1,
            "facts_exact_in_pdf": 1,
            "facts_exact_in_literature": 1,
            "facts_provisional_internal_match": 1,
            "facts_needing_review": 0,
            "flags": ["test_flag"],
            "facts": [{
                "field": "spec.technical[0].value",
                "text": "R2.0",
                "status": "provisional_internal_transcription_match",
                "exact_hash_bound_pdf_matches": [{"path": pdf_relative, "sha256": pdf_hash, "pages": [1]}],
            }],
            "documents": [{
                "path": pdf_relative, "sha256": pdf_hash, "current_sha256": pdf_hash,
                "manifest_hash_matches": True, "exists": True,
            }],
            "authoring_inputs": [
                {"path": research_relative, "sha256": research_hash},
                {"path": guide_relative, "sha256": guide_hash},
            ],
            "family_literature": [{"path": literature_relative, "sha256": literature_hash}],
        })
        cached_docs[pdf_relative] = {
            "sha256": pdf_hash, "status": "text_extracted", "page_count": 1,
            "truncated": False, "pages": [{"page": 1, "text": f"R2.0 source evidence {index}\nPrice $100.00\nEmail: test@example.invalid"}],
        }
        mapping.append({
            "family_id": family_id, "status": "supported", "confidence": 100,
            "row_count": 2, "source_signature": f"old-signature-{index}",
            "rows": [{"our_sku": "SECRET-ROW-SHOULD-NOT-LEAK"}],
        })
        accuracy.append({
            "family_id": family_id, "status": "validated", "accuracy_score": 80,
            "unsupported_claims": "test claim", "missed_facts": "test omission",
        })
    source_review_path = root / "data/local/source_review.json"
    source_review_path.parent.mkdir(parents=True, exist_ok=True)
    source_review_path.write_text(json.dumps({"documents": cached_docs}), encoding="utf-8")
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports/product_sheet_validation.json").write_text(json.dumps(mapping), encoding="utf-8")
    (root / "reports/tds_accuracy.json").write_text(json.dumps(accuracy), encoding="utf-8")
    (root / "data/local/product_sheet_validation_state.json").write_text(
        json.dumps({"source_hash": "historical-hash", "model": "local-model"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pilot, "read_current_report", lambda root: {
        "report_signature": "audit-signature",
        "generated_at": "2026-10-06T00:00:00Z",
        "families": families,
    })
    return ids


def test_builds_blind_packet_and_separate_prior_results_addendum(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    packet, comparison = pilot.build_packet(tmp_path, ids)

    assert [family["family_id"] for family in packet["families"]] == list(ids)
    assert packet["provenance"]["network_or_model_calls_made"] is False
    assert packet["provenance"]["review_states_changed"] is False
    blind = json.dumps(packet, ensure_ascii=False)
    assert "supported" not in blind
    assert "confidence" not in blind
    assert "SECRET-ROW-SHOULD-NOT-LEAK" not in blind
    assert "$100.00" not in blind
    assert "test@example.invalid" not in blind
    assert '"sha256"' in blind
    assert comparison["families"][0]["prior_product_sheet_mapping_assessment"]["status"] == "supported"
    assert comparison["families"][0]["prior_tds_accuracy_assessment"]["accuracy_score"] == 80
    assert "historical" in comparison["limitations"][1]


def test_rejects_non_supported_or_unbound_family(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    report = pilot.read_current_report(tmp_path)
    next(family for family in report["families"] if family["family_id"] == ids[0])["documents"][0]["manifest_hash_matches"] = False
    monkeypatch.setattr(pilot, "read_current_report", lambda root: report)
    with pytest.raises(ValueError, match="No complete hash-bound local PDF"):
        pilot.build_packet(tmp_path, ids)


def test_requires_exactly_five_distinct_families(tmp_path, monkeypatch):
    _fixture_inputs(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="exactly five"):
        pilot.build_packet(tmp_path, ("FAMILY_0",))


def test_writes_packet_prompt_and_addendum_separately(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    packet, comparison = pilot.build_packet(tmp_path, ids)
    packet_path, prompt_path, comparison_path, comparison_markdown_path = pilot.write_packet(
        packet, comparison, tmp_path / "out"
    )

    assert packet_path.is_file()
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "blind pilot" in prompt
    assert "prior" not in prompt.casefold()
    assert "do not grant the model broad repository access" in prompt
    assert json.loads(comparison_path.read_text(encoding="utf-8"))["purpose"].endswith(
        "open_only_after_blind_pass"
    )
    comparison_markdown = comparison_markdown_path.read_text(encoding="utf-8")
    assert "open only after blind review" in comparison_markdown
    assert all(family_id in comparison_markdown for family_id in ids)


def test_full_suite_builds_blind_batches_with_supplied_urls_and_items(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    manifest, batches, signature = pilot.build_full_suite(tmp_path, max_batch_tokens=5000)

    assert len(manifest) == 5
    assert sum(len(batch) for batch in batches) == 5
    assert all(row["coverage_status"] == "eligible_pending_owner_submission" for row in manifest)
    first = batches[0][0]
    blind = json.dumps(first, ensure_ascii=False)
    assert first["source_references"][0]["provenance"] == "supplied_manually"
    assert first["source_references"][0]["url"].startswith("https://maker.invalid/")
    assert first["product_items"][0]["item"]["variant"]
    assert "CODE-0" in blind
    assert "$12.00" not in blind
    assert "supported" not in blind
    assert "confidence" not in blind
    assert "prior" not in blind.casefold()

    run_dir = pilot.write_full_suite(
        manifest, batches, signature, tmp_path / "output", max_batch_tokens=5000
    )
    coverage = json.loads((run_dir / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert len(coverage["families"]) == 5
    assert coverage["network_or_model_calls_made"] is False
    assert coverage["canonical_data_changed"] is False
    assert (run_dir / "owner_instructions.md").is_file()
    prompt_files = list((run_dir / "batches").glob("*_prompt.md"))
    assert prompt_files
    prompt = prompt_files[0].read_text(encoding="utf-8")
    assert "Do not search the web" in prompt.replace("\n", " ")
    assert "only the exact URLs explicitly listed" in prompt


def test_full_suite_reports_families_without_local_or_supplied_sources(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    report = pilot.read_current_report(tmp_path)
    target = next(family for family in report["families"] if family["family_id"] == ids[0])
    target["documents"] = []
    research_path = tmp_path / "knowledge/maker/research/family_0.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    research.pop("datasheet_pdf_url")
    research.pop("datasheet_source")
    _write(research_path, json.dumps(research))
    target["authoring_inputs"][0]["sha256"] = hashlib.sha256(
        research_path.read_bytes()
    ).hexdigest()
    monkeypatch.setattr(pilot, "read_current_report", lambda root: {
        **report,
        "families": report["families"],
    })

    manifest, batches, _ = pilot.build_full_suite(tmp_path, max_batch_tokens=5000)

    excluded = next(row for row in manifest if row["family_id"] == ids[0])
    assert excluded["coverage_status"] == "held_insufficient_source_evidence"
    assert excluded["batch_id"] is None
    assert sum(len(batch) for batch in batches) == 4


def test_full_suite_uses_supplied_url_when_local_pdf_exceeds_page_limit(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    report = pilot.read_current_report(tmp_path)
    family = next(row for row in report["families"] if row["family_id"] == ids[0])
    relative = family["documents"][0]["path"]
    source_review_path = tmp_path / "data/local/source_review.json"
    cache = json.loads(source_review_path.read_text(encoding="utf-8"))
    cache["documents"][relative]["pages"] = [
        {"page": page, "text": f"page {page} product specification"}
        for page in range(1, pilot.MAX_SOURCE_PAGES + 2)
    ]
    source_review_path.write_text(json.dumps(cache), encoding="utf-8")
    monkeypatch.setattr(pilot, "read_current_report", lambda root: report)

    manifest, batches, _ = pilot.build_full_suite(tmp_path, max_batch_tokens=5000)

    coverage = next(row for row in manifest if row["family_id"] == ids[0])
    assert coverage["coverage_status"] == "eligible_pending_owner_submission"
    assert "local_pdf_exceeds_six_page_text_limit" in coverage["reasons"]
    family_packet = next(
        item for batch in batches for item in batch if item["family_id"] == ids[0]
    )
    assert family_packet["local_source"]["pages_omitted_reason"]
    assert family_packet["source_references"]


def test_full_suite_includes_owner_source_leads_without_mutating_research(tmp_path, monkeypatch):
    ids = _fixture_inputs(tmp_path, monkeypatch)
    research_path = tmp_path / "knowledge/maker/research/family_0.json"
    before = research_path.read_bytes()
    leads_path = tmp_path / "data/local/chatgpt_validation_full_suite/owner_supplied_source_leads.json"
    leads_path.parent.mkdir(parents=True)
    leads_path.write_text(json.dumps({
        "schema_version": 1,
        "leads": [{
            "family_id": ids[0],
            "url": "https://maker.invalid/manual-review.pdf",
            "classification": "product_guide_only_not_tds",
            "owner_note": "Owner supplied guide link.",
            "review_eligible": True,
        }],
        "not_used_as_family_evidence": [{
            "family_id": ids[1],
            "url": "https://maker.invalid/wrong-product.pdf",
            "classification": "owner_marked_product_mismatch",
            "review_eligible": False,
        }],
    }), encoding="utf-8")

    manifest, batches, _ = pilot.build_full_suite(tmp_path, max_batch_tokens=5000)
    entry = next(row for row in manifest if row["family_id"] == ids[0])
    packet_family = next(
        family for batch in batches for family in batch if family["family_id"] == ids[0]
    )

    assert entry["coverage_status"] == "eligible_pending_owner_submission"
    source = next(
        row for row in packet_family["source_references"]
        if row["url"] == "https://maker.invalid/manual-review.pdf"
    )
    assert source["classification"] == "product_guide_only_not_tds"
    assert source["provenance"] == "owner_supplied_product_guide_only_not_tds"
    assert all(
        row["url"] != "https://maker.invalid/wrong-product.pdf"
        for batch in batches for family in batch for row in family["source_references"]
    )
    assert research_path.read_bytes() == before


def test_owner_source_leads_reject_unknown_family_id(tmp_path, monkeypatch):
    _fixture_inputs(tmp_path, monkeypatch)
    leads_path = tmp_path / "data/local/chatgpt_validation_full_suite/owner_supplied_source_leads.json"
    leads_path.parent.mkdir(parents=True)
    leads_path.write_text(json.dumps({
        "schema_version": 1,
        "leads": [{
            "family_id": "NOT_INDEXED",
            "url": "https://maker.invalid/source.pdf",
            "review_eligible": True,
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown family IDs"):
        pilot.build_full_suite(tmp_path, max_batch_tokens=5000)
