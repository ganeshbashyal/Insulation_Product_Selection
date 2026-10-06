import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from family_review import (
    ReviewInventoryError,
    build_review_inventory,
    family_review_detail,
    mapped_group_review_detail,
    unmapped_review_detail,
    validate_family_review,
)
import research_api


SOURCE_HASH = "a" * 64


class FakeIndex:
    def __init__(self, root=None):
        self.root = root
        self.families = {
            "FAM-A": {"name": "Family A", "manufacturer": "Maker", "category": "Board"},
            "FAM-B": {"name": "Family B", "manufacturer": "Maker", "category": "Accessory"},
        }

    def detail(self, family_id):
        family = self.families[family_id]
        return {
            "family": family,
            "research": {"spec": {"install": ["Use safely"], "unit_price": 42}},
            "guide_text": "Local review guide",
            "dossier": {"provenance_state": "retained", "alternatives": [], "groups": {}},
            "sources": {
                "research_path": None,
                "guide": None,
                "source_gaps": ["No current source"],
                "documents": [],
            },
        }


class FakeStore:
    def __init__(self):
        self.rows = {}

    def history(self, target=None):
        return list(self.rows.get(target, [])) if target else []

    def save_revision(self, target, kind, payload, actor, expected_version):
        history = self.rows.setdefault(target, [])
        if expected_version != (history[-1]["id"] if history else 0):
            raise ValueError("Concurrent change")
        row = {"id": len(history) + 1, "kind": kind, "payload": payload,
               "actor": actor, "occurred": "2026-01-01T00:00:00Z"}
        history.append(row)
        return row


def make_inputs(root):
    inventory_path = root / "data/local/staff_release_skus_model_candidate.json"
    triage_path = root / "data/local/family_data_gathering/v3_sku_mapping_triage.json"
    inventory_path.parent.mkdir(parents=True)
    triage_path.parent.mkdir(parents=True)
    inventory = {
        "source_sha256": SOURCE_HASH,
        "price_values_included": False,
        "active_product_master_skus": 3,
        "products": [
            {"active": True, "sku": "SKU-A", "family_id": "FAM-A", "candidate_family_id": "FAM-B",
             "manufacturer": "Maker", "category": "Board", "product_name": "Panel $10.00",
             "family_mapping_group": "G-A", "price": 10.0, "price_values_included": False},
            {"active": True, "sku": "SKU-B", "family_id": "FAM-B", "candidate_family_id": "FAM-B",
             "manufacturer": "Maker", "category": "Accessory", "product_name": "Tape",
             "family_mapping_group": "G-B", "price": 20.0, "price_values_included": False},
            {"active": True, "sku": "SKU-C", "family_id": None, "candidate_family_id": None,
             "manufacturer": "Maker", "product_name": "Unmapped", "price": 30.0,
             "price_values_included": False},
        ],
    }
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    triage = {
        "source_sha256": SOURCE_HASH,
        "price_values_included": False,
        "inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        "unmapped_sku_count": 1,
        "mapped_group_audit": [{
            "group_id": "G-A", "family_id": "FAM-A",
            "product_identity_review": {
                "issues": ["product_names_contain_specific_other_family_terms"],
                "products": [{"sku": "SKU-A", "best_distinct_alternate_family_match": {
                    "family_id": "FAM-B", "name": "Family B",
                }}],
            },
        }],
        "priority_review_queue": [{
            "group_id": "G-A", "manufacturer": "Maker", "sku_count": 1,
            "current_family_id": "FAM-A", "current_family_name": "Family A",
            "mapping_status": "heuristic_candidate_review_required",
            "review_reasons": ["product_names_contain_specific_other_family_terms"],
            "alternate_family_matches": [{"family_id": "FAM-B", "name": "Family B"}],
            "form_conflicts": [],
            "mismatched_name_examples": [{"sku": "SKU-A", "product_name": "Panel $10.00"}],
        }],
        "unmapped_groups": [{
            "group_id": "UG-1", "manufacturer": "Maker", "family_code": "X",
            "products": [{"sku": "SKU-C", "manufacturer": "Maker", "mpn": "MPN-C",
                          "product_name": "Unmapped", "unit_cost": 90}],
        }],
    }
    triage_path.write_text(json.dumps(triage), encoding="utf-8")


@pytest.fixture
def review_context(tmp_path):
    make_inputs(tmp_path)
    return tmp_path, FakeIndex(), FakeStore()


