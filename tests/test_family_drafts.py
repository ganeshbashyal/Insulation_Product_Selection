"""Private draft packs retain data without model/publication authority."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import family_drafts as drafts


@pytest.fixture
def index(tmp_path):
    source = tmp_path / "knowledge" / "test" / "guide.md"
    source.parent.mkdir(parents=True)
    source.write_text("Lost-original retained guide <img src=x>", encoding="utf-8")
    rows = [{"field": "material", "value": "Glass wool", "origin": "legacy.md",
             "locator": "Material", "status": "retained_not_reviewed"}]
    dossier = {"family_id": "TEST", "dossier_id": "hash", "groups": {"material": rows},
               "provenance_state": "legacy_supplied_original_unavailable", "alternatives": [],
               "retained": {"guide_text": source.read_text(), "research": {"unknown": [1, None]},
                            "commercial_rows": [{"sku_record_id": "EXACT"}]}}
    detail = {"family": {"name": "Synthetic <img src=x>"}, "dossier": dossier,
              "sources": {"documents": [], "source_gaps": ["Missing original"]}}
    return SimpleNamespace(root=tmp_path, families={"TEST": {}}, detail=lambda key: detail,
                           unassigned=[], errors=[], documents={}, skus=[{"family_id": "TEST"}],
                           missing=[], manual_rows=[], triage=[], evidence={}, accuracy={},
                           sources=SimpleNamespace(research={}))


def create(index):
    manifest, packs = drafts.build_preview(index)
    result = drafts.write_batch(index, manifest["preview_id"])
    return manifest, packs, result


def test_preview_no_writes_and_full_retention(index):
    before = drafts.input_inventory(index.root)
    literature = index.root / "output" / "literature" / "generated.md"
    literature.parent.mkdir(parents=True, exist_ok=True)
    literature.write_text("Generated family projection")
    assert drafts.input_inventory(index.root) == before
    manifest, packs = drafts.build_preview(index)
    assert not (index.root / "data").exists()
    assert manifest["family_count"] == 1 and manifest["sku_count"] == 1
    assert packs["TEST"]["dossier"] == index.detail("TEST")["dossier"]
    text = drafts.readable(packs["TEST"])
    assert "Lost-original retained guide <img src=x>" in text
    assert "legacy.md" in text and drafts.WARNING in text
    assert drafts.input_inventory(index.root) == before


def test_write_is_verified_repeatable_not_recursive(index):
    manifest, packs, result = create(index)
    assert result["files"] == 2
    assert drafts.build_preview(index)[0] == manifest
    assert drafts.write_batch(index, manifest["preview_id"])["state"].startswith("existing")
    actual = drafts.inspect_family(index, "TEST")
    assert actual["pack"] == packs["TEST"]
    assert actual["state"].startswith("current")
    assert actual["annotations"]["status"] == {"pending": 1, "failed": 0, "validated": 0}


def test_bad_confirmation_stale_sources_and_corruption(index):
    manifest, _, result = create(index)
    with pytest.raises(ValueError, match="confirmation"):
        drafts.write_batch(index, "wrong")
    source = next((index.root / "knowledge").rglob("*.md"))
    source.write_text("changed")
    assert drafts.inspect_family(index, "TEST")["state"] == "stale"
    stem = manifest["families"]["TEST"]["file"]
    (Path(result["path"]) / (stem + ".json")).write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        drafts.verify_batch(index.root, result["batch"])


def test_lock_and_path_escape_fail_explicitly(index):
    with drafts.writer_lock(index.root):
        with pytest.raises(ValueError, match="active"):
            drafts.write_batch(index, "wrong")
    for value in ("../outside", "a" * 64 + "/x", "A" * 64):
        with pytest.raises(ValueError):
            drafts.batch_path(index.root, value)
    with pytest.raises(ValueError, match="escapes"):
        drafts.private_path(index.root, "..", "..", "..", "outside")


class LocalClient:
    def __init__(self, invalid=False):
        self.calls = []
        self.invalid = invalid

    def request(self, endpoint, payload=None):
        self.calls.append((endpoint, payload))
        if endpoint == "/api/tags":
            return {"models": [{"name": "llama3.1:8b"}]}
        if endpoint == "/api/ps":
            return {"models": []}
        if endpoint == "/api/generate":
            return {}
        items = json.loads(payload["messages"][1]["content"])
        ids = [row["id"] for row in items]
        if self.invalid and not ids[0].startswith("probe"):
            ids = ["invented"]
        return {"message": {"content": json.dumps({"assignments": [
            {"id": key, "group": "material", "issue": "needs_review"} for key in ids]})}}


def test_local_annotation_grounding_limits_cache_unload(index):
    _, _, result = create(index)
    client = LocalClient()
    actual = drafts.annotate(index.root, result["batch"], 1, client=client)
    assert actual["status"]["validated"] == 1 and actual["status"]["pending"] == 0
    assert all(payload["options"]["num_thread"] == 2 for endpoint, payload in client.calls if endpoint == "/api/chat")
    assert len([1 for endpoint, _ in client.calls if endpoint == "/api/generate"]) == 2
    calls = len(client.calls)
    drafts.annotate(index.root, result["batch"], 1, client=client)
    assert len(client.calls) == calls
    family = drafts.inspect_family(index, "TEST")
    assert family["annotations"]["suggestions"][0]["result"]["assignments"][0]["id"] == "material:0"


def test_failed_reply_saved_no_auto_retry(index):
    _, _, result = create(index)
    client = LocalClient(invalid=True)
    with pytest.raises(ValueError, match="no automatic retry"):
        drafts.annotate(index.root, result["batch"], 1, client=client)
    assert drafts.annotation_status(index.root, result["batch"])["status"]["failed"] == 1
    calls = len(client.calls)
    with pytest.raises(ValueError, match="explicit retry"):
        drafts.annotate(index.root, result["batch"], 1, client=client)
    assert len(client.calls) == calls
    client.invalid = False
    assert drafts.annotate(index.root, result["batch"], 1, retry=True, client=client)["status"]["validated"] == 1
    receipt = next(p for p in Path(result["path"]).joinpath("annotations").glob("*.json") if p.name != "probe.json")
    assert json.loads(receipt.read_text())["prior_attempt"]["raw"]


@pytest.mark.parametrize("reply", [
    {"assignments": []},
    {"assignments": [{"id": "material:0", "group": "material", "issue": "approved"}]},
    {"assignments": [{"id": "material:0", "group": "material", "issue": "needs_review", "fact": "invented"}]},
])
def test_model_cannot_introduce_facts_or_approval(reply):
    with pytest.raises(ValueError):
        drafts.validate_annotation(json.dumps(reply), [{"id": "material:0"}])


def test_real_all_family_preview_preserves_every_retained_value():
    from product_research import ResearchIndex
    index = ResearchIndex(Path(__file__).resolve().parents[1])
    manifest, packs = drafts.build_preview(index)
    assert set(packs) == set(index.families)
    ids = []
    for key, pack in packs.items():
        assert pack["dossier"] == index.detail(key)["dossier"]
        ids.extend(row["sku_record_id"] for row in pack["dossier"]["retained"]["commercial_rows"])
    assert sorted(ids) == sorted(row["sku_record_id"] for row in index.skus)
    assert manifest["sku_count"] == len(ids)
