import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import scripts.check_family_transcription as audit
import research_api


def test_fact_inventory_uses_structured_tds_fields_not_catalogue_ranges():
    facts = audit._fact_values({
        "spec": {
            "description": "Dense glass fibre board.",
            "features": ["Thermal resistance R2.0"],
            "range": [{"rating": "R2.0", "price": 12.5}],
            "technical": [{"property": "R-value", "value": "R2.0", "standard": "AS/NZS 4859.1"}],
            "limitations": [],
        },
    })
    assert [row["text"] for row in facts] == [
        "Dense glass fibre board.", "Thermal resistance R2.0", "R2.0", "AS/NZS 4859.1",
    ]
    assert all("price" not in row["field"] for row in facts)


def test_exact_text_match_returns_source_page_locator():
    matches = audit._match_fact("Thermal resistance R2.0", [{
        "path": "data/tds/sample.pdf",
        "sha256": "a" * 64,
        "pages": [
            {"page": 1, "normalised": audit._normalise("Product overview")},
            {"page": 3, "normalised": audit._normalise("Thermal resistance R2.0, tested to standard")},
        ],
    }])
    assert matches == [{"path": "data/tds/sample.pdf", "sha256": "a" * 64, "pages": [3]}]


def test_report_requires_hash_matched_pdf_and_family_literature(monkeypatch, tmp_path):
    source = tmp_path / "data" / "tds" / "sample.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"local PDF placeholder")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    literature = "# Family\nThermal resistance R2.0."
    family_data = {
        "FAM": {
            "family": {"name": "Family", "manufacturer": "Maker"},
            "research": {"spec": {"technical": [{"value": "Thermal resistance R2.0"}]}},
            "derived_literature": {"output/literature/maker/fam.md": literature},
        },
    }
    family_data["FAM2"] = family_data["FAM"]
    cache_path = tmp_path / "data" / "local" / "source_review.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"documents": {
        "data/tds/sample.pdf": {
            "sha256": digest,
            "status": "text_extracted",
            "pages": [{"page": 3, "text": "Thermal resistance R2.0."}],
        },
    }}), encoding="utf-8")
    literature_path = tmp_path / "output" / "literature" / "maker" / "fam.md"
    literature_path.parent.mkdir(parents=True)
    literature_path.write_text(literature, encoding="utf-8")
    monkeypatch.setattr(audit, "GAP_REPORT", tmp_path / "gap.json")

    class FakeSources:
        def family(self, family_id, include_compiled=False):
            return {"documents": [{
                "path": "data/tds/sample.pdf",
                "sha256": digest,
                "exists": True,
                "manifest_hash_matches": True,
            }]}

    class FakeIndex:
        root = tmp_path
        families = {"FAM2": family_data["FAM2"]["family"], "FAM": family_data["FAM"]["family"]}
        sources = FakeSources()

        def detail(self, family_id):
            return family_data[family_id]

    monkeypatch.setattr(audit, "ResearchIndex", lambda root: FakeIndex())
    report = audit.build_report(tmp_path)
    audit.write_report(report, tmp_path / "data" / "local" / "family_tds_transcription_check")

    assert report["family_count"] == 2
    assert report["family_status_counts"] == {"provisional_transcription_match_candidate": 2}
    assert [family["family_id"] for family in report["families"]] == ["FAM", "FAM2"]
    fact = report["families"][0]["facts"][0]
    assert fact["exact_hash_bound_pdf_matches"][0]["pages"] == [3]
    assert fact["exact_in_family_literature"] is True
    assert audit._signature(report["families"], report["input_files"]) == report["report_signature"]
    assert report["canonical_data_changed"] is False
    assert report["publication_changed"] is False
    assert audit.read_current_report(tmp_path)["report_signature"] == report["report_signature"]

    source.write_bytes(b"changed PDF bytes")
    with pytest.raises(ValueError, match="inputs changed"):
        audit.read_current_report(tmp_path)


def test_transcription_audit_api_is_authenticated_read_only_and_links_documents(monkeypatch):
    class AuthStore:
        def session(self, token):
            if token == "reader":
                return {"username": "reader", "roles": ["reader"], "csrf": "csrf"}
            return None

    report = {
        "family_count": 1,
        "family_status_counts": {"partial_exact_matches_flagged": 1},
        "fact_count": 1,
        "provisional_internal_transcription_match_count": 1,
        "fact_review_count": 0,
        "report_signature": "b" * 64,
        "input_files": {},
        "families": [{
            "family_id": "FAM", "family_name": "Family", "manufacturer": "Maker",
            "status": "partial_exact_matches_flagged", "facts_checked": 1,
            "facts_provisional_internal_match": 1, "facts_needing_review": 0,
            "facts": [{
                "field": "spec.fire", "text": "Fire class B.",
                "status": "provisional_internal_transcription_match",
                "exact_in_family_literature": True,
                "exact_hash_bound_pdf_matches": [{
                    "path": "data/tds/family.pdf", "sha256": "a" * 64, "pages": [2],
                }],
            }],
        }],
    }

    class FakeIndex:
        documents = {"DOC-ID": {"id": "DOC-ID", "path": "data/tds/family.pdf", "sha256": "a" * 64}}

    monkeypatch.setattr(research_api, "store", lambda: AuthStore())
    monkeypatch.setattr(research_api, "index", lambda: FakeIndex())
    monkeypatch.setattr(audit, "read_current_report", lambda root: report)
    app = FastAPI()
    app.include_router(research_api.router)
    client = TestClient(app)

    assert client.get("/api/research/transcription-audit").status_code == 401
    client.cookies.set(research_api.COOKIE, "reader")
    summary = client.get("/api/research/transcription-audit")
    assert summary.status_code == 200
    assert "facts" not in summary.json()["items"][0]
    detail = client.get("/api/research/transcription-audit/family/FAM")
    assert detail.status_code == 200
    assert detail.json()["facts"][0]["exact_hash_bound_pdf_matches"][0]["document_id"] == "DOC-ID"
    assert "provisional internal transcription checks only" in detail.json()["review_boundary"]

    def stale_report(root):
        raise ValueError("Transcription audit inputs changed")

    monkeypatch.setattr(audit, "read_current_report", stale_report)
    assert client.get("/api/research/transcription-audit").status_code == 409