def test_inventory_covers_families_mapped_candidates_and_unmapped_without_prices(review_context):
    root, idx, store = review_context
    result = build_review_inventory(root, idx, store)

    assert result["family_count"] == 2
    assert result["active_sku_count"] == 3
    assert result["mapped_sku_count"] == 2
    assert result["mapped_exception_group_count"] == 1
    assert result["mapped_exception_sku_count"] == 1
    assert result["unmapped_sku_count"] == 1
    assert {row["family_id"] for row in result["families"]} == {"FAM-A", "FAM-B"}
    assert {row["sku_count"] for row in result["families"]} == {1, 2}
    family_b = family_review_detail(root, idx, store, "FAM-B")
    assert [(row["sku"], row["association"]) for row in family_b["v3_products"]] == [
        ("SKU-B", "current"), ("SKU-A", "candidate"),
    ]
    assert result["unmapped_groups"][0]["products"][0]["sku"] == "SKU-C"
    assert result["mapped_exception_groups"][0]["sku_ids"] == ["SKU-A"]
    assert result["unmapped_groups"][0]["suggestion"]["applied"] is False
    assert "$10.00" not in json.dumps(result)
    assert "unit_cost" not in json.dumps(result)
    assert '"price":' not in json.dumps(result)


def test_details_include_every_sku_and_redact_dossier_price_fields(review_context):
    root, idx, store = review_context
    family = family_review_detail(root, idx, store, "FAM-A")
    unmapped = unmapped_review_detail(root, idx, store, "UG-1")

    assert family["v3_sku_ids"] == ["SKU-A"]
    assert family["research"]["spec"]["install"] == ["Use safely"]
    assert "unit_price" not in json.dumps(family)
    assert "$10.00" not in json.dumps(family)
    assert unmapped["sku_ids"] == ["SKU-C"]
    assert unmapped["products"][0]["mpn"] == "MPN-C"
    assert "unit_cost" not in json.dumps(unmapped)


def test_mapped_exception_detail_and_attestation_are_group_scoped(review_context):
    root, idx, store = review_context
    detail = mapped_group_review_detail(root, idx, store, "G-A")
    assert detail["sku_ids"] == ["SKU-A"]
    assert [row["sku"] for row in detail["products"]] == ["SKU-A"]
    assert detail["products"][0]["alternate_family_match"]["family_id"] == "FAM-B"
    assert "$10.00" not in json.dumps(detail)
    assert "unit_price" not in json.dumps(detail)

    data = {
        "decision": "correction_needed",
        "rationale": "This flagged group needs the exact alternate family checked.",
        "review_signature": detail["signature"],
        "reviewed_sku_ids": detail["sku_ids"],
        "identity_checked": True,
        "sources_checked": True,
        "sku_mappings_checked": True,
    }
    saved = validate_family_review(root, idx, store, "mapped", "G-A", data, "reviewer", 0)

    assert saved["canonical_mapping_changed"] is False
    payload = store.history("family-validation:mapped:G-A")[-1]["payload"]
    assert payload["reviewed_sku_ids"] == ["SKU-A"]
    assert payload["source_binding_changed"] is False
    assert payload["publication_changed"] is False


def test_family_attestation_requires_exact_skus_and_preserves_approval_boundaries(review_context):
    root, idx, store = review_context
    detail = family_review_detail(root, idx, store, "FAM-A")
    data = {
        "decision": "confirmed",
        "rationale": "Identity, source state and associated SKU mapping checked.",
        "review_signature": detail["signature"],
        "reviewed_sku_ids": detail["v3_sku_ids"],
        "identity_checked": True,
        "sources_checked": True,
        "sku_mappings_checked": True,
    }

    saved = validate_family_review(root, idx, store, "family", "FAM-A", data, "reviewer", 0)

    assert saved["decision"] == "confirmed"
    assert saved["canonical_mapping_changed"] is False
    payload = store.history("family-validation:family:FAM-A")[-1]["payload"]
    assert payload["reviewed_sku_ids"] == ["SKU-A"]
    assert payload["claim_approval_changed"] is False
    assert payload["publication_changed"] is False


def test_unmapped_review_records_candidate_without_applying_mapping(review_context):
    root, idx, store = review_context
    detail = unmapped_review_detail(root, idx, store, "UG-1")
    data = {
        "decision": "candidate_supported_not_applied",
        "rationale": "Product identity and every supplier code in the group checked.",
        "review_signature": detail["signature"],
        "reviewed_sku_ids": detail["sku_ids"],
        "products_checked": True,
    }

    saved = validate_family_review(root, idx, store, "unmapped", "UG-1", data, "reviewer", 0)

    assert saved["decision"] == "candidate_supported_not_applied"
    assert saved["canonical_mapping_changed"] is False
    payload = store.history("family-validation:unmapped:UG-1")[-1]["payload"]
    assert payload["reviewed_sku_ids"] == ["SKU-C"]
    assert payload["canonical_mapping_changed"] is False


def test_review_rejects_duplicate_or_incomplete_sku_attestations(review_context):
    root, idx, store = review_context
    detail = family_review_detail(root, idx, store, "FAM-A")
    data = {
        "decision": "confirmed",
        "rationale": "Identity, source state and associated SKU mapping checked.",
        "review_signature": detail["signature"],
        "reviewed_sku_ids": ["SKU-A", "SKU-A"],
        "identity_checked": True,
        "sources_checked": True,
        "sku_mappings_checked": True,
    }

    with pytest.raises(ValueError, match="duplicates"):
        validate_family_review(root, idx, store, "family", "FAM-A", data, "reviewer", 0)
    data["reviewed_sku_ids"] = []
    with pytest.raises(ValueError, match="every SKU"):
        validate_family_review(root, idx, store, "family", "FAM-A", data, "reviewer", 0)


