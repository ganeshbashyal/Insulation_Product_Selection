import json
import shutil

import scripts.validate_catalogue as validator


def test_catalogue_and_evidence_are_valid():
    assert validator.validate() == []


def isolated_catalogue(tmp_path):
    for name in ("knowledge", "schemas", "data"):
        shutil.copytree(validator.ROOT / name, tmp_path / name)
    return tmp_path


def test_registry_family_mismatch_is_rejected(tmp_path, monkeypatch):
    root = isolated_catalogue(tmp_path)
    path = root / "knowledge" / "performance_evidence.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["families"].pop()
    path.write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", root)
    assert any("missing evidence records" in issue for issue in validator.validate())


def test_verified_metric_without_standard_is_rejected(tmp_path, monkeypatch):
    root = isolated_catalogue(tmp_path)
    path = root / "knowledge" / "performance_evidence.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    item = evidence["families"][0]["evidence_items"][0]
    item.update({"evidence_status": "verified", "verified_by": "reviewer-1", "verified_at": "2026-09-04T09:00:00Z", "source_locator": "Page 1, performance table", "test_standard": ""})
    path.write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", root)
    assert any("requires a test standard" in issue for issue in validator.validate())
