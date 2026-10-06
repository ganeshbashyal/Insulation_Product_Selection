"""Source-bound local worklists for methodical family and SKU review."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from research_store import canonical


INVENTORY_PATH = Path("data/local/staff_release_skus_model_candidate.json")
TRIAGE_PATH = Path("data/local/family_data_gathering/v3_sku_mapping_triage.json")
FAMILY_REVIEW_PREFIX = "family-validation:family:"
MAPPED_REVIEW_PREFIX = "family-validation:mapped:"
UNMAPPED_REVIEW_PREFIX = "family-validation:unmapped:"

PRODUCT_FIELDS = (
    "sku", "product_name", "manufacturer", "category", "material_type",
    "spec_material_type", "product_use", "spec_family_name", "spec_id",
    "source_row", "family_codes", "migration_statuses",
    "migration_code_conflict", "our_sku", "family_id", "candidate_family_id",
    "family_mapping_status", "family_mapping_group", "deterministic_tier",
    "mpn", "manufacturer_product_code", "supplier_product_key",
)


class ReviewInventoryError(ValueError):
    """The local candidate inventory cannot safely support a review queue."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewInventoryError(f"Cannot read local review input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewInventoryError(f"Local review input is not a JSON object: {path}")
    return value


def _display_name(value: str) -> str:
    """Hide likely appended price-like decimals while preserving dimensions and category numbers."""
    return re.sub(r"\s+(?:\$\s*)?\d[\d,]*\.\d{2}\s*$", "", value or "").rstrip()


def _safe_product(row: dict) -> dict:
    return {key: _display_name(row.get(key, "")) if key == "product_name" else row.get(key)
            for key in PRODUCT_FIELDS if key in row}


def _without_price_fields(value):
    if isinstance(value, dict):
        return {key: _without_price_fields(item) for key, item in value.items()
                if not any(token in str(key).casefold() for token in ("price", "cost", "currency"))}
    if isinstance(value, list):
        return [_without_price_fields(item) for item in value]
    return value