def test_changed_dossier_makes_prior_signature_unusable(review_context):
    root, idx, store = review_context
    detail = family_review_detail(root, idx, store, "FAM-A")
    data = {
        "decision": "confirmed",
        "rationale": "Identity, source state and associated SKU mapping checked.",
        "review_signature": detail["signature"],
        "reviewed_sku_ids": detail["v3_sku_ids"],
        "identity_checked": True,
        "sources_checked": True,
        "sku_mappings_checked": True,
    }
    idx.families["FAM-A"]["name"] = "Family A updated"

    with pytest.raises(ValueError, match="evidence changed"):
        validate_family_review(root, idx, store, "family", "FAM-A", data, "reviewer", 0)


def test_saved_review_becomes_stale_when_dossier_changes(review_context):
    root, idx, store = review_context
    detail = family_review_detail(root, idx, store, "FAM-A")
    data = {
        "decision": "confirmed",
        "rationale": "Identity, source state and associated SKU mapping checked.",
        "review_signature": detail["signature"],
        "reviewed_sku_ids": detail["v3_sku_ids"],
        "identity_checked": True,
        "sources_checked": True,
        "sku_mappings_checked": True,
    }
    validate_family_review(root, idx, store, "family", "FAM-A", data, "reviewer", 0)
    idx.families["FAM-A"]["category"] = "Updated category"

    refreshed = build_review_inventory(root, idx, store)
    family = next(row for row in refreshed["families"] if row["family_id"] == "FAM-A")
    assert family["review"]["status"] == "stale"


def test_stale_triage_cannot_build_review_queue(review_context):
    root, idx, store = review_context
    inventory_path = root / "data/local/staff_release_skus_model_candidate.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["products"][0]["product_name"] = "Changed name"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ReviewInventoryError, match="stale"):
        build_review_inventory(root, idx, store)


def test_family_review_routes_require_local_reader_and_reviewer_roles(monkeypatch):
    class Sessions:
        def session(self, token):
            if token == "reader":
                return {"username": "reader", "roles": ["reader"], "csrf": "token"}
            return None

    monkeypatch.setattr(research_api, "store", lambda: Sessions())
    app = FastAPI()
    app.include_router(research_api.router)
    client = TestClient(app)

    assert client.get("/api/research/family-review").status_code == 401
    client.cookies.set("aurora_research_session", "reader")
    response = client.post("/api/research/family-review/family/FAM-A",
                           json={"data": {}, "expected_version": 0})
    assert response.status_code == 403


def test_local_family_review_api_worklist_detail_and_save(monkeypatch, review_context):
    root, idx, store = review_context
    idx.root = root

    class AuthenticatedStore(FakeStore):
        def session(self, token):
            if token == "reviewer":
                return {"username": "local-reviewer", "roles": ["reader", "reviewer"], "csrf": "csrf"}
            return None

    authenticated_store = AuthenticatedStore()
    monkeypatch.setattr(research_api, "store", lambda: authenticated_store)
    monkeypatch.setattr(research_api, "index", lambda: idx)
    app = FastAPI()
    app.include_router(research_api.router)
    client = TestClient(app)
    client.cookies.set("aurora_research_session", "reviewer")

    worklist = client.get("/api/research/family-review")
    assert worklist.status_code == 200
    assert worklist.json()["family_count"] == 2
    mapped = client.get("/api/research/family-review?lane=mapped")
    assert mapped.status_code == 200
    assert mapped.json()["total"] == 1
    assert mapped.json()["mapped_exception_sku_count"] == 1
    mapped_card = client.get("/api/research/family-review/mapped/G-A")
    assert mapped_card.status_code == 200
    assert mapped_card.json()["sku_ids"] == ["SKU-A"]
    card = client.get("/api/research/family-review/family/FAM-A")
    assert card.status_code == 200
    data = {
        "decision": "confirmed",
        "rationale": "Identity, source state and associated SKU mapping checked.",
        "review_signature": card.json()["signature"],
        "reviewed_sku_ids": card.json()["v3_sku_ids"],
        "identity_checked": True,
        "sources_checked": True,
        "sku_mappings_checked": True,
    }
    saved = client.post("/api/research/family-review/family/FAM-A",
                        headers={"Origin": "http://testserver", "X-Research-CSRF": "csrf"},
                        json={"expected_version": 0, "data": data})

    assert saved.status_code == 200
    assert saved.json()["canonical_mapping_changed"] is False
    refreshed = client.get("/api/research/family-review/family/FAM-A")
    assert refreshed.json()["review"]["status"] == "confirmed"
