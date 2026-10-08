"""Reconcile a local Vault PDF mirror to the frozen source register and catalogue."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_OUTPUT = REPO_ROOT / "data" / "local" / "vault_product_files"
FAMILY_SKU_FIELDS = (
    "sku_record_id",
    "our_sku",
    "supplier_sku",
    "product_name",
    "validation_status",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolved(value: str | Path) -> Path:
    return Path(str(value).removeprefix("\\\\?\\")).resolve()


def _load_register(root: Path) -> list[dict]:
    pointer_path = root / "data" / "local" / "tds_register.json"
    if not pointer_path.is_file():
        raise ValueError(f"Frozen TDS register pointer is missing: {pointer_path}")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    cache = _resolved(pointer["cache"])
    output = _resolved(pointer["outputs"]["json"])
    reports = (cache / "AuroraKnowledge" / "reports").resolve()
    if not output.is_relative_to(reports) or not output.is_file():
        raise ValueError("Frozen TDS register output is missing or outside its managed reports directory")
    if _sha256(output) != pointer.get("sha256"):
        raise ValueError("Frozen TDS register checksum mismatch")

    payload = json.loads(output.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("build_id") != pointer.get("build_id"):
        raise ValueError("Frozen TDS register identity mismatch")

    retained_packs = _resolved(payload["retained_packs"])
    if not retained_packs.is_file() or _sha256(retained_packs) != payload.get("retained_packs_hash"):
        raise ValueError("Frozen TDS register retained-pack checksum mismatch")

    checked: dict[Path, str] = {}
    for row in payload.get("rows", []):
        path_value = row.get("path")
        if not path_value:
            continue
        source = _resolved(path_value)
        if not source.is_relative_to(cache):
            raise ValueError("Frozen TDS source escapes its managed cache")
        if source in checked:
            if checked[source] != row.get("sha256"):
                raise ValueError(f"Frozen TDS register has conflicting hashes for: {source}")
            continue
        checked[source] = row.get("sha256", "")
        if not source.is_file() or _sha256(source) != row.get("sha256"):
            raise ValueError(f"Frozen TDS source is missing or has changed: {source}")
    return payload.get("rows", [])


def _load_family_markdown(root: Path) -> dict[str, Path]:
    documents: dict[str, Path] = {}
    duplicates: set[str] = set()
    for path in sorted((root / "output" / "literature").rglob("*.md")):
        match = re.search(r"(?m)^family_id:\s*([^\s#]+)\s*$", path.read_text(
            encoding="utf-8-sig", errors="replace"))
        if not match:
            continue
        family_id = match.group(1)
        if family_id in documents:
            duplicates.add(family_id)
        documents[family_id] = path
    if duplicates:
        raise ValueError(f"Multiple family Markdown documents found for: {', '.join(sorted(duplicates))}")
    return documents


def build_reconciliation(product_files: Path, root: Path = REPO_ROOT) -> dict:
    """Build a verified, read-only mapping. No source files are modified."""
    root = root.resolve()
    product_files = product_files.resolve()
    manifest_path = product_files / "product_files_manifest.csv"
    validation_path = product_files / "knowledge_validation_final.csv"
    catalogue_path = root / "data" / "processed" / "product_catalogue_skus.csv"
    for path in (manifest_path, validation_path, catalogue_path):
        if not path.is_file():
            raise ValueError(f"Required reconciliation input is missing: {path}")

    manifest = _read_csv(manifest_path)
    validation_rows = _read_csv(validation_path)
    validation_by_hash = {row.get("expected_sha256", ""): row for row in validation_rows}
    register_rows = _load_register(root)
    markdown = _load_family_markdown(root)
    catalogue = _read_csv(catalogue_path)

    sku_by_family: dict[str, list[dict[str, str]]] = defaultdict(list)
    for sku in catalogue:
        sku_by_family[sku.get("family_id", "")].append(sku)

    register_families: dict[str, set[str]] = defaultdict(set)
    for row in register_rows:
        if row.get("sha256") and row.get("family_id"):
            register_families[row["sha256"]].add(row["family_id"])

    files = []
    seen_paths: set[Path] = set()
    validation_errors = []
    for row in manifest:
        sha = row.get("Sha256", "").lower()
        raw_path = Path(row.get("VaultPath", ""))
        path = raw_path.resolve() if raw_path.is_absolute() else (product_files / raw_path).resolve()
        if not path.is_relative_to(product_files):
            raise ValueError(f"Manifest path escapes the selected product-files folder: {raw_path}")
        if path in seen_paths:
            raise ValueError(f"Duplicate Vault path in manifest: {path}")
        seen_paths.add(path)
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError(f"Invalid SHA-256 in product-files manifest: {raw_path}")
        if not path.is_file():
            raise ValueError(f"Manifest PDF is missing: {path}")
        actual_sha = _sha256(path)
        if actual_sha != sha:
            validation_errors.append(f"Manifest hash mismatch: {path.name}")
        validation = validation_by_hash.get(sha)
        if not validation:
            validation_errors.append(f"No PDF validation record for: {path.name}")
        elif (validation.get("hash_ok", "").casefold() != "true"
              or validation.get("actual_sha256", "").lower() != actual_sha
              or validation.get("status", "").casefold() != "readable"):
            validation_errors.append(f"PDF validation is stale or not readable: {path.name}")
        if validation and validation.get("path"):
            validation_path_value = Path(validation["path"]).resolve()
            if validation_path_value != path:
                validation_errors.append(f"Validation path does not match manifest: {path.name}")

        family_ids = sorted(register_families.get(sha, set()))
        files.append({
            "sha256": sha,
            "vault_path": str(path),
            "filename": path.name,
            "bytes": path.stat().st_size,
            "source_count": int(row.get("SourceCount") or 0),
            "family_ids": family_ids,
            "validation_status": validation.get("status", "missing") if validation else "missing",
            "page_count": int(validation.get("page_count") or 0) if validation else 0,
        })

    unknown_families = sorted({
        family_id
        for file in files
        for family_id in file["family_ids"]
        if family_id not in markdown
    })
    known_family_ids = sorted({
        family_id
        for file in files
        for family_id in file["family_ids"]
        if family_id in markdown
    })

    family_page_ids = sorted(set(known_family_ids) | {
        family_id for family_id, skus in sku_by_family.items()
        if skus and family_id in markdown
    })
    families = []
    for family_id in family_page_ids:
        matched_files = [file for file in files if family_id in file["family_ids"]]
        families.append({
            "family_id": family_id,
            "markdown_path": str(markdown[family_id].relative_to(root)),
            "sku_count": len(sku_by_family.get(family_id, [])),
            "skus": [{field: sku.get(field, "") for field in FAMILY_SKU_FIELDS}
                     for sku in sku_by_family.get(family_id, [])],
            "files": matched_files,
        })

    unassigned_files = [file for file in files if not file["family_ids"]]
    missing_sku_markdown = sorted(
        family_id for family_id, skus in sku_by_family.items()
        if skus and family_id not in markdown
    )
    duplicated_catalogue_skus: dict[str, list[str]] = defaultdict(list)
    for family_id, skus in sku_by_family.items():
        seen: set[str] = set()
        for sku in skus:
            sku_id = sku.get("sku_record_id", "")
            if not sku_id or sku_id in seen:
                duplicated_catalogue_skus[family_id].append(sku_id or "(missing sku_record_id)")
            seen.add(sku_id)

    return {
        "version": 1,
        "repository_root": str(root),
        "product_files_root": str(product_files),
        "inputs": {
            "manifest": str(manifest_path),
            "validation_report": str(validation_path),
            "frozen_register_build_id": json.loads(
                (root / "data" / "local" / "tds_register.json").read_text(encoding="utf-8")
            )["build_id"],
        },
        "summary": {
            "pdf_count": len(files),
            "unique_hash_count": len({file["sha256"] for file in files}),
            "hash_validation_errors": len(validation_errors),
            "catalogue_sku_rows": len(catalogue),
            "catalogue_families": len(sku_by_family),
            "family_markdown_count": len(markdown),
            "mapped_family_count": len(known_family_ids),
            "family_page_count": len(families),
            "unmapped_register_family_count": len(unknown_families),
            "unassigned_pdf_count": len(unassigned_files),
            "families_with_skus_missing_markdown": len(missing_sku_markdown),
            "catalogue_duplicate_record_id_families": len(duplicated_catalogue_skus),
        },
        "validation_errors": validation_errors,
        "unmapped_register_families": unknown_families,
        "families_missing_markdown": missing_sku_markdown,
        "catalogue_duplicate_record_ids": dict(duplicated_catalogue_skus),
        "files": files,
        "families": families,
        "unassigned_files": unassigned_files,
    }


def _md_cell(value: str) -> str:
    return str(value).replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def _file_uri(path: str) -> str:
    return Path(path).resolve().as_uri().replace("(", "%28").replace(")", "%29")


def _render_family_markdown(family: dict, root: Path) -> str:
    md = Path(family["markdown_path"])
    canonical = (root / md).resolve().as_uri()
    lines = [
        f"# {family['family_id']}",
        "",
        f"Canonical product-family Markdown: [{md.as_posix()}]({canonical})",
        "",
        "Local review aid generated from byte-hash links. Source-to-family association is not approval of any claim.",
        "",
        f"## Catalogue SKUs ({family['sku_count']} source rows)",
        "",
        "| SKU record | Internal SKU | Supplier SKU | Product | Validation status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for sku in family["skus"]:
        lines.append("| " + " | ".join(_md_cell(sku[field]) for field in FAMILY_SKU_FIELDS) + " |")
    if not family["skus"]:
        lines.append("| No catalogue SKU rows for this family | | | | |")

    lines.extend([
        "",
        f"## Verified local PDF files ({len(family['files'])})",
        "",
        "| File | SHA-256 | Pages | Validation |",
        "| --- | --- | ---: | --- |",
    ])
    for file in family["files"]:
        lines.append(
            f"| [{_md_cell(file['filename'])}]({_file_uri(file['vault_path'])}) "
            f"| `{file['sha256']}` | {file['page_count']} | {_md_cell(file['validation_status'])} |"
        )
    return "\n".join(lines) + "\n"


def _index_markdown(report: dict, root: Path = REPO_ROOT, output: Path = LOCAL_OUTPUT) -> str:
    summary = report["summary"]
    lines = [
        "# Local product-file family links",
        "",
        "Private, machine-local report. It is generated from the selected Vault manifest, its PDF validation report, the frozen TDS register, and the in-repository SKU catalogue.",
        "",
        f"- PDFs: {summary['pdf_count']} (unique hashes: {summary['unique_hash_count']})",
        f"- Catalogue rows: {summary['catalogue_sku_rows']} across {summary['catalogue_families']} families",
        f"- Families with linked PDFs: {summary['mapped_family_count']}",
        f"- PDFs without a register family: {summary['unassigned_pdf_count']}",
        f"- Hash/readability validation errors: {summary['hash_validation_errors']}",
        "",
        "Register family links are source associations only; they do not confirm document currency, SKU applicability, or claim approval.",
        "",
        "## Family pages",
        "",
        "| Family ID | Catalogue SKUs | Local PDFs | Product-family Markdown |",
        "| --- | ---: | ---: | --- |",
    ]
    for family in report["families"]:
        overlay = f"families/{family['family_id']}.md"
        canonical = Path(family["markdown_path"]).as_posix()
        canonical_link = Path(os.path.relpath(root / canonical, output)).as_posix()
        lines.append(
            f"| `{family['family_id']}` | {family['sku_count']} | {len(family['files'])} "
            f"| [{canonical}]({quote(canonical_link, safe='/._-')}) · "
            f"[local family page]({quote(overlay, safe='/._-')}) |"
        )
    lines.extend(["", "## Files without a family association", ""])
    if report["unassigned_files"]:
        lines.extend([
            "| File | SHA-256 | Validation |",
            "| --- | --- | --- |",
        ])
        for file in report["unassigned_files"]:
            lines.append(
                f"| [{_md_cell(file['filename'])}]({_file_uri(file['vault_path'])}) "
                f"| `{file['sha256']}` | {_md_cell(file['validation_status'])} |"
            )
    else:
        lines.append("None.")
    if report["validation_errors"]:
        lines.extend(["", "## Validation errors", ""])
        lines.extend(f"- {_md_cell(error)}" for error in report["validation_errors"])
    if report["unmapped_register_families"]:
        lines.extend(["", "## Register families without a product Markdown", ""])
        lines.extend(f"- `{_md_cell(family_id)}`" for family_id in report["unmapped_register_families"])
    if report["families_missing_markdown"]:
        lines.extend(["", "## Catalogue families without a product Markdown", ""])
        lines.extend(f"- `{_md_cell(family_id)}`" for family_id in report["families_missing_markdown"])
    return "\n".join(lines) + "\n"


def write_reconciliation(report: dict, output: Path = LOCAL_OUTPUT) -> list[Path]:
    """Write only generated private review aids under data/local."""
    output = output.resolve()
    root = _resolved(report["repository_root"])
    private_root = (root / "data" / "local").resolve()
    if not output.is_relative_to(private_root):
        raise ValueError("Local reconciliation output must stay under this repository's data/local directory")
    if report["validation_errors"]:
        raise ValueError("Refusing to generate family links while PDF hash/readability validation has errors")

    output.mkdir(parents=True, exist_ok=True)
    families_dir = output / "families"
    families_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for family in report["families"]:
        destination = families_dir / f"{family['family_id']}.md"
        temp = destination.with_suffix(".md.tmp")
        temp.write_text(_render_family_markdown(family, root), encoding="utf-8")
        temp.replace(destination)
        written.append(destination)
    index = output / "index.md"
    temp_index = index.with_suffix(".md.tmp")
    temp_index.write_text(_index_markdown(report, root, output), encoding="utf-8")
    temp_index.replace(index)
    json_path = output / "reconciliation.json"
    temp_json = json_path.with_suffix(".json.tmp")
    temp_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    temp_json.replace(json_path)
    written.extend((index, json_path))
    return written
