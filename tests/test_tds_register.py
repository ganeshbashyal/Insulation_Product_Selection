import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tds_build import checksum
from tds_cache_inventory import inventory
from tds_register import cached_rows, compiled_sources, export_register, render_family, source_rows


def file_row(path):
    return {"path": str(path.resolve()), "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_inventory_preserves_duplicate_locations_and_skips_generated(tmp_path):
    first = tmp_path / "TDS" / "a.pdf"
    first.parent.mkdir()
    first.write_bytes(b"same")
    second = tmp_path / "AuroraKnowledge" / "originals" / "b.pdf"
    second.parent.mkdir(parents=True)
    second.write_bytes(b"same")
    generated = tmp_path / "AuroraKnowledge" / "builds" / "old.pdf"
    generated.parent.mkdir()
    generated.write_bytes(b"generated")
    ordinary = tmp_path / "TDS" / "reports" / "source.docx"
    ordinary.parent.mkdir()
    ordinary.write_bytes(b"ordinary")
    rows = inventory(tmp_path)
    assert len(rows) == 3
    assert rows[0]["sha256"] == hashlib.sha256(b"same").hexdigest()
    assert len({row["sha256"] for row in rows}) == 2


def test_source_rows_cover_supplied_conflicts_files_and_empty_families(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"same")
    f = file_row(path)
    (tmp_path / "downloads").mkdir()
    url = "https://example.test/a.pdf"
    (tmp_path / "downloads" / (checksum(url)[:24] + ".json")).write_text(json.dumps({
        "status": "archived", "sha256": f["sha256"], "final_url": url,
    }))
    supplied = {"family_id": "A", "url": url, "display_url": url, "holds": [],
                "sheet": "Sheet3", "row": 2}
    held = {**supplied, "family_id": "B", "holds": ["display_hyperlink_conflict"],
            "display_url": "https://example.test/conflict.pdf"}
    build = SimpleNamespace(job=lambda _: (tmp_path, {"rows": [supplied, held]}),
                            sources=lambda _: {f["sha256"]: {"families": ["A"]}})
    rows = source_rows(build, "build", SimpleNamespace(families={"A": {}, "B": {}, "C": {}}), [f])
    assert any(r["family_id"] == "A" and r["path"] == f["path"] and r["url"] == url for r in rows)
    assert any(r["family_id"] == "B" and r["status"] == "held" and not r["path"] for r in rows)
    assert any(r["family_id"] == "C" and r["status"] == "no_source" for r in rows)


def test_markdown_and_csv_show_paths_and_neutralise_formulas(tmp_path):
    path = tmp_path / "a (copy).pdf"
    path.write_bytes(b"test")
    row = cached_rows({file_row(path)["sha256"]: {"families": ["A"]}}, [file_row(path)])[0]
    row.update(url="https://example.test/a.pdf", provenance="=danger|<b>\n")
    payload = {"families": ["A"], "rows": [row], "warning": "Private"}
    outputs = export_register(tmp_path / "reports", payload)
    text = Path(outputs["md"]).read_text()
    assert str(path) in text and path.name in text and "https://example.test/a.pdf" in text
    assert "%28copy%29" in text
    assert "&lt;b&gt;" in text and "&#124;" in text
    with Path(outputs["csv"]).open(encoding="utf-8-sig", newline="") as stream:
        assert next(csv.DictReader(stream))["provenance"].startswith("'=danger")


def test_compiled_pointer_absence_and_tamper(tmp_path):
    assert compiled_sources(tmp_path, "A")["state"] == "not_compiled"
    cache = tmp_path / "cache"
    report = cache / "AuroraKnowledge" / "reports" / "register.json"
    report.parent.mkdir(parents=True)
    report.write_text("{}")
    pointer = tmp_path / "data" / "local" / "tds_register.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"version": 1, "cache": str(cache),
                                  "outputs": {"json": str(report)}, "sha256": "wrong"}))
    with pytest.raises(ValueError, match="hash mismatch"):
        compiled_sources(tmp_path, "A")


def test_known_archive_without_family_is_retained_unassigned(tmp_path):
    source = tmp_path / "unassigned.pdf"
    source.write_bytes(b"retained")
    row = file_row(source)
    rows = cached_rows({row["sha256"]: {"families": []}}, [row])
    assert len(rows) == 1 and rows[0]["status"] == "unassigned"
    assert rows[0]["path"] == str(source)


def test_private_bot_brief_receives_provenance_without_approval(monkeypatch):
    import agent_core
    from sales_brief import SalesBriefBuilder
    import tds_register

    calls = []
    def sources(root, family_id):
        calls.append(family_id)
        return {"state": "compiled", "collection": "frozen",
                "sources": [{"filename": "retained.pdf"}], "approval": "not_granted"}
    monkeypatch.setattr(tds_register, "compiled_sources", sources)
    builder = SalesBriefBuilder(agent_core.FAMILIES)
    assert not builder.release
    result = builder.build({"problem": "retrofit thermal insulation behind a brick wall with plasterboard",
                            "application": "wall", "priority": "thermal"})
    assert result["candidates"] and calls
    assert result["approval"] is None
    for candidate in result["candidates"]:
        assert candidate["evidence"]["compiled_sources"]["collection"] == "frozen"
        assert candidate["disposition"] == "HOLD"


def test_private_compiled_source_detects_changed_file(tmp_path):
    cache = tmp_path / "cache"
    source = cache / "a.pdf"
    cache.mkdir()
    source.write_bytes(b"original")
    row = cached_rows({file_row(source)["sha256"]: {"families": ["A"]}}, [file_row(source)])[0]
    packs = cache / "current.json"
    packs.write_text("{}")
    payload = {"version": 1, "build_id": "B", "rows": [row], "documents": {},
               "retained_packs": str(packs), "retained_packs_hash": hashlib.sha256(b"{}").hexdigest(),
               "warning": "Unapproved"}
    report = cache / "AuroraKnowledge" / "reports" / "register.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps(payload))
    pointer = tmp_path / "data" / "local" / "tds_register.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"version": 1, "cache": str(cache), "build_id": "B",
                                  "outputs": {"json": str(report), "md": "register.md"},
                                  "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}))
    assert compiled_sources(tmp_path, "A")["state"] == "compiled"
    source.write_bytes(b"changed")
    result = compiled_sources(tmp_path, "A")
    assert result["state"] == "stale" and not result["sources"][0]["file_current"]


def test_cached_primary_availability_is_not_falsely_missing(tmp_path, monkeypatch):
    from local_source_review import SourceReview
    import tds_register

    monkeypatch.setattr(tds_register, "compiled_sources", lambda root, key: {
        "state": "compiled", "collection": "frozen",
        "sources": [{"file_current": True}], "documents": [],
        "approval": "not_granted",
    })
    review = SourceReview()
    monkeypatch.setattr(review, "documents", lambda key: [])
    result = review.family("ACOUSTICA_ACCESSORY", include_compiled=True)
    assert not any("No family-linked local primary" in gap for gap in result["source_gaps"])
    assert result["review_status"] == "pending_human_review"
    assert any("absence is not proof" in gap for gap in result["source_gaps"])
    assert "compiled_sources" not in review.family("ACOUSTICA_ACCESSORY")
