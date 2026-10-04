"""Formal reviews and atomic local publication; drafts never alter runtime."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, StrictBool, StrictStr

from bot_engine import recommendation_allowed
from product_research import ResearchIndex
from research_store import Conflict, ResearchStore, canonical, stamp
from local_source_review import checked_pages

CORRECTABLE = {"product_name", "material_type", "product_use", "mpn", "active",
               "thermal_r_value", "acoustic_rw", "nrc_aw", "bot_content_status"}

class ReviewInput(BaseModel):
    kind: Literal["claim", "sku"]
    decision: Literal["approved", "rejected", "needs_information", "revoked"]
    rationale: StrictStr
    citation: dict = {}
    claim: dict = {}
    sku_record_id: StrictStr = ""
    corrections: dict[str, StrictStr] = {}
    resolutions: dict[str, StrictStr] = {}
    duplicate_resolution: StrictStr = ""
    variant_confirmed: StrictBool = False
    eligibility_requested: StrictBool = False
    evidence_ids: list[StrictStr] = []
    applicable_skus: list[StrictStr] = []


def normal_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def citation(index: ResearchIndex, item: dict) -> dict:
    if not isinstance(item.get("document_id"), str):
        raise ValueError("Choose an exact local document ID")
    path, doc = index.document(item.get("document_id", ""))
    if item.get("sha256") != doc["sha256"]:
        raise Conflict("Source hash changed; reopen the document before review")
    page = item.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("An exact positive source page number is required")
    extraction = checked_pages(path, doc["sha256"])
    if extraction["status"] == "read_error":
        raise ValueError(f"Source PDF cannot be read: {extraction['error']}")
    if page > len(extraction["pages"]):
        raise ValueError("Citation page does not exist")
    if not isinstance(item.get("locator"), str) or not isinstance(item.get("quote"), str):
        raise ValueError("Citation locator and quote must be text")
    locator, quote = item["locator"].strip(), item["quote"].strip()
    if len(locator) < 3 or re.search(r"\b(?:pending|unknown|tbd)\b", locator, re.I):
        raise ValueError("An exact table/section/region locator is required")
    if len(quote) < 8 or normal_text(quote) not in normal_text(extraction["pages"][page - 1]["text"]):
        raise ValueError("Supporting quote must occur on the cited page; scans need manual/OCR review outside this workflow")
    return {**doc, "document_id": doc["id"], "page": page, "locator": locator, "quote": quote}


def validate_review(index: ResearchIndex, family_id: str, data: dict, actor: str) -> dict:
    data = ReviewInput.model_validate(data).model_dump()
    if family_id not in index.families:
        raise ValueError("Unknown family")
    decision = data.get("decision")
    if decision not in {"approved", "rejected", "needs_information", "revoked"}:
        raise ValueError("Invalid review decision")
    kind = data.get("kind")
    if kind not in {"claim", "sku"}:
        raise ValueError("Review kind must be claim or sku")
    if len(data.get("rationale", "").strip()) < 10:
        raise ValueError("Provide a meaningful review rationale")
    result = {**data, "reviewer": actor, "reviewed_at": stamp(), "family_id": family_id,
              "baseline": index.baseline()}
    if kind == "sku":
        sku = index.by_sku.get(data.get("sku_record_id"))
        if not sku or sku["family_id"] != family_id:
            raise ValueError("SKU is not a child of this family")
        result["target"] = "sku:" + sku["sku_record_id"]
    else:
        claim = dict(data.get("claim") or {})
        key = claim.get("evidence_id", "")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Z0-9]+(?:[-_][A-Z0-9]+)*", key) or len(key) > 100:
            raise ValueError("A stable evidence_id is required")
        result["target"] = f"claim:{family_id}:{key}"
    if decision != "approved":
        return result
    if not recommendation_allowed(index.families[family_id]):
        raise ValueError("Family identity is unresolved; approval is blocked")
    source = citation(index, data.get("citation") or {})
    result["citation"] = source
    if kind == "sku":
        corrections = data.get("corrections") or {}
        if not isinstance(corrections, dict) or not set(corrections).issubset(CORRECTABLE):
            raise ValueError("Only explicit allowed SKU field corrections are supported")
        if any(not isinstance(value, str) or len(value) > 2000 for value in corrections.values()):
            raise ValueError("Corrected SKU values must be bounded text")
        result["corrections"] = corrections
        conflicts = sku.get("validation_notes", "").split(";")
        conflicts = [value.strip() for value in conflicts if value.strip()]
        resolutions = data.get("resolutions") or {}
        if any(len(str(resolutions.get(issue, "")).strip()) < 10 for issue in conflicts):
            raise ValueError("Every original validation issue needs a documented resolution")
        duplicates = [field for field in index.code_counts if sku.get(field) and index.code_counts[field][sku[field].casefold()] > 1]
        if duplicates and len(data.get("duplicate_resolution", "").strip()) < 10:
            raise ValueError("Shared SKU codes need explicit record/variant disambiguation")
        if data.get("variant_confirmed") is not True:
            raise ValueError("Explicit confirmation of the exact SKU-to-family/variant association is required")
        if not isinstance(data.get("evidence_ids"), list) or not data["evidence_ids"]:
            raise ValueError("Select exact reviewed evidence IDs applicable to this SKU")
        if not isinstance(data.get("eligibility_requested"), bool):
            raise ValueError("Choose whether this SKU should become internally selection-eligible")
        return result
    claim.update({
        "evidence_status": "verified", "verified_by": actor, "verified_at": result["reviewed_at"],
        "source_locator": f"Page {source['page']}, {source['locator']} [sha256 {source['sha256']}]",
        "extraction_method": "manual_transcription",
    })
    schema = json.loads((index.root / "schemas" / "performance-evidence.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator({"$ref": "#/$defs/evidence", "$defs": schema["$defs"]}, format_checker=FormatChecker())
    errors = [error.message for error in validator.iter_errors(claim)]
    if errors:
        raise ValueError("; ".join(errors))
    if claim["value_type"] == "scalar" and (isinstance(claim["value"], bool) or not isinstance(claim["value"], (int, float))):
        raise ValueError("Scalar claims need a numeric value")
    if isinstance(claim["value"], (int, float)) and not math.isfinite(claim["value"]):
        raise ValueError("Metric value must be finite")
    if not claim["variant"].strip() or not claim["unit"].strip() or not claim["test_context"].strip():
        raise ValueError("Exact variant, unit and test context are required")
    if claim["metric_type"] != "product_identity" and not claim["test_standard"].strip():
        raise ValueError("Performance claims require the relevant test standard")
    result["claim"] = claim
    result["applicable_skus"] = data.get("applicable_skus") or []
    if any(key not in index.by_sku or index.by_sku[key]["family_id"] != family_id for key in result["applicable_skus"]):
        raise ValueError("Claim applicability contains a SKU outside this family")
    return result


def latest_reviews(store: ResearchStore):
    latest = {}
    for revision in store.history():
        if revision["kind"] == "review":
            latest[revision["target"]] = revision
    return latest


def publication_preview(index: ResearchIndex, store: ResearchStore, actor: str, *, scoped: bool = False):
    baseline = index.baseline()
    version = store.version()
    claims, revoked, sku_decisions, blockers = {}, [], {}, []
    changes = []
    for target, revision in latest_reviews(store).items():
        data = revision["payload"]
        if data["decision"] in {"rejected", "revoked"}:
            if data["kind"] == "claim":
                revoked.append({"family_id": data["family_id"], "evidence_id": data["claim"]["evidence_id"]})
            changes.append({"target": target, "decision": data["decision"], "revision": revision["id"]})
            continue
        if data["decision"] != "approved":
            continue
        if data["baseline"] != baseline:
            blockers.append(f"{target}: source inputs changed; review again")
            continue
        with store.connection() as conn:
            reviewer = conn.execute("SELECT roles,disabled FROM users WHERE username=?", (data["reviewer"],)).fetchone()
        if not reviewer or reviewer["disabled"] or "reviewer" not in json.loads(reviewer["roles"]):
            blockers.append(f"{target}: reviewer account no longer authorised")
            continue
        # Re-check source page/quote/hash rather than trusting submitted UI values.
        citation(index, data["citation"])
        if data["kind"] == "claim":
            claims[target] = data
        else:
            sku_decisions[data["sku_record_id"]] = data
        changes.append({"target": target, "decision": "approved", "revision": revision["id"]})
    eligibility = {}
    for key, decision in sku_decisions.items():
        row = {**index.by_sku[key], **decision["corrections"]}
        applicable = [data for data in claims.values() if data["family_id"] == decision["family_id"]
                      and data["claim"]["evidence_id"] in decision["evidence_ids"] and key in data["applicable_skus"]
                      and data["claim"]["scope"] in {"product", "component"}]
        eligible = bool(applicable) and row.get("active", "").casefold() in {"yes", "true", "active", "1"} and row.get("bot_content_status", "").upper() == "READY"
        if decision["eligibility_requested"] and not eligible:
            blockers.append(f"{key}: exact published applicable claim, confirmed active state and READY content are required")
        eligibility[key] = {"eligible": eligible and decision["eligibility_requested"],
                            "corrections": decision["corrections"], "family_id": decision["family_id"],
                            "evidence_ids": [item["claim"]["evidence_id"] for item in applicable],
                            "reviewer": decision["reviewer"], "reviewed_at": decision["reviewed_at"]}
        if scoped:
            eligibility[key]["source_dependency"] = decision["citation"]["path"]
    active = store.active()
    old = active["payload"] if active else {}
    old_claims = {(c["family_id"], c["claim"]["evidence_id"]): c for c in old.get("claims", [])}
    new_claims = {(c["family_id"], c["claim"]["evidence_id"]): c for c in claims.values()}
    claim_diff = {
        "added": [list(key) for key in new_claims.keys() - old_claims.keys()],
        "replaced": [list(key) for key in new_claims.keys() & old_claims.keys() if new_claims[key] != old_claims[key]],
        "removed": [list(key) for key in old_claims.keys() - new_claims.keys()],
    }
    old_eligibility = old.get("eligibility", {})
    eligibility_diff = {key: {"before": old_eligibility.get(key, {"eligible": False}),
                             "after": eligibility.get(key, {"eligible": False})}
                        for key in old_eligibility.keys() | eligibility.keys()
                        if old_eligibility.get(key) != eligibility.get(key)}
    payload = {"review_version": version, "claims": list(claims.values()), "revoked": revoked,
               "eligibility": eligibility, "blockers": blockers, "changes": changes,
               "claim_diff": claim_diff, "eligibility_diff": eligibility_diff,
               "previous_publication": active["id"] if active else None,
               "impact": {"fact_claims_after": len(claims), "fact_claims_before": len(old_claims),
                          "eligible_skus_after": sum(v["eligible"] for v in eligibility.values()),
                          "eligible_skus_before": sum(v["eligible"] for v in old.get("eligibility", {}).values()),
                          "automatic_customer_selection": False},
               "baseline": baseline}
    if scoped:
        payload["dependency_mode"] = "source_scoped_v1"
        payload["source_bindings"] = index.source_bindings()
        payload["non_source_baseline"] = index.non_source_baseline()
    identifier = store.preview(payload, baseline, actor)
    return {"proposal_id": identifier, **payload}


def active_effective(index: ResearchIndex, store: ResearchStore) -> dict:
    active = store.active()
    if not active:
        return {"state": "baseline_only", "publication_id": None, "claims": [], "revoked": [], "eligibility": {}}
    payload = active["payload"]
    if payload.get("dependency_mode") == "source_scoped_v1":
        return scoped_effective(index, store, active)
    if active["baseline"] != index.baseline():
        return {"state": "stale_sources_review_required", "publication_id": active["id"], "claims": [], "revoked": active["payload"]["revoked"], "eligibility": {}}
    with store.connection() as conn:
        authorised = {row["username"] for row in conn.execute("SELECT username,roles FROM users WHERE disabled=0")
                      if "reviewer" in json.loads(row["roles"])}
    if any(c["reviewer"] not in authorised for c in payload["claims"]) or any(v["reviewer"] not in authorised for v in payload["eligibility"].values()):
        return {"state": "reviewer_disabled_review_required", "publication_id": active["id"], "claims": [], "revoked": payload["revoked"], "eligibility": {}}
    return {"state": "published", "publication_id": active["id"], **payload}


def scoped_effective(index: ResearchIndex, store: ResearchStore, active: dict) -> dict:
    payload = active["payload"]
    empty = {"publication_id": active["id"], "claims": [], "revoked": payload["revoked"], "eligibility": {}}
    if not isinstance(payload.get("source_bindings"), dict) or payload.get("non_source_baseline") != index.non_source_baseline():
        return {**empty, "state": "stale_sources_review_required", "hold_scope": "global_unknown_dependency"}
    current = index.source_bindings()
    original = payload["source_bindings"]
    changed = {path for path in original.keys() | current.keys() if original.get(path) != current.get(path)}
    with store.connection() as conn:
        authorised = {row["username"] for row in conn.execute("SELECT username,roles FROM users WHERE disabled=0")
                      if "reviewer" in json.loads(row["roles"])}
    claims, holds = [], []
    for claim in payload["claims"]:
        path = claim.get("citation", {}).get("path")
        if path not in original:
            return {**empty, "state": "stale_sources_review_required", "hold_scope": "global_unknown_dependency"}
        if path in changed or claim["reviewer"] not in authorised:
            holds.append({"kind": "claim", "family_id": claim["family_id"],
                          "evidence_id": claim["claim"]["evidence_id"], "source": path,
                          "reason": "source_changed" if path in changed else "reviewer_unauthorised"})
        else:
            claims.append(claim)
    available = {(row["family_id"], row["claim"]["evidence_id"]) for row in claims}
    eligibility = {}
    for key, row in payload["eligibility"].items():
        path = row.get("source_dependency")
        if path not in original:
            return {**empty, "state": "stale_sources_review_required", "hold_scope": "global_unknown_dependency"}
        claim_missing = not any((row["family_id"], identifier) in available for identifier in row["evidence_ids"])
        if path in changed or row["reviewer"] not in authorised or (row["eligible"] and claim_missing):
            holds.append({"kind": "sku", "sku_record_id": key, "family_id": row["family_id"], "source": path,
                          "reason": "source_or_reviewer_or_applicable_claim_changed"})
        else:
            eligibility[key] = row
    return {**payload, "state": "published_with_scoped_holds" if holds else "published",
            "publication_id": active["id"], "claims": claims, "eligibility": eligibility,
            "holds": holds, "hold_scope": "explicit_citation_dependencies_only",
            "changed_sources": sorted(changed)}


def effective_evidence(index: ResearchIndex, store: ResearchStore) -> tuple[dict, dict]:
    state = active_effective(index, store)
    evidence = {key: list(record["evidence_items"]) for key, record in index.evidence.items()}
    for revoke in state["revoked"]:
        evidence[revoke["family_id"]] = [c for c in evidence.get(revoke["family_id"], []) if c["evidence_id"] != revoke["evidence_id"]]
    for approved in state["claims"]:
        key, claim = approved["family_id"], approved["claim"]
        evidence[key] = [c for c in evidence.get(key, []) if c["evidence_id"] != claim["evidence_id"]] + [claim]
    return evidence, state
