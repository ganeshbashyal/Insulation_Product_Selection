import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.vault_product_files import build_reconciliation, write_reconciliation


def _csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path):
    root = tmp_path / "repo"
    vault = tmp_path / "product_files"
    cache = tmp_path / "cache"
    (root / "data" / "local").mkdir(parents=True)
    (root / "output" / "literature" / "maker").mkdir(parents=True)
    (root / "output" / "literature" / "maker" / "family.md").write_text(
        "---\nfamily_id: FAMILY_A\n---\n# Family\n", encoding="utf-8"
    )
    (cache / "AuroraKnowledge" / "reports").mkdir(parents=True)
    (cache / "retained").mkdir(parents=True)
    retained = cache / "retained" / "packs.json"
    retained.write_text("{}", encoding="utf-8")

    pdf = vault / "family.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF test fixture")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    cached_pdf = cache / "sources" / "family.pdf"
    cached_pdf.parent.mkdir(parents=True)
    cached_pdf.write_bytes(pdf.read_bytes())

    register = cache / "AuroraKnowledge" / "reports" / "register.json"
    payload = {
        "version": 1,
        "build_id": "fixture-build",
        "rows": [{
            "family_id": "FAMILY_A",
            "path": str(cached_pdf),
            "sha256": digest,
        }],
        "retained_packs": str(retained),
        "retained_packs_hash": hashlib.sha256(retained.read_bytes()).hexdigest(),
    }
    register.write_text(json.dumps(payload), encoding="utf-8")
    (root / "data" / "local" / "tds_register.json").write_text(json.dumps({
        "cache": str(cache),
        "build_id": "fixture-build",
        "outputs": {"json": str(register)},
        "sha256": hashlib.sha256(register.read_bytes()).hexdigest(),
    }), encoding="utf-8")

    _csv(vault / "product_files_manifest.csv", [{
        "Sha256": digest,
        "VaultPath": str(pdf),
        "SourceCount": "2",
    }])
    _csv(vault / "knowledge_validation_final.csv", [{
        "expected_sha256": digest,
        "actual_sha256": digest,
        "hash_ok": "True",
        "status": "readable",
        "page_count": "2",
        "path": str(pdf),
    }])
    _csv(root / "data" / "processed" / "product_catalogue_skus.csv", [{
        "sku_record_id": "SKU-ONE",
        "our_sku": "INT-1",
        "supplier_sku": "SUP-1",
        "product_name": "Product one",
        "validation_status": "REVIEW",
        "family_id": "FAMILY_A",
    }, {
        "sku_record_id": "SKU-TWO",
        "our_sku": "INT-2",
        "supplier_sku": "SUP-2",
        "product_name": "Product two",
        "validation_status": "REVIEW",
        "family_id": "FAMILY_A",
    }])
    return root, vault, pdf, digest


def test_reconciliation_joins_verified_file_to_family_markdown_and_all_skus(tmp_path):
    root, vault, pdf, digest = _fixture(tmp_path)
    report = build_reconciliation(vault, root)

    assert report["summary"]["pdf_count"] == 1
    assert report["summary"]["mapped_family_count"] == 1
    assert report["summary"]["unassigned_pdf_count"] == 0
    assert report["families"][0]["family_id"] == "FAMILY_A"
    assert [sku["sku_record_id"] for sku in report["families"][0]["skus"]] == ["SKU-ONE", "SKU-TWO"]
    assert report["families"][0]["files"][0]["sha256"] == digest
    assert report["families"][0]["files"][0]["vault_path"] == str(pdf)


def test_reconciliation_keeps_unknown_document_unassigned(tmp_path):
    root, vault, _, _ = _fixture(tmp_path)
    register_path = root / "data" / "local" / "tds_register.json"
    pointer = json.loads(register_path.read_text(encoding="utf-8"))
    payload = json.loads(Path(pointer["outputs"]["json"]).read_text(encoding="utf-8"))
    payload["rows"][0]["family_id"] = ""
    output = Path(pointer["outputs"]["json"])
    output.write_text(json.dumps(payload), encoding="utf-8")
    pointer["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    register_path.write_text(json.dumps(pointer), encoding="utf-8")

    report = build_reconciliation(vault, root)
    assert report["summary"]["unassigned_pdf_count"] == 1
    assert len(report["families"]) == 1
    assert report["families"][0]["family_id"] == "FAMILY_A"
    assert report["families"][0]["files"] == []
    assert report["unassigned_files"][0]["filename"] == "family.pdf"


def test_hash_mismatch_is_reported_and_blocks_private_exports(tmp_path):
    root, vault, _, _ = _fixture(tmp_path)
    pdf = vault / "family.pdf"
    pdf.write_bytes(b"changed after validation")
    report = build_reconciliation(vault, root)

    assert report["summary"]["hash_validation_errors"] >= 1
    with pytest.raises(ValueError, match="hash/readability validation"):
        write_reconciliation(report, root / "data" / "local" / "vault_product_files")


def test_export_stays_under_private_data_local_and_links_files_and_skus(tmp_path):
    root, vault, pdf, _ = _fixture(tmp_path)
    report = build_reconciliation(vault, root)
    output = root / "data" / "local" / "vault_product_files"

    written = write_reconciliation(report, output)

    family_page = output / "families" / "FAMILY_A.md"
    text = family_page.read_text(encoding="utf-8")
    assert family_page in written
    assert "SKU-ONE" in text and "SKU-TWO" in text
    assert pdf.as_uri() in text
    assert (output / "index.md").is_file()
    with pytest.raises(ValueError, match="data/local"):
        write_reconciliation(report, tmp_path / "outside")
