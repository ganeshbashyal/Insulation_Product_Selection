"""Shared local family loading and lossless dossier assembly; never approves data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_families(root: Path) -> dict[str, dict]:
    families = {}
    for path in sorted(root.glob("knowledge/*/families.json")):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Family file escapes checkout")
        for row in read_json(path)["families"]:
            key = row["family_id"]
            if key in families:
                raise ValueError(f"Duplicate family identity: {key}")
            families[key] = {**row, "manufacturer": row.get("manufacturer", path.parent.name.title()),
                             "record_path": path.relative_to(root).as_posix()}
    return families


def load_research(root: Path) -> dict[str, dict]:
    records = {}
    for path in sorted(root.glob("knowledge/*/research/*.json")):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Research file escapes checkout")
        row = read_json(path)
        key = row["family_id"]
        if key in records:
            raise ValueError(f"Duplicate research family identity: {key}")
        records[key] = {**row, "_path": path.relative_to(root).as_posix()}
    return records


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        return {}
    return {key.strip(): value.strip() for key, value in
            (line.split(":", 1) for line in match[1].splitlines() if ":" in line and not line.startswith(" "))}


def dossier(detail: dict) -> dict:
    """Group occurrences without last-write-wins or interpreting prose as proof."""
    family = detail["family"]
    research = detail.get("research", {})
    spec = research.get("spec") or {}
    has_source = any(row["exists"] for row in detail["sources"]["documents"])
    groups = {key: [] for key in ("identity", "applications", "material", "variants",
              "performance", "installation", "limitations", "safety", "warranty",
              "references", "retained_sections", "unparsed")}

    def add(group, field, value, origin, locator, status="retained_not_reviewed"):
        if value is None or value == "" or value == [] or value == {}:
            return
        groups[group].append({"field": field, "value": value, "origin": origin,
                              "locator": locator, "status": status})

    origin = family.get("record_path", "canonical family metadata")
    for field in ("family_id", "name", "manufacturer", "category", "primary_function", "confidence"):
        add("identity", field, family.get(field), origin, field, "canonical_metadata_not_claim_approval")
    for field in ("applications", "keywords", "questions", "human_gates"):
        add("applications", field, family.get(field), origin, field)
    research_origin = detail["sources"].get("research_path") or "retained research"
    known = {"description": "identity", "applications": "applications", "features": "material",
             "range": "variants", "range_headers": "variants", "technical": "performance",
             "fire": "performance", "install": "installation", "clearances": "installation",
             "limitations": "limitations", "selection_checklist": "limitations",
             "warranty": "warranty", "compliance": "performance",
             "sustainability": "material", "accessories": "applications", "accessories_upsell": "applications",
             "material": "material", "installation": "installation", "safety": "safety",
             "references": "references"}
    for field, value in spec.items():
        add(known.get(field, "unparsed"), field, value, research_origin, "spec." + field)
    add("applications", "retrieval", research.get("retrieval"), research_origin, "retrieval",
        "retrieval_signal_not_product_fact")
    for field, value in research.items():
        if field not in {"spec", "retrieval"}:
            add("unparsed", field, value, research_origin, field)
    for field in ("source_url", "datasheet_url", "legacy_source_url"):
        add("references", field, family.get(field), origin, field)
    text = detail.get("guide_text") or ""
    guide = detail["sources"].get("guide") or "retained guide"
    add("identity", "frontmatter", frontmatter(text), guide, "frontmatter")
    for match in re.finditer(r"(?ms)^(#{1,6}) (.+?)\r?\n(.*?)(?=^#{1,6} |\Z)", text):
        add("retained_sections", match[2], match[3], guide, match[2],
            "historical_heading_not_current_approval")
    for doc in detail["sources"]["documents"]:
        add("references", "document", doc, doc["path"], "source association")
        for candidate in doc.get("candidate_fields", []):
            group = {"dimension": "variants", "application": "applications", "standard": "performance",
                     "limitation": "limitations", "reference": "references"}.get(candidate["kind"], candidate["kind"])
            add(group if group in groups else "unparsed", candidate["field"], candidate, doc["path"],
                f"page {candidate['page']}", "pending_human_review")
    occurrences = {}
    for group, rows in groups.items():
        for row in rows:
            occurrences.setdefault((group, row["field"]), []).append(row)
    alternatives = [{"group": group, "field": field, "occurrences": rows,
                     "resolution": "review_required_no_automatic_merge"}
                    for (group, field), rows in occurrences.items()
                    if len({json.dumps(row["value"], sort_keys=True) for row in rows}) > 1]
    body = {"schema_version": 1, "family_id": family["family_id"], "groups": groups,
            "alternatives": alternatives,
            "provenance_state": "original_available_not_approval" if has_source
                                else "legacy_supplied_original_unavailable",
            "retained": {"family": family, "research": research, "guide_text": text,
                         "commercial_rows": detail["skus"],
                         "baseline_evidence": detail["evidence"],
                         "derived_literature": detail["derived_literature"],
                         "retrieval_cards": detail["retrieval_cards"],
                         "manual_requests": detail.get("manual_requests", []),
                         "manual_workbook_rows": detail.get("manual_workbook_rows", []),
                         "evidence_triage": detail.get("evidence_triage", []),
                         "accuracy_audit": detail.get("accuracy_audit"),
                         "source_workbooks": detail.get("source_workbooks", [])},
            "rule": "One dossier, multiple retained occurrences. Common origin/copies are not independent evidence. Missing originals do not delete knowledge."}
    body["dossier_id"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return body