def _within_root(root: Path, relative: str) -> Path | None:
    value = Path(str(relative).replace("\\", "/"))
    candidate = (value if value.is_absolute() else root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _local_file_hash(root: Path, relative: str | None) -> str | None:
    if not relative:
        return None
    path = _within_root(root, relative)
    if path is None or not path.is_file():
        return None
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _load_inputs(root: Path) -> tuple[dict, dict, str, str]:
    inventory_path = root / INVENTORY_PATH
    triage_path = root / TRIAGE_PATH
    inventory = _read_json(inventory_path)
    triage = _read_json(triage_path)
    inventory_file_hash = _sha256_bytes(inventory_path.read_bytes())
    if inventory.get("price_values_included") is not False or triage.get("price_values_included") is not False:
        raise ReviewInventoryError("Price-redaction invariant is missing or failed")
    source_hash = inventory.get("source_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ReviewInventoryError("Candidate inventory has no valid source workbook SHA-256")
    if triage.get("source_sha256") != source_hash:
        raise ReviewInventoryError("SKU triage and candidate inventory use different source workbooks")
    if triage.get("inventory_sha256") != inventory_file_hash:
        raise ReviewInventoryError("SKU triage is stale for the current candidate inventory")
    products = inventory.get("products")
    if not isinstance(products, list):
        raise ReviewInventoryError("Candidate inventory has no product rows")
    active = [row for row in products if isinstance(row, dict) and row.get("active") is True]
    if len(active) != inventory.get("active_product_master_skus"):
        raise ReviewInventoryError("Active product count does not match the inventory manifest")
    skus = [row.get("sku") for row in active]
    if any(not isinstance(sku, str) or not sku for sku in skus) or len(set(skus)) != len(skus):
        raise ReviewInventoryError("Active product rows contain missing or duplicate SKU identifiers")
    for row in active:
        if row.get("price_values_included") is not False:
            raise ReviewInventoryError("An active product row violates the price-redaction invariant")
    return inventory, triage, inventory_file_hash, source_hash


def _document_fingerprints(root: Path, detail: dict) -> list[dict]:
    result = []
    for document in detail.get("sources", {}).get("documents", []):
        path = document.get("path", "")
        expected = document.get("sha256")
        current = _local_file_hash(root, path)
        result.append({
            "path": path,
            "sha256": expected,
            "exists": bool(document.get("exists")),
            "current_sha256": current,
            "hash_matches": current == expected if current and expected else None,
            "extraction_status": document.get("extraction", {}).get("status", "unknown"),
            "manifest_hash_matches": document.get("manifest_hash_matches"),
        })
    return result


def _review_state(store, target: str, signature: str) -> dict:
    revisions = [row for row in store.history(target)
                 if row["kind"] == "family_validation_review"]
    if not revisions:
        return {"status": "pending", "revision": 0, "decision": None, "reviewer": None}
    latest = revisions[-1]
    payload = latest["payload"]
    stale = payload.get("review_signature") != signature
    return {
        "status": "stale" if stale else payload.get("decision", "pending"),
        "revision": latest["id"],
        "decision": payload.get("decision"),
        "reviewer": latest["actor"],
        "occurred": latest["occurred"],
        "rationale": payload.get("rationale", ""),
    }


def _risk_tier(reasons: list[str]) -> str:
    if any(reason.startswith(("source_", "identity_", "extraction_")) for reason in reasons):
        return "high"
    if reasons:
        return "review"
    return "routine"


def build_review_inventory(root: Path, idx, store) -> dict:
    """Build a read-only, hash-bound family plus unmapped-SKU review queue."""
    root = root.resolve()
    inventory, triage, inventory_file_hash, source_hash = _load_inputs(root)
    family_ids = set(idx.families)
    active_products = [row for row in inventory["products"] if row.get("active") is True]
    for row in active_products:
        for family_id in (row.get("family_id"), row.get("candidate_family_id")):
            if family_id is not None and (not isinstance(family_id, str) or family_id not in family_ids):
                raise ReviewInventoryError(
                    f"Active SKU {row['sku']} refers to a family outside the current family index"
                )
    audit_by_group = {row["group_id"]: row for row in triage.get("mapped_group_audit", [])
                      if isinstance(row, dict) and isinstance(row.get("group_id"), str)}
    priority_by_group = {row["group_id"]: row for row in triage.get("priority_review_queue", [])
                         if isinstance(row, dict) and isinstance(row.get("group_id"), str)}
    products_by_family: dict[str, list[dict]] = defaultdict(list)
    for row in active_products:
        safe = _safe_product(row)
        associations = [(row.get("family_id"), "current")]
        if row.get("candidate_family_id") != row.get("family_id"):
            associations.append((row.get("candidate_family_id"), "candidate"))
        for family_id, field in associations:
            if family_id in family_ids:
                scoped = {**safe, "association": field}
                group_id = row.get("family_mapping_group")
                audit = audit_by_group.get(group_id, {})
                priority = priority_by_group.get(group_id, {})
                sku_audit = next((item for item in audit.get("product_identity_review", {}).get("products", [])
                                  if item.get("sku") == row.get("sku")), {})
                scoped["mapping_flags"] = list(audit.get("product_identity_review", {}).get("issues", []))
                scoped["alternate_family_match"] = sku_audit.get("best_distinct_alternate_family_match")
                scoped["priority_group"] = bool(priority)
                products_by_family[family_id].append(scoped)

    families = []
    for family_id, family in idx.families.items():
        detail = idx.detail(family_id)
        rows = products_by_family.get(family_id, [])
        docs = _document_fingerprints(root, detail)
        source_gaps = detail.get("sources", {}).get("source_gaps", [])
        source_reasons = []
        if not docs or any(not doc["exists"] for doc in docs):
            source_reasons.append("source_missing_or_unlinked")
        if any(doc["exists"] and (not doc["sha256"] or not doc["current_sha256"]) for doc in docs):
            source_reasons.append("source_hash_unavailable")
        if any(doc["hash_matches"] is False for doc in docs):
            source_reasons.append("source_hash_mismatch")
        if any(doc["extraction_status"] not in {"text_extracted", "not_applicable"} for doc in docs):
            source_reasons.append("extraction_needs_review")
        if any(reason in " ".join(source_gaps).casefold()
               for reason in ("identity", "mismatch", "held")):
            source_reasons.append("identity_or_source_hold")
        mapping_reasons = sorted({flag for row in rows for flag in row["mapping_flags"]})
        mapping_reasons.extend("alternate_family_title_match" for row in rows if row["alternate_family_match"])
        reasons = list(dict.fromkeys(source_reasons + mapping_reasons))
        guide_text = detail.get("guide_text") or ""
        research_path = detail.get("sources", {}).get("research_path")
        guide_path = detail.get("sources", {}).get("guide")
        signature_payload = {
            "workbook_sha256": source_hash,
            "family": family,
            "research": detail.get("research", {}),
            "guide_sha256": _local_file_hash(root, guide_path),
            "guide_text_sha256": _sha256_bytes(guide_text.encode("utf-8")) if guide_text else None,
            "research_sha256": _local_file_hash(root, research_path),
            "documents": docs,
            "v3_products": rows,
        }
        signature = _sha256_bytes(canonical(signature_payload).encode("utf-8"))
        target = FAMILY_REVIEW_PREFIX + family_id
        families.append({
            "family_id": family_id,
            "workbook_sha256": source_hash,
            "name": family.get("name", family_id),
            "manufacturer": family.get("manufacturer", ""),
            "category": family.get("category", ""),
            "risk_tier": _risk_tier(reasons),
            "review_reasons": reasons,
            "sku_count": len(rows),
            "sku_ids": sorted({row["sku"] for row in rows}),
            "source_gap_count": len(source_gaps),
            "source_document_count": len(docs),
            "signature": signature,
            "review": _review_state(store, target, signature),
        })
    families.sort(key=lambda row: ({"high": 0, "review": 1, "routine": 2}[row["risk_tier"]],
                                   0 if row["review"]["status"] in {"pending", "stale"} else 1,
                                   row["manufacturer"].casefold(), row["name"].casefold(), row["family_id"]))

    mapped_exceptions = []
    seen_mapped_group_ids: set[str] = set()
    seen_mapped_skus: set[str] = set()
    for priority in triage.get("priority_review_queue", []):
        if not isinstance(priority, dict) or not isinstance(priority.get("group_id"), str):
            continue
        group_id = priority["group_id"]
        if group_id in seen_mapped_group_ids:
            raise ReviewInventoryError("Mapped exception queue repeats a group identifier")
        seen_mapped_group_ids.add(group_id)
        family_id = priority.get("current_family_id")
        if not isinstance(family_id, str) or family_id not in family_ids:
            raise ReviewInventoryError(f"Mapped exception group {group_id} has no current indexed family")
        products = [row for row in active_products if row.get("family_mapping_group") == group_id]
        if len(products) != priority.get("sku_count") or not products:
            raise ReviewInventoryError(f"Mapped exception group {group_id} does not match its active SKU count")
        product_skus = {row["sku"] for row in products}
        if seen_mapped_skus.intersection(product_skus):
            raise ReviewInventoryError("Mapped exception queue repeats an active SKU identifier")
        seen_mapped_skus.update(product_skus)
        if any(family_id not in {row.get("family_id"), row.get("candidate_family_id")} for row in products):
            raise ReviewInventoryError(f"Mapped exception group {group_id} contains an unrelated family association")
        audit = audit_by_group.get(group_id)
        if not isinstance(audit, dict):
            raise ReviewInventoryError(f"Mapped exception group {group_id} has no matching identity audit")

        safe_priority = _without_price_fields({
            key: priority.get(key) for key in (
                "group_id", "manufacturer", "sku_count", "current_family_id",
                "current_family_name", "mapping_status", "review_reasons",
                "alternate_family_matches", "form_conflicts", "mismatched_name_examples",
            )
        })
        for example in safe_priority.get("mismatched_name_examples", []) or []:
            if isinstance(example, dict) and "product_name" in example:
                example["product_name"] = _display_name(example["product_name"])
        family_detail = idx.detail(family_id)
        documents = _document_fingerprints(root, family_detail)
        scoped_products = []
        audited_products = {
            row.get("sku"): row for row in audit.get("product_identity_review", {}).get("products", [])
            if isinstance(row, dict)
        }
        for product in products:
            scoped = _safe_product(product)
            sku_audit = audited_products.get(product["sku"], {})
            scoped.update({
                "association": "current" if product.get("family_id") == family_id else "candidate",
                "mapping_flags": audit.get("product_identity_review", {}).get("issues", []),
                "alternate_family_match": sku_audit.get("best_distinct_alternate_family_match"),
            })
            scoped_products.append(scoped)
        scoped_products.sort(key=lambda row: row["sku"])
        family_context = _without_price_fields({
            "family": family_detail.get("family", {}),
            "research": family_detail.get("research", {}),
            "dossier": family_detail.get("dossier", {}),
        })
        signature_payload = {
            "workbook_sha256": source_hash,
            "priority": safe_priority,
            "audit": _without_price_fields(audit),
            "family_context": family_context,
            "guide_sha256": _local_file_hash(root, family_detail.get("sources", {}).get("guide")),
            "research_sha256": _local_file_hash(root, family_detail.get("sources", {}).get("research_path")),
            "documents": documents,
            "v3_products": scoped_products,
        }
        signature = _sha256_bytes(canonical(signature_payload).encode("utf-8"))
        target = MAPPED_REVIEW_PREFIX + group_id
        mapped_exceptions.append({
            **safe_priority,
            "family_id": family_id,
            "family_name": safe_priority.get("current_family_name") or family_id,
            "sku_ids": [row["sku"] for row in scoped_products],
            "signature": signature,
            "review": _review_state(store, target, signature),
        })
    mapped_exceptions.sort(key=lambda row: (
        row["review"]["status"] not in {"pending", "stale"},
        row.get("manufacturer", "").casefold(), row["group_id"],
    ))

    unmapped = []
    seen_unmapped_skus: set[str] = set()
    for group in triage.get("unmapped_groups", []):
        if not isinstance(group, dict):
            continue
        products = [_safe_product(row) | {
            "mpn": row.get("mpn"),
            "supplier_product_key": row.get("supplier_product_key"),
        } for row in group.get("products", []) if isinstance(row, dict)]
        group_skus = [row.get("sku") for row in products]
        if len(group_skus) != len(set(group_skus)) or seen_unmapped_skus.intersection(group_skus):
            raise ReviewInventoryError("Unmapped triage repeats a SKU identifier")
        seen_unmapped_skus.update(group_skus)
        suggestion = group.get("local_rule_suggestion") or {}
        family_id = suggestion.get("family_id")
        safe_suggestion = {
            "family_id": family_id if family_id in family_ids else None,
            "evidence_score": suggestion.get("evidence_score"),
            "score_type": suggestion.get("score_type"),
            "status": suggestion.get("status"),
            "evidence": suggestion.get("evidence"),
            "applied": suggestion.get("applied", False),
        }
        signature_payload = {"workbook_sha256": source_hash, "group": group, "products": products}
        signature = _sha256_bytes(canonical(signature_payload).encode("utf-8"))
        target = UNMAPPED_REVIEW_PREFIX + group["group_id"]
        unmapped.append({
            "group_id": group["group_id"],
            "workbook_sha256": source_hash,
            "manufacturer": group.get("manufacturer", ""),
            "family_code": group.get("family_code", ""),
            "sku_count": len(products),
            "review_request_present": group.get("review_request_present"),
            "suggestion": safe_suggestion,
            "products": products,
            "signature": signature,
            "review": _review_state(store, target, signature),
        })
    unmapped.sort(key=lambda row: (row["review"]["status"] not in {"pending", "stale"},
                                  -(row["suggestion"]["evidence_score"] or 0),
                                  row["manufacturer"].casefold(), row["group_id"]))

    mapped_skus = {row.get("sku") for row in active_products
                   if row.get("family_id") or row.get("candidate_family_id")}
    all_skus = {row.get("sku") for row in active_products}
    if len(mapped_skus) + len(seen_unmapped_skus) != len(all_skus) or mapped_skus.intersection(seen_unmapped_skus):
        raise ReviewInventoryError("Mapped and unmapped SKU queues do not exactly cover the active inventory")
    if len(seen_unmapped_skus) != triage.get("unmapped_sku_count"):
        raise ReviewInventoryError("Unmapped triage SKU count does not match its manifest")
    if {row.get("sku") for group in triage.get("unmapped_groups", []) if isinstance(group, dict)
        for row in group.get("products", []) if isinstance(row, dict)} != all_skus - mapped_skus:
        raise ReviewInventoryError("Unmapped triage SKU identifiers do not match the candidate inventory")

    family_states = Counter(row["review"]["status"] for row in families)
    mapped_states = Counter(row["review"]["status"] for row in mapped_exceptions)
    unmapped_states = Counter(row["review"]["status"] for row in unmapped)
    return {
        "state": "ready",
        "workbook_sha256": source_hash,
        "inventory_sha256": inventory_file_hash,
        "price_values_included": False,
        "family_count": len(families),
        "active_sku_count": len(active_products),
        "mapped_sku_count": len(mapped_skus),
        "mapped_exception_group_count": len(mapped_exceptions),
        "mapped_exception_sku_count": sum(row["sku_count"] for row in mapped_exceptions),
        "unmapped_sku_count": len(seen_unmapped_skus),
        "family_review_states": dict(family_states),
        "mapped_review_states": dict(mapped_states),
        "unmapped_review_states": dict(unmapped_states),
        "family_risk_counts": dict(Counter(row["risk_tier"] for row in families)),
        "families": families,
        "mapped_exception_groups": mapped_exceptions,
        "unmapped_groups": unmapped,
        "note": "Family validation records are private review attestations only. They do not approve claims, bind sources, assign families, change SKU eligibility, or publish.",
    }


def family_review_detail(root: Path, idx, store, family_id: str) -> dict:
    inventory = build_review_inventory(root, idx, store)
    family = next((row for row in inventory["families"] if row["family_id"] == family_id), None)
    if family is None:
        raise ValueError("Unknown family")
    detail = idx.detail(family_id)
    scoped_products = []
    # Reconstruct row details using the same validated inputs used by the worklist.
    inputs, triage, _, _ = _load_inputs(Path(root))
    audits = {group["group_id"]: group for group in triage.get("mapped_group_audit", [])}
    priorities = {group["group_id"]: group for group in triage.get("priority_review_queue", [])}
    for product in inputs["products"]:
        if product.get("active") is not True or family_id not in {product.get("family_id"), product.get("candidate_family_id")}:
            continue
        row = _safe_product(product)
        group_id = product.get("family_mapping_group")
        audit = audits.get(group_id, {})
        priority = priorities.get(group_id, {})
        sku_audit = next((item for item in audit.get("product_identity_review", {}).get("products", [])
                          if item.get("sku") == product.get("sku")), {})
        row.update({
            "association": "current" if product.get("family_id") == family_id else "candidate",
            "mapping_group": group_id,
            "mapping_status": product.get("family_mapping_status"),
            "group_review_reasons": audit.get("product_identity_review", {}).get("issues", []),
            "alternate_family_match": sku_audit.get("best_distinct_alternate_family_match"),
            "priority_review_group": priority.get("review_reasons", []),
            "mpn": None,
            "supplier_product_key": None,
        })
        scoped_products.append(row)
    scoped_products.sort(key=lambda row: (row["association"] != "current", row.get("manufacturer", "").casefold(),
                                          row["sku"]))
    safe_sources = _document_fingerprints(Path(root), detail)
    return {
        **family,
        "family": _without_price_fields(detail.get("family", {})),
        "research": _without_price_fields(detail.get("research", {})),
        "dossier": _without_price_fields(detail.get("dossier", {})),
        "dossier_summary": {
            "provenance_state": detail.get("dossier", {}).get("provenance_state"),
            "alternative_count": len(detail.get("dossier", {}).get("alternatives", [])),
            "group_counts": {key: len(value) for key, value in detail.get("dossier", {}).get("groups", {}).items()},
        },
        "guide_available": bool(detail.get("guide_text")),
        "source_gaps": detail.get("sources", {}).get("source_gaps", []),
        "source_documents": safe_sources,
        "v3_products": scoped_products,
        "v3_sku_ids": [row["sku"] for row in scoped_products],
        "product_research_url": "/admin/products#" + family_id,
    }


def unmapped_review_detail(root: Path, idx, store, group_id: str) -> dict:
    inventory = build_review_inventory(root, idx, store)
    group = next((row for row in inventory["unmapped_groups"] if row["group_id"] == group_id), None)
    if group is None:
        raise ValueError("Unknown unmapped SKU group")
    group["sku_ids"] = [row["sku"] for row in group["products"]]
    candidate_id = group["suggestion"].get("family_id")
    group["product_research_url"] = "/admin/products#" + candidate_id if candidate_id else None
    return group


def mapped_group_review_detail(root: Path, idx, store, group_id: str) -> dict:
    inventory = build_review_inventory(root, idx, store)
    group = next((row for row in inventory["mapped_exception_groups"] if row["group_id"] == group_id), None)
    if group is None:
        raise ValueError("Unknown mapped exception group")
    detail = idx.detail(group["family_id"])
    group["family"] = _without_price_fields(detail.get("family", {}))
    group["research"] = _without_price_fields(detail.get("research", {}))
    group["dossier"] = _without_price_fields(detail.get("dossier", {}))
    group["source_gaps"] = detail.get("sources", {}).get("source_gaps", [])
    group["source_documents"] = _document_fingerprints(Path(root), detail)
    group["products"] = []
    for product in inventory["families"]:
        if product["family_id"] == group["family_id"]:
            group["product_research_url"] = "/admin/products#" + group["family_id"]
            break
    inputs, triage, _, _ = _load_inputs(Path(root))
    audit = {row["group_id"]: row for row in triage.get("mapped_group_audit", [])
             if isinstance(row, dict) and isinstance(row.get("group_id"), str)}.get(group_id, {})
    audited_products = {
        row.get("sku"): row for row in audit.get("product_identity_review", {}).get("products", [])
        if isinstance(row, dict)
    }
    for product in inputs["products"]:
        if product.get("active") is not True or product.get("family_mapping_group") != group_id:
            continue
        scoped = _safe_product(product)
        sku_audit = audited_products.get(product["sku"], {})
        scoped.update({
            "association": "current" if product.get("family_id") == group["family_id"] else "candidate",
            "mapping_flags": audit.get("product_identity_review", {}).get("issues", []),
            "alternate_family_match": sku_audit.get("best_distinct_alternate_family_match"),
        })
        group["products"].append(scoped)
    group["products"].sort(key=lambda row: row["sku"])
    return group


def validate_family_review(root: Path, idx, store, scope: str, scope_id: str,
                           data: dict, actor: str, expected_version: int) -> dict:
    if scope not in {"family", "mapped", "unmapped"}:
        raise ValueError("Unknown review scope")
    if not isinstance(data, dict):
        raise ValueError("Review data must be an object")
    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not 10 <= len(rationale.strip()) <= 10000:
        raise ValueError("A rationale of 10 to 10000 characters is required")
    signature = data.get("review_signature")
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise ValueError("Review signature is invalid")
    reviewed_ids = data.get("reviewed_sku_ids")
    if not isinstance(reviewed_ids, list) or any(not isinstance(value, str) for value in reviewed_ids):
        raise ValueError("Reviewed SKU identifiers must be a list of strings")
    if len(reviewed_ids) != len(set(reviewed_ids)):
        raise ValueError("Reviewed SKU identifiers contain duplicates")

    if scope == "family":
        current = family_review_detail(root, idx, store, scope_id)
        decision = data.get("decision")
        allowed = {"confirmed", "correction_needed", "blocked"}
        expected_ids = set(current["v3_sku_ids"])
        target = FAMILY_REVIEW_PREFIX + scope_id
        checks = ("identity_checked", "sources_checked", "sku_mappings_checked")
        if any(data.get(check) is not True for check in checks):
            raise ValueError("Confirm identity, source/dossier, and every associated SKU mapping before saving")
    elif scope == "mapped":
        current = mapped_group_review_detail(root, idx, store, scope_id)
        decision = data.get("decision")
        allowed = {"confirmed", "correction_needed", "blocked"}
        expected_ids = set(current["sku_ids"])
        target = MAPPED_REVIEW_PREFIX + scope_id
        checks = ("identity_checked", "sources_checked", "sku_mappings_checked")
        if any(data.get(check) is not True for check in checks):
            raise ValueError("Confirm family identity, source/dossier, and every flagged SKU mapping before saving")
    else:
        current = unmapped_review_detail(root, idx, store, scope_id)
        decision = data.get("decision")
        allowed = {"candidate_supported_not_applied", "candidate_rejected_keep_unassigned",
                   "needs_evidence", "non_product_hold"}
        expected_ids = set(current["sku_ids"])
        target = UNMAPPED_REVIEW_PREFIX + scope_id
        if data.get("products_checked") is not True:
            raise ValueError("Confirm that every SKU in this unmapped group was reviewed")
    if decision not in allowed:
        raise ValueError("Invalid review decision for this scope")
    if signature != current["signature"]:
        raise ValueError("Review evidence changed; refresh the worklist before saving")
    if set(reviewed_ids) != expected_ids:
        raise ValueError("Review must cover every SKU in this family/group exactly once")
    payload = {
        "scope": scope,
        "scope_id": scope_id,
        "decision": decision,
        "rationale": rationale.strip(),
        "review_signature": current["signature"],
        "workbook_sha256": current.get("workbook_sha256", ""),
        "reviewed_sku_ids": sorted(reviewed_ids),
        "dossier_checked": data.get("identity_checked") is True,
        "sources_checked": data.get("sources_checked") is True,
        "sku_mappings_checked": data.get("sku_mappings_checked") is True,
        "products_checked": data.get("products_checked") is True,
        "canonical_mapping_changed": False,
        "source_binding_changed": False,
        "claim_approval_changed": False,
        "publication_changed": False,
    }
    return {"revision": store.save_revision(target, "family_validation_review", payload, actor, expected_version),
            "decision": decision, "canonical_mapping_changed": False, "source_binding_changed": False,
            "claim_approval_changed": False, "publication_changed": False}
